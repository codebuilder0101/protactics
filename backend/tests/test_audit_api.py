"""Endpoints de auditoría: /api/audit/verify y /api/audit (solo admin)."""
from conftest import standard_xlsx, login_client, XLSX_CT


def test_verify_ok_para_admin(client, admin):
    # Genera algo de actividad auditable y verifica la cadena.
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    r = client.get("/api/audit/verify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["count"] >= 1


def test_listado_devuelve_eventos(client, admin):
    # El registro del admin (bootstrap) no audita; un login sí genera evento.
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    r = client.get("/api/audit?limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 1
    assert {"accion", "entidad", "creado_en"} <= set(rows[0].keys())


def test_no_admin_recibe_403(client, admin):
    client.post("/api/auth/users",
                json={"email": "obs@test.co", "password": "observ1234",
                      "role": "observador", "puerto_id": 0})
    c = login_client("obs@test.co", "observ1234")
    assert c.get("/api/audit/verify").status_code == 403
    assert c.get("/api/audit").status_code == 403


def test_no_autenticado_recibe_401(client):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    assert c.get("/api/audit/verify").status_code == 401
