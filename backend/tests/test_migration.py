"""Feature 2 — migraciones: idempotencia y upgrade desde esquema legacy."""
from sqlalchemy import inspect, text

import database
from models import EscaneosDiarios

NEW_TABLES = ("alertas", "sla", "infracciones", "auditoria")


def test_init_db_idempotente(client):
    # Ejecutar la migración dos veces no debe fallar ni duplicar nada.
    database.init_db()
    database.init_db()
    tables = inspect(database.engine).get_table_names()
    for t in NEW_TABLES:
        assert t in tables


def test_upgrade_legacy_preserva_datos(client):
    db = database.SessionLocal()
    db.add(EscaneosDiarios(puerto_id=0, year=2026, mes=4, dia=1, total=10))
    db.commit()
    antes = db.query(EscaneosDiarios).count()
    db.close()

    # Simular una instalación previa SIN la tabla nueva de auditoría.
    with database.engine.begin() as conn:
        conn.execute(text("DROP TABLE auditoria"))
    assert "auditoria" not in inspect(database.engine).get_table_names()

    # La migración la recrea sin tocar los datos existentes.
    database.init_db()
    assert "auditoria" in inspect(database.engine).get_table_names()

    db = database.SessionLocal()
    assert db.query(EscaneosDiarios).count() == antes
    db.close()
