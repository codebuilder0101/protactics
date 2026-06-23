"""
PROTACTICS — Motor de cumplimiento de SLA
─────────────────────────────────────────────────────────────────
Evalúa, por puerto y mes, la disponibilidad observada contra la meta configurada
(tabla `sla`), registra infracciones y abre/cierra alertas de forma idempotente.
También calcula la racha de meses consecutivos en incumplimiento.

Reglas clave (acordadas con el cliente):
  • Meta por defecto: disponibilidad 95% (`puerto_id` NULL en `sla`). Un puerto
    puede tener su propia meta que la sobreescribe.
  • Los días en mantenimiento se EXCLUYEN del cálculo (denominador): la
    disponibilidad se mide solo sobre días elegibles. Ver `mantenimiento.py`.
  • Un mes pasado SIN datos de un puerto activo rompe la racha y genera una
    alerta `no_upload`, salvo que el mes entero esté en mantenimiento.
  • Idempotencia: reevaluar no duplica infracciones ni alertas; corregir los
    datos para cumplir resuelve la infracción y su alerta automáticamente.

Estados auditables del badge (reemplazan el semáforo de umbrales fijos):
  CUMPLE · EN_RIESGO · INCUMPLE · EN_MANTENIMIENTO · SIN_DATOS
"""
import calendar
from datetime import datetime

from sqlalchemy.orm import Session

from models import EscaneosDiarios, SLA, Infraccion
import mantenimiento as mant
from alert_store import upsert_alerta, resolver_obsoletas

MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# ── Parámetros (configurables) ─────────────────────────────
DEFAULT_AVAILABILITY_TARGET = 95.0   # meta por defecto si no hay fila en `sla`
METRIC = "availability"
RIESGO_MARGEN = 3.0                  # EN_RIESGO: cumple pero a < margen de la meta
RACHA_CRITICA = 3                    # racha ≥ esto → severidad critical
TIPOS_SLA = ("sla_breach", "no_upload")


# ══════════════════════════════════════════════════════════════
#  Meta efectiva
# ══════════════════════════════════════════════════════════════
def meta_efectiva(db: Session, puerto_id: int, metrica: str = METRIC):
    """SLA aplicable a un puerto: su meta propia activa, o la global (puerto NULL),
    o None (el llamador usa DEFAULT_AVAILABILITY_TARGET)."""
    row = db.query(SLA).filter_by(puerto_id=puerto_id, metrica=metrica, activo=True).first()
    if row:
        return row
    return db.query(SLA).filter_by(puerto_id=None, metrica=metrica, activo=True).first()


# ══════════════════════════════════════════════════════════════
#  Disponibilidad (excluyendo mantenimiento)
# ══════════════════════════════════════════════════════════════
def disponibilidad_sla(db: Session, puerto_id: int, year: int, mes: int):
    """Disponibilidad (%) del mes sobre días ELEGIBLES (no en mantenimiento).

    = días activos elegibles / días elegibles transcurridos × 100.
    Devuelve None si el mes es futuro o no hay días elegibles (todo mantenimiento)."""
    today = datetime.utcnow()
    if (year, mes) > (today.year, today.month):
        return None  # mes futuro
    dim = calendar.monthrange(year, mes)[1]
    last_day = today.day if (year == today.year and mes == today.month) else dim
    excl = mant.dias_excluidos(db, puerto_id, year, mes)
    elegibles = [d for d in range(1, last_day + 1) if d not in excl]
    if not elegibles:
        return None
    activos = {e.dia for e in db.query(EscaneosDiarios).filter(
        EscaneosDiarios.puerto_id == puerto_id, EscaneosDiarios.year == year,
        EscaneosDiarios.mes == mes, EscaneosDiarios.total > 0).all()}
    n_activos = sum(1 for d in elegibles if d in activos)
    return round(n_activos / len(elegibles) * 100.0, 1)


def _primer_mes(db: Session, puerto_id: int):
    row = db.query(EscaneosDiarios.year, EscaneosDiarios.mes)\
        .filter_by(puerto_id=puerto_id)\
        .order_by(EscaneosDiarios.year, EscaneosDiarios.mes).first()
    return (row.year, row.mes) if row else None


def _ultimo_mes(db: Session, puerto_id: int):
    row = db.query(EscaneosDiarios.year, EscaneosDiarios.mes)\
        .filter_by(puerto_id=puerto_id)\
        .order_by(EscaneosDiarios.year.desc(), EscaneosDiarios.mes.desc()).first()
    return (row.year, row.mes) if row else None


