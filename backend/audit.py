"""
PROTACTICS — Pista de auditoría (append-only, a prueba de manipulación)
─────────────────────────────────────────────────────────────────────
Cada acción sensible (carga de archivos, edición de datos, aprobación de
usuarios, inicio de sesión) escribe un evento inmutable en `auditoria`.

Garantías:
  • Append-only en la capa de aplicación: este módulo NUNCA actualiza ni borra.
    En Postgres, además, un trigger rechaza UPDATE/DELETE (ver database.py).
  • Cadena hash: hash = SHA256(prev_hash + fila_canónica). Alterar o quitar una
    fila rompe la verificación a partir de ese punto (verify_chain).
  • Política log-and-continue: record_audit usa su PROPIA sesión y captura
    cualquier error, de modo que un fallo de auditoría jamás revierte ni rompe
    la acción principal que se estaba auditando.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AuditLog

log = logging.getLogger("protactics.audit")

# Hash de arranque de la cadena (no hay fila previa a la primera).
GENESIS = "0" * 64
# Clave arbitraria para serializar el cálculo de la cadena en Postgres.
_CHAIN_LOCK_KEY = 728345


def _ts(dt: Optional[datetime]) -> Optional[str]:
    """Normaliza un datetime a UTC naive con microsegundos.

    Hace que el hash sea estable entre dialectos: SQLite devuelve datetimes
    naive; Postgres (timestamptz) los devuelve aware. Normalizando a UTC sin
    tzinfo, la verificación recalcula el mismo string que se firmó al escribir.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def _canonical(value) -> str:
    """Serialización determinista (claves ordenadas) de los campos firmados."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      default=str, separators=(",", ":"))


def _fields(row) -> dict:
    """Campos que entran en el hash (orden irrelevante: _canonical ordena)."""
    return {
        "actor_user_id": row.actor_user_id,
        "actor_email":   row.actor_email,
        "accion":        row.accion,
        "entidad":       row.entidad,
        "entidad_id":    row.entidad_id,
        "puerto_id":     row.puerto_id,
        "detalle":       row.detalle,
        "ip":            row.ip,
        "user_agent":    row.user_agent,
        "creado_en":     _ts(row.creado_en),
    }


def compute_hash(prev_hash: Optional[str], fields: dict) -> str:
    return hashlib.sha256(((prev_hash or GENESIS) + _canonical(fields))
                          .encode("utf-8")).hexdigest()


def record_audit(*, accion: str, entidad: str, actor=None,
                 entidad_id=None, puerto_id: Optional[int] = None,
                 detalle: Optional[dict] = None, request=None,
                 actor_email: Optional[str] = None,
                 actor_user_id: Optional[int] = None) -> Optional[AuditLog]:
    """Registra un evento en la pista inmutable. Devuelve la fila o None si falló.

    `actor` (un User) tiene prioridad sobre actor_email/actor_user_id sueltos
    (útiles para login fallido, donde no hay objeto User autenticado).
    `request` (Request de FastAPI) aporta ip y user-agent.
    """
    try:
        if actor is not None:
            actor_user_id = getattr(actor, "id", None)
            actor_email = getattr(actor, "email", None)

        ip = user_agent = None
        if request is not None:
            ip = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        if entidad_id is not None:
            entidad_id = str(entidad_id)

        db: Session = SessionLocal()
        try:
            # Serializa el cálculo de la cadena entre escrituras concurrentes.
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(:k)"),
                           {"k": _CHAIN_LOCK_KEY})

            prev = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
            prev_hash = prev.hash if prev else None

            row = AuditLog(
                actor_user_id=actor_user_id, actor_email=actor_email,
                accion=accion, entidad=entidad, entidad_id=entidad_id,
                puerto_id=puerto_id, detalle=detalle, ip=ip, user_agent=user_agent,
                creado_en=datetime.utcnow(), prev_hash=prev_hash,
            )
            row.hash = compute_hash(prev_hash, _fields(row))
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            db.close()
    except Exception as e:  # log-and-continue: nunca rompe la acción principal
        log.error("Fallo al escribir auditoría (%s/%s): %s", accion, entidad, e)
        return None


def verify_chain(db: Session) -> dict:
    """Recorre la pista en orden y valida prev_hash + hash de cada fila.

    Devuelve {"ok": True, "count": n} si la cadena es íntegra, o
    {"ok": False, "broken_at": id, "count": n} en la primera fila alterada.
    """
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    prev_hash = None
    for r in rows:
        expected = compute_hash(prev_hash, _fields(r))
        if (r.prev_hash or None) != (prev_hash or None) or r.hash != expected:
            return {"ok": False, "broken_at": r.id, "count": len(rows)}
        prev_hash = r.hash
    return {"ok": True, "count": len(rows)}
