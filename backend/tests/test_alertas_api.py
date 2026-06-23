"""API de alertas: listado, filtros, permisos, ack/resolve, recálculo, migración."""
from datetime import datetime

import database
from models import Alerta, EscaneosDiarios
from conftest import login_client


# ── Helpers ─────────────────────────────────────────────────
def _add_alerta(puerto_id, tipo, severidad="warning", estado="open",
                year=2025, mes=3, dia=None):
    db = database.SessionLocal()
    try:
        a = Alerta(puerto_id=puerto_id, tipo=tipo, severidad=severidad,
                   mensaje="prueba", estado=estado, year=year, mes=mes, dia=dia,
                   creada_en=datetime.utcnow())
        db.add(a)
        db.commit()
        db.refresh(a)
        return a.id
    finally:
        db.close()


def _seed_dias(puerto_id, year, mes, dias, total=100):
    db = database.SessionLocal()
    try:
        for d in dias:
            db.add(EscaneosDiarios(puerto_id=puerto_id, year=year, mes=mes,
                                   dia=d, total=total))
        db.commit()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
#  Migración del CHECK (regresión)
# ══════════════════════════════════════════════════════════════
def test_tipos_de_anomalia_pasan_el_check(client):
    # Insertar cada tipo nuevo no debe violar el CHECK ampliado de alertas.tipo.
    from models import ALERTA_TIPOS
    for t in ALERTA_TIPOS:
        _add_alerta(0, t)
    db = database.SessionLocal()
    try:
        assert db.query(Alerta).count() == len(ALERTA_TIPOS)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
#  Listado y filtros
# ══════════════════════════════════════════════════════════════
def test_listar_y_filtrar_por_estado(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    _add_alerta(0, "sla_breach", estado="open")
    _add_alerta(0, "zero_day", estado="resolved")
    abiertas = client.get("/alertas?estado=open").json()
    assert len(abiertas) == 1 and abiertas[0]["tipo"] == "sla_breach"


def test_orden_por_severidad(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    _add_alerta(0, "zero_day", severidad="warning")
    _add_alerta(0, "sla_breach", severidad="critical")
    rows = client.get("/alertas").json()
    assert rows[0]["severidad"] == "critical"   # critical primero


def test_resumen_cuenta_por_puerto(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    _add_alerta(0, "sla_breach", severidad="critical")
    _add_alerta(0, "zero_day", severidad="warning")
    _add_alerta(0, "operator_drop", severidad="warning", estado="resolved")  # no cuenta
    res = client.get("/alertas/resumen").json()
    assert res["0"]["critical"] == 1 and res["0"]["warning"] == 1


def test_observador_de_otro_puerto_no_ve_alertas(client, admin):
    _add_alerta(0, "sla_breach")
    client.post("/api/auth/users", json={"email": "obs@test.co", "password": "observ1234",
                "role": "observador", "puerto_id": 1})
    c = login_client("obs@test.co", "observ1234")
    assert c.get("/alertas").json() == []
    assert c.get("/alertas?puerto_id=0").status_code == 403


# ══════════════════════════════════════════════════════════════
#  Ack / Resolve
# ══════════════════════════════════════════════════════════════
def test_ack_y_resolve_admin(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    aid = _add_alerta(0, "sla_breach")
    assert client.post(f"/alertas/{aid}/ack").json()["estado"] == "acknowledged"
    assert client.post(f"/alertas/{aid}/resolve").json()["estado"] == "resolved"
    eventos = client.get("/api/audit?limit=20").json()
    assert any(e["accion"] == "resolve_alerta" for e in eventos)


def test_feeder_del_puerto_puede_gestionar(client, admin, feeder):
    aid = _add_alerta(0, "sla_breach")             # feeder es del puerto 0
    assert feeder.post(f"/alertas/{aid}/ack").status_code == 200


def test_observador_no_puede_gestionar(client, admin):
    aid = _add_alerta(0, "sla_breach")
    client.post("/api/auth/users", json={"email": "obs0@test.co", "password": "observ1234",
                "role": "observador", "puerto_id": 0})
    c = login_client("obs0@test.co", "observ1234")
    assert c.post(f"/alertas/{aid}/ack").status_code == 403


def test_resolve_es_idempotente(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    aid = _add_alerta(0, "sla_breach")
    client.post(f"/alertas/{aid}/resolve")
    r = client.post(f"/alertas/{aid}/resolve")     # repetir no falla
    assert r.status_code == 200 and r.json()["estado"] == "resolved"


# ══════════════════════════════════════════════════════════════
#  Recálculo
# ══════════════════════════════════════════════════════════════
def test_recalcular_admin_genera_alertas(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    _seed_dias(0, 2025, 3, range(1, 25))           # 24/31 < 95 → incumple
    r = client.post("/alertas/recalcular/0/2025/3")
    assert r.status_code == 200 and r.json()["alertas_abiertas"] >= 1


def test_recalcular_no_admin_403(client, admin, feeder):
    assert feeder.post("/alertas/recalcular/0/2025/3").status_code == 403


def test_no_autenticado_401(client):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    assert c.get("/alertas").status_code == 401
    assert c.get("/alertas/resumen").status_code == 401