# ══════════════════════════════════════════════════════════════
#  Clasificación (pura, sin escribir)
# ══════════════════════════════════════════════════════════════
def clasificar_mes(db: Session, puerto_id: int, year: int, mes: int) -> dict:
    """Clasifica el estado de SLA de un mes SIN tocar la base de datos.

    La usan el badge auditable (solo lectura), la racha y `evaluar_mes`.
    `es_incumplimiento` alimenta la racha; `neutral` = no cuenta ni rompe."""
    today = datetime.utcnow()
    cur = (today.year, today.month)
    ym = (year, mes)
    meta = meta_efectiva(db, puerto_id)
    umbral = meta.umbral if meta else DEFAULT_AVAILABILITY_TARGET
    sla_id = meta.id if meta else None
    dim = calendar.monthrange(year, mes)[1]
    excl = mant.dias_excluidos(db, puerto_id, year, mes)
    base = {"year": year, "mes": mes, "mes_nombre": MONTHS[mes - 1],
            "umbral": umbral, "sla_id": sla_id, "observado": None,
            "dias_mantenimiento": len(excl)}

    # Mes completamente en mantenimiento → neutro, sin SLA.
    if len(excl) >= dim:
        return {**base, "estado": "EN_MANTENIMIENTO",
                "motivo": "Mes en mantenimiento programado / falla técnica",
                "es_incumplimiento": False, "neutral": True}

    # Mes futuro → neutro.
    if ym > cur:
        return {**base, "estado": "SIN_DATOS", "motivo": "Mes futuro",
                "es_incumplimiento": False, "neutral": True}

    n_rows = db.query(EscaneosDiarios)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).count()

    if n_rows == 0:
        if ym == cur:
            return {**base, "estado": "SIN_DATOS",
                    "motivo": "Mes en curso sin datos aún",
                    "es_incumplimiento": False, "neutral": True}
        # Solo un HUECO INTERNO (mes faltante ENTRE dos meses con datos) cuenta
        # como no_upload. Los meses posteriores al último reporte NO se marcan:
        # un puerto que aún no ha reportado más adelante no incumple por cada mes
        # transcurrido (evita inundar de alertas al cargar un mes antiguo).
        primer = _primer_mes(db, puerto_id)
        ultimo = _ultimo_mes(db, puerto_id)
        if primer is not None and ultimo is not None and primer < ym < ultimo:
            return {**base, "estado": "INCUMPLE", "tipo_alerta": "no_upload",
                    "motivo": f"Sin carga de datos para {MONTHS[mes - 1]} {year} "
                              f"(hueco entre meses reportados)",
                    "es_incumplimiento": True, "neutral": False}
        return {**base, "estado": "SIN_DATOS", "motivo": "Sin datos",
                "es_incumplimiento": False, "neutral": True}

    obs = disponibilidad_sla(db, puerto_id, year, mes)
    base["observado"] = obs
    if obs is None:
        return {**base, "estado": "SIN_DATOS", "motivo": "Sin días elegibles",
                "es_incumplimiento": False, "neutral": True}
    if obs < umbral:
        return {**base, "estado": "INCUMPLE", "tipo_alerta": "sla_breach",
                "motivo": f"Disponibilidad {obs}% por debajo de la meta {umbral}%",
                "es_incumplimiento": True, "neutral": False}
    if obs < umbral + RIESGO_MARGEN:
        return {**base, "estado": "EN_RIESGO",
                "motivo": f"Disponibilidad {obs}% cerca de la meta {umbral}%",
                "es_incumplimiento": False, "neutral": False}
    return {**base, "estado": "CUMPLE",
            "motivo": f"Disponibilidad {obs}% cumple la meta {umbral}%",
            "es_incumplimiento": False, "neutral": False}


# ══════════════════════════════════════════════════════════════
#  Infracciones
# ══════════════════════════════════════════════════════════════
def _clear_infraccion(db: Session, puerto_id: int, year: int, mes: int):
    db.query(Infraccion).filter_by(puerto_id=puerto_id, year=year, mes=mes).delete()


def _set_infraccion(db: Session, puerto_id: int, sla_id, year: int, mes: int,
                    obs: float, umbral: float):
    """Reemplaza la infracción del mes (idempotente). None si no hay SLA (no
    debería ocurrir: siempre existe la meta global por defecto)."""
    _clear_infraccion(db, puerto_id, year, mes)
    if sla_id is None:
        return None
    inf = Infraccion(puerto_id=puerto_id, sla_id=sla_id, year=year, mes=mes,
                     dia=None, valor_observado=obs, valor_esperado=umbral,
                     detectada_en=datetime.utcnow())
    db.add(inf)
    return inf


