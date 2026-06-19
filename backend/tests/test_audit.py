"""Feature 7 — auditoría inmutable: cadena hash, enlace y detección de manipulación."""
from sqlalchemy import text

import audit
import database
from models import AuditLog


def test_cadena_y_verificacion_ok(client):
    for i in range(5):
        assert audit.record_audit(accion="test", entidad="x", entidad_id=i) is not None

    db = database.SessionLocal()
    try:
        res = audit.verify_chain(db)
        assert res["ok"] is True and res["count"] == 5
        rows = db.query(AuditLog).order_by(AuditLog.id).all()
        assert rows[0].prev_hash is None          # génesis
        for prev, cur in zip(rows, rows[1:]):     # cada fila enlaza con la anterior
            assert cur.prev_hash == prev.hash
    finally:
        db.close()


def test_manipulacion_detectada(client):
    for i in range(3):
        audit.record_audit(accion="test", entidad="x", entidad_id=i)

    # En producción el trigger de Postgres impide este UPDATE; aquí (SQLite) lo
    # forzamos por SQL directo para comprobar que la cadena hash lo detecta.
    with database.engine.begin() as conn:
        conn.execute(text("UPDATE auditoria SET accion='HACKED' WHERE id=2"))

    db = database.SessionLocal()
    try:
        res = audit.verify_chain(db)
        assert res["ok"] is False and res["broken_at"] == 2
    finally:
        db.close()


def test_eliminacion_detectada(client):
    for i in range(4):
        audit.record_audit(accion="test", entidad="x", entidad_id=i)
    # Quitar una fila intermedia rompe el enlace prev_hash de la siguiente.
    with database.engine.begin() as conn:
        conn.execute(text("DELETE FROM auditoria WHERE id=2"))
    db = database.SessionLocal()
    try:
        assert audit.verify_chain(db)["ok"] is False
    finally:
        db.close()


def test_detalle_json_en_hash(client):
    a = audit.record_audit(accion="edit", entidad="disponibilidad",
                           detalle={"antes": 90.0, "despues": 95.0})
    assert a is not None and a.detalle == {"antes": 90.0, "despues": 95.0}
    db = database.SessionLocal()
    try:
        assert audit.verify_chain(db)["ok"] is True
    finally:
        db.close()
