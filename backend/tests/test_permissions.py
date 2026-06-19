"""Matriz de permisos para los endpoints de carga (admin/feeder/observador)."""
from conftest import standard_xlsx, rapiscan_xlsx, login_client, XLSX_CT


def test_observador_no_puede_cargar(client, admin):
    client.post("/api/auth/users",
                json={"email": "obs@test.co", "password": "observ1234",
                      "role": "observador", "puerto_id": 0})
    c = login_client("obs@test.co", "observ1234")
    r = c.post("/upload/0/2026/4",
               files={"file": ("f.xlsx", standard_xlsx(["2026-04-05 10:00"]), XLSX_CT)})
    assert r.status_code == 403


def test_feeder_no_puede_cargar_otro_puerto(feeder):
    r = feeder.post("/upload/1/2026/4",
                    files={"file": ("f.xlsx", rapiscan_xlsx(["2026-04-05 10:00"]), XLSX_CT)})
    assert r.status_code == 403


def test_feeder_puede_cargar_su_puerto(feeder):
    r = feeder.post("/upload/0/2026/4",
                    files={"file": ("f.xlsx", standard_xlsx(["2026-04-05 10:00"]), XLSX_CT)})
    assert r.status_code == 200, r.text


def test_no_autenticado_rechazado(client):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    r = c.post("/upload/0/2026/4",
               files={"file": ("f.xlsx", standard_xlsx(["2026-04-05 10:00"]), XLSX_CT)})
    assert r.status_code == 401
