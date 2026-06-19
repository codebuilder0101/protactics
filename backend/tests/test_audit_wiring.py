"""Feature 8 — auditoría enganchada en login, carga, edición y aprobación."""
from fastapi.testclient import TestClient

import audit
import database
import main
from models import AuditLog
from conftest import standard_xlsx, login_client, XLSX_CT


def _audits(accion=None):
    db = database.SessionLocal()
    q = db.query(AuditLog)
    if accion:
        q = q.filter_by(accion=accion)
    rows = q.all()
    db.close()
    return rows


def test_login_exitoso_auditado(client, admin):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    assert r.status_code == 200
    assert any(a.accion == "login_success" for a in _audits())


def test_login_fallido_auditado_sin_sesion(client):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": "nadie@test.co", "password": "malisima"})
    assert r.status_code == 401
    fails = _audits("login_failure")
    assert len(fails) == 1
    assert fails[0].actor_email == "nadie@test.co"


def test_carga_auditada(feeder):
    b = standard_xlsx(["2026-04-05 10:00"])
    r = feeder.post("/upload/0/2026/4", files={"file": ("f.xlsx", b, XLSX_CT)})
    assert r.status_code == 200, r.text
    ups = [a for a in _audits("upload") if a.puerto_id == 0]
    assert ups and ups[0].entidad_id == "0/2026/4"


def test_edicion_disponibilidad_auditada(feeder):
    r = feeder.put("/disponibilidad/0/2026/4", json={"valor": 97.5})
    assert r.status_code == 200, r.text
    evs = _audits("edit_disponibilidad")
    assert evs and evs[0].detalle["despues"] == 97.5


def test_aprobacion_auditada(client, admin):
    c2 = TestClient(main.app)
    r = c2.post("/api/auth/register",
                json={"email": "pend@test.co", "password": "pending1234",
                      "role": "observador_global"})
    assert r.status_code == 200
    uid = r.json()["id"]
    r = client.post(f"/api/auth/users/{uid}/approve", json={})
    assert r.status_code == 200, r.text
    evs = _audits("approve_user")
    assert any(a.entidad_id == str(uid) for a in evs)


def test_cadena_integra_tras_actividad(feeder):
    feeder.post("/upload/0/2026/4",
                files={"file": ("f.xlsx", standard_xlsx(["2026-04-05 10:00"]), XLSX_CT)})
    db = database.SessionLocal()
    try:
        assert audit.verify_chain(db)["ok"] is True
    finally:
        db.close()


def test_fallo_de_auditoria_no_rompe_la_accion(feeder, monkeypatch):
    # Si la escritura de auditoría falla, la acción principal debe seguir OK
    # (política log-and-continue).
    def boom():
        raise RuntimeError("auditoría caída")
    monkeypatch.setattr(audit, "SessionLocal", boom)
    b = standard_xlsx(["2026-04-05 10:00"])
    r = feeder.post("/upload/0/2026/4", files={"file": ("f.xlsx", b, XLSX_CT)})
    assert r.status_code == 200
