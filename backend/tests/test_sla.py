"""Motor de SLA: meta efectiva, evaluación, infracciones, racha y API."""
from datetime import date

import database
import sla as sla_engine
from models import EscaneosDiarios, Infraccion, Alerta, SLA, VentanaMantenimiento
from conftest import login_client


# ── Helpers ─────────────────────────────────────────────────
def _seed_dias(puerto_id, year, mes, dias, total=100):
    db = database.SessionLocal()
    try:
        for d in dias:
            db.add(EscaneosDiarios(puerto_id=puerto_id, year=year, mes=mes,
                                   dia=d, total=total))
        db.commit()
    finally:
        db.close()


def _add_ventana(puerto_id, ini, fin):
    db = database.SessionLocal()
    try:
        db.add(VentanaMantenimiento(puerto_id=puerto_id, tipo="programado",
                                    fecha_inicio=ini, fecha_fin=fin))
        db.commit()
    finally:
        db.close()


def _evaluar_mes(puerto_id, year, mes):
    db = database.SessionLocal()
    try:
        info = sla_engine.evaluar_mes(db, puerto_id, year, mes)
        db.commit()
        return info
    finally:
        db.close()


def _count(model, **kw):
    db = database.SessionLocal()
    try:
        return db.query(model).filter_by(**kw).count()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
#  Meta efectiva
# ══════════════════════════════════════════════════════════════
def test_meta_global_por_defecto(client):
    db = database.SessionLocal()
    try:
        m = sla_engine.meta_efectiva(db, 0)
        assert m is not None and m.umbral == 95.0 and m.puerto_id is None
    finally:
        db.close()


def test_meta_propia_sobreescribe_global(client):
    db = database.SessionLocal()
    try:
        db.add(SLA(puerto_id=0, metrica="availability", umbral=90.0,
                   periodo="mensual", activo=True))
        db.commit()
        m = sla_engine.meta_efectiva(db, 0)
        assert m.umbral == 90.0 and m.puerto_id == 0
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
#  Evaluación
# ══════════════════════════════════════════════════════════════
def test_incumplimiento_registra_infraccion_y_alerta(client):
    _seed_dias(0, 2025, 3, range(1, 25))          # 24/31 ≈ 77% < 95
    info = _evaluar_mes(0, 2025, 3)
    assert info["estado"] == "INCUMPLE"
    assert _count(Infraccion, puerto_id=0, year=2025, mes=3) == 1
    assert _count(Alerta, puerto_id=0, tipo="sla_breach", estado="open") == 1


def test_cumplimiento_no_registra_infraccion(client):
    _seed_dias(0, 2025, 3, range(1, 32))          # 31/31 = 100% ≥ 95
    info = _evaluar_mes(0, 2025, 3)
    assert info["estado"] == "CUMPLE"
    assert _count(Infraccion, puerto_id=0, year=2025, mes=3) == 0


def test_mantenimiento_rescata_el_sla(client):
    _seed_dias(0, 2025, 3, range(1, 25))          # 24 días activos
    _add_ventana(0, date(2025, 3, 25), date(2025, 3, 31))  # excluye 25..31
    info = _evaluar_mes(0, 2025, 3)
    # elegibles = 1..24 (24), activos = 24 → 100% → CUMPLE
    assert info["estado"] == "CUMPLE"
    assert _count(Infraccion, puerto_id=0, year=2025, mes=3) == 0


def test_idempotencia_no_duplica(client):
    _seed_dias(0, 2025, 3, range(1, 25))
    _evaluar_mes(0, 2025, 3)
    _evaluar_mes(0, 2025, 3)
    assert _count(Infraccion, puerto_id=0, year=2025, mes=3) == 1
    assert _count(Alerta, puerto_id=0, tipo="sla_breach", estado="open") == 1


def test_correccion_resuelve_infraccion_y_alerta(client):
    _seed_dias(0, 2025, 3, range(1, 25))
    _evaluar_mes(0, 2025, 3)
    assert _count(Alerta, puerto_id=0, tipo="sla_breach", estado="open") == 1
    # completar el mes → cumple
    _seed_dias(0, 2025, 3, range(25, 32))
    _evaluar_mes(0, 2025, 3)
    assert _count(Infraccion, puerto_id=0, year=2025, mes=3) == 0
    assert _count(Alerta, puerto_id=0, tipo="sla_breach", estado="open") == 0


# ══════════════════════════════════════════════════════════════
#  Racha y meses faltantes
# ══════════════════════════════════════════════════════════════
def test_racha_tres_meses_consecutivos(client):
    # marzo/abril/mayo 2026 por debajo de la meta; junio (en curso) sin datos
    for m in (3, 4, 5):
        _seed_dias(0, 2026, m, range(1, 16))      # ~50% < 95
    db = database.SessionLocal()
    try:
        res = sla_engine.evaluar_puerto(db, 0)
    finally:
        db.close()
    assert res["racha"] == 3
    # el incumplimiento de la racha (≥3) escala a critical
    assert _count(Alerta, puerto_id=0, tipo="sla_breach", severidad="critical",
                  estado="open") >= 1


def test_mes_que_cumple_reinicia_racha(client):
    _seed_dias(0, 2026, 3, range(1, 16))          # incumple
    _seed_dias(0, 2026, 4, range(1, 31))          # cumple (30/30)
    _seed_dias(0, 2026, 5, range(1, 16))          # incumple
    db = database.SessionLocal()
    try:
        res = sla_engine.evaluar_puerto(db, 0)
    finally:
        db.close()
    assert res["racha"] == 1                       # solo mayo cuenta


def test_mes_faltante_genera_no_upload(client):
    _seed_dias(0, 2025, 1, range(1, 32))          # enero con datos
    _seed_dias(0, 2025, 3, range(1, 32))          # marzo con datos
    info = _evaluar_mes(0, 2025, 2)               # febrero vacío
    assert info["estado"] == "INCUMPLE"
    assert _count(Alerta, puerto_id=0, tipo="no_upload", mes=2, estado="open") == 1


def test_mes_faltante_en_mantenimiento_no_alerta(client):
    _seed_dias(0, 2025, 1, range(1, 32))
    _seed_dias(0, 2025, 3, range(1, 32))
    _add_ventana(0, date(2025, 2, 1), date(2025, 2, 28))   # febrero entero
    info = _evaluar_mes(0, 2025, 2)
    assert info["estado"] == "EN_MANTENIMIENTO"
    assert _count(Alerta, puerto_id=0, tipo="no_upload", mes=2, estado="open") == 0


# ══════════════════════════════════════════════════════════════
#  API
# ══════════════════════════════════════════════════════════════
def test_set_sla_puerto_admin(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    r = client.put("/sla/0", json={"umbral": 92.0})
    assert r.status_code == 200 and r.json()["umbral"] == 92.0
    est = client.get("/sla/0/estado").json()
    assert est["umbral"] == 92.0 and est["origen"] == "puerto"


def test_set_sla_umbral_invalido(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    assert client.put("/sla/0", json={"umbral": 150}).status_code == 422


def test_set_sla_no_admin_403(client, admin, feeder):
    assert feeder.put("/sla/0", json={"umbral": 90}).status_code == 403


def test_set_sla_audita(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    client.put("/sla/0", json={"umbral": 93.0})
    eventos = client.get("/api/audit?limit=20").json()
    assert any(e["accion"] == "edit_sla" for e in eventos)
    assert client.get("/api/audit/verify").json()["ok"] is True
