"""Feature 1 — esquema: constraints CHECK y UNIQUE de las tablas nuevas."""
import pytest
from sqlalchemy.exc import IntegrityError

import database
from models import Alerta, SLA, Infraccion, AuditLog


def test_check_constraint_rechaza_severidad_invalida(client):
    db = database.SessionLocal()
    try:
        db.add(Alerta(puerto_id=0, tipo="sla_breach", severidad="bogus", mensaje="x"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback(); db.close()


def test_check_constraint_rechaza_tipo_invalido(client):
    db = database.SessionLocal()
    try:
        db.add(Alerta(puerto_id=0, tipo="no_existe", severidad="info", mensaje="x"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback(); db.close()


def test_check_constraint_acepta_valores_validos(client):
    db = database.SessionLocal()
    try:
        db.add(Alerta(puerto_id=0, tipo="availability_low", severidad="critical",
                      mensaje="disponibilidad baja", estado="open",
                      payload={"valor": 88.0}))
        db.commit()
        a = db.query(Alerta).first()
        assert a.payload == {"valor": 88.0}      # JSON round-trip
    finally:
        db.close()


def test_unique_sla_puerto_metrica(client):
    db = database.SessionLocal()
    try:
        db.add(SLA(puerto_id=0, metrica="availability", umbral=95.0))
        db.commit()
        db.add(SLA(puerto_id=0, metrica="availability", umbral=90.0))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback(); db.close()


def test_infraccion_round_trip(client):
    db = database.SessionLocal()
    try:
        sla = SLA(puerto_id=0, metrica="min_daily_scans", umbral=50.0, periodo="diario")
        db.add(sla); db.commit()
        db.add(Infraccion(puerto_id=0, sla_id=sla.id, year=2026, mes=4, dia=3,
                          valor_observado=40.0, valor_esperado=50.0))
        db.commit()
        inf = db.query(Infraccion).first()
        assert (inf.year, inf.mes, inf.dia) == (2026, 4, 3)
        assert inf.valor_observado == 40.0
    finally:
        db.close()
