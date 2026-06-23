"""
PROTACTICS — Ventanas de mantenimiento (exclusiones compartidas)
─────────────────────────────────────────────────────────────────
Fuente única de verdad de qué días de un puerto-mes están excluidos por
mantenimiento programado o falla técnica del escáner. Lo consumen TANTO el motor
de anomalías (`anomalies.py`) como el de SLA (`sla.py`), de modo que ambos vean
exactamente las mismas exclusiones y no puedan divergir.

Regla: una ventana cubre días COMPLETOS [fecha_inicio, fecha_fin] inclusive.
`fecha_fin` NULL = ventana abierta (en curso) → cubre hasta el fin del mes
consultado (los días futuros no tienen escaneos, así que tratarlos como
excluidos es inocuo para anomalías y SLA).
"""
import calendar
from datetime import date

from sqlalchemy.orm import Session

from models import VentanaMantenimiento


def dias_excluidos(db: Session, puerto_id: int, year: int, mes: int) -> set:
    """Conjunto de días (1..N) del (puerto, year, mes) cubiertos por mantenimiento.

    Devuelve un `set[int]`. Vacío si no hay ventanas que intersecten el mes.
    Maneja ventanas abiertas (fecha_fin NULL), ventanas que cruzan el inicio o el
    fin del mes, y solapamientos (la unión de días se resuelve sola al usar set).
    """
    dim = calendar.monthrange(year, mes)[1]
    month_start = date(year, mes, 1)
    month_end = date(year, mes, dim)

    ventanas = db.query(VentanaMantenimiento).filter_by(puerto_id=puerto_id).all()
    out = set()
    for v in ventanas:
        inicio = v.fecha_inicio
        fin = v.fecha_fin if v.fecha_fin is not None else month_end  # abierta → fin de mes
        # Recortar la ventana a los límites del mes (intersección).
        lo = max(inicio, month_start)
        hi = min(fin, month_end)
        if lo > hi:
            continue  # la ventana no toca este mes
        out.update(range(lo.day, hi.day + 1))
    return out


def mes_totalmente_en_mantenimiento(db: Session, puerto_id: int,
                                    year: int, mes: int) -> bool:
    """True si TODOS los días del mes están bajo mantenimiento.

    Lo usa el motor de SLA: un mes sin datos NO rompe la racha ni genera alerta
    `no_upload` si el mes entero estuvo en mantenimiento (RN-4.11)."""
    dim = calendar.monthrange(year, mes)[1]
    return len(dias_excluidos(db, puerto_id, year, mes)) >= dim