# ══════════════════════════════════════════════════════════════
#  Evaluación (escribe infracciones + alertas)
# ══════════════════════════════════════════════════════════════
def evaluar_mes(db: Session, puerto_id: int, year: int, mes: int,
                actor_id=None, severidad: str = "warning") -> dict:
    """Evalúa un mes y sincroniza infracción + alertas. NO hace commit."""
    info = clasificar_mes(db, puerto_id, year, mes)
    claves_validas = set()

    if info["estado"] == "INCUMPLE":
        tipo = info["tipo_alerta"]
        if tipo == "sla_breach":
            obs, umbral, sla_id = info["observado"], info["umbral"], info["sla_id"]
            _set_infraccion(db, puerto_id, sla_id, year, mes, obs, umbral)
            mensaje = (f"Incumplimiento de SLA: disponibilidad {obs}% por debajo "
                       f"de la meta {umbral}% en {MONTHS[mes - 1]} {year}.")
            payload = {"observado": obs, "umbral": umbral, "metrica": METRIC}
        else:  # no_upload
            _clear_infraccion(db, puerto_id, year, mes)
            mensaje = f"Sin carga de datos para {MONTHS[mes - 1]} {year}."
            payload = {"motivo": "no_upload"}
        a = upsert_alerta(db, puerto_id=puerto_id, tipo=tipo, severidad=severidad,
                          mensaje=mensaje, year=year, mes=mes, dia=None, payload=payload)
        db.flush()
        if tipo == "sla_breach":
            inf = db.query(Infraccion)\
                .filter_by(puerto_id=puerto_id, year=year, mes=mes).first()
            if inf:
                inf.alerta_id = a.id
        claves_validas.add((tipo, None))
    else:
        _clear_infraccion(db, puerto_id, year, mes)

    resolver_obsoletas(db, puerto_id=puerto_id, year=year, mes=mes,
                       tipos=TIPOS_SLA, claves_validas=claves_validas,
                       actor_id=actor_id)
    return info


def _racha_desde(resultados: list) -> int:
    """Racha de incumplimiento al final de la serie: cuenta incumplimientos
    consecutivos desde el último mes, saltando los meses neutrales
    (mantenimiento / futuro / en curso) y deteniéndose en el primero que cumple."""
    r = 0
    for info in reversed(resultados):
        if info["neutral"]:
            continue
        if info["es_incumplimiento"]:
            r += 1
        else:
            break
    return r


def evaluar_puerto(db: Session, puerto_id: int, actor_id=None) -> dict:
    """Evalúa TODOS los meses del puerto (desde su primer dato hasta el mes en
    curso), sincroniza alertas/infracciones y calcula la racha. Un solo commit.

    Recorrer todos los meses es barato (puñado de filas) y deja la racha y la
    detección de meses faltantes (no_upload) siempre consistentes."""
    primer = _primer_mes(db, puerto_id)
    if primer is None:
        db.commit()
        return {"puerto_id": puerto_id, "meses": [], "racha": 0}

    today = datetime.utcnow()
    cur = (today.year, today.month)
    resultados = []
    streak = 0
    y, m = primer
    while (y, m) <= cur:
        preview = clasificar_mes(db, puerto_id, y, m)
        if preview["es_incumplimiento"]:
            streak += 1
        elif not preview["neutral"]:
            streak = 0   # un mes que cumple rompe la racha
        # los meses neutrales no cambian la racha
        sev = "critical" if streak >= RACHA_CRITICA else "warning"
        info = evaluar_mes(db, puerto_id, y, m, actor_id=actor_id, severidad=sev)
        info["racha_hasta_aqui"] = streak
        resultados.append(info)
        m += 1
        if m > 12:
            m = 1
            y += 1

    db.commit()
    return {"puerto_id": puerto_id, "meses": resultados,
            "racha": _racha_desde(resultados)}


def racha_incumplimiento(db: Session, puerto_id: int) -> int:
    """Racha actual de meses consecutivos en incumplimiento (solo lectura)."""
    primer = _primer_mes(db, puerto_id)
    if primer is None:
        return 0
    today = datetime.utcnow()
    cur = (today.year, today.month)
    resultados = []
    y, m = primer
    while (y, m) <= cur:
        resultados.append(clasificar_mes(db, puerto_id, y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return _racha_desde(resultados)
