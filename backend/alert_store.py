"""
PROTACTICS — Almacén de alertas idempotente
─────────────────────────────────────────────────────────────────
Helpers compartidos por los motores de SLA y de anomalías para crear/actualizar
alertas sin duplicar y para auto-resolver las que dejaron de aplicar. La clave de
deduplicación es (puerto_id, tipo, year, mes, dia); `dia` NULL = alcance mensual.

Garantías:
  • upsert_alerta: si ya existe una alerta ABIERTA (open/acknowledged) con la
    misma clave, la actualiza conservando su estado (un 'acknowledged' del
    operador no se pisa). Si no existe, crea una nueva 'open'.
  • resolver_obsoletas: resuelve (estado='resolved') las alertas abiertas de los
    tipos gestionados en un mes cuya clave ya no está en el conjunto vigente.
"""
from datetime import datetime

from models import Alerta

SEVERIDAD_ORDEN = {"info": 0, "warning": 1, "critical": 2}
ESTADOS_ABIERTOS = ("open", "acknowledged")


def _match(db, puerto_id, tipo, year, mes, dia):
    q = db.query(Alerta).filter(
        Alerta.puerto_id == puerto_id,
        Alerta.tipo == tipo,
        Alerta.estado.in_(ESTADOS_ABIERTOS),
        Alerta.year == year,
        Alerta.mes == mes,
    )
    q = q.filter(Alerta.dia.is_(None)) if dia is None else q.filter(Alerta.dia == dia)
    return q.first()


def upsert_alerta(db, *, puerto_id, tipo, severidad, mensaje,
                  year, mes, dia=None, payload=None):
    """Crea o actualiza la alerta de esa clave. Devuelve la fila (sin commit)."""
    row = _match(db, puerto_id, tipo, year, mes, dia)
    if row:
        row.severidad = severidad
        row.mensaje = mensaje
        row.payload = payload
        # estado se conserva (open/acknowledged): no se reabre ni se pisa el ack.
    else:
        row = Alerta(puerto_id=puerto_id, tipo=tipo, severidad=severidad,
                     mensaje=mensaje, estado="open", year=year, mes=mes, dia=dia,
                     payload=payload, creada_en=datetime.utcnow())
        db.add(row)
    return row


def resolver_obsoletas(db, *, puerto_id, year, mes, tipos, claves_validas,
                       actor_id=None):
    """Resuelve alertas abiertas de `tipos` en (puerto, year, mes) cuya
    (tipo, dia) NO esté en `claves_validas`. `actor_id` None = resuelta por el
    sistema. No hace commit."""
    abiertas = db.query(Alerta).filter(
        Alerta.puerto_id == puerto_id,
        Alerta.year == year,
        Alerta.mes == mes,
        Alerta.tipo.in_(tuple(tipos)),
        Alerta.estado.in_(ESTADOS_ABIERTOS),
    ).all()
    for a in abiertas:
        if (a.tipo, a.dia) not in claves_validas:
            a.estado = "resolved"
            a.resuelta_en = datetime.utcnow()
            a.resuelta_por = actor_id
