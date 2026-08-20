"""Matriz de permisos: carga de archivos y edición de disponibilidad."""
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


# ── Disponibilidad: dato de gestión, SOLO el administrador lo fija ──────────

def test_admin_puede_fijar_disponibilidad(client, admin):
    r = client.put("/disponibilidad/0/2026/4", json={"valor": 97.5})
    assert r.status_code == 200, r.text
    assert r.json()["valor"] == 97.5


def test_alimentador_no_puede_fijar_disponibilidad_de_su_puerto(feeder):
    """Cambio de regla: el alimentador carga XLS pero NO informa la cifra."""
    r = feeder.put("/disponibilidad/0/2026/4", json={"valor": 97.5})
    assert r.status_code == 403


def test_observador_no_puede_fijar_disponibilidad(client, admin):
    client.post("/api/auth/users",
                json={"email": "obsd@test.co", "password": "observ1234",
                      "role": "observador", "puerto_id": 0})
    c = login_client("obsd@test.co", "observ1234")
    r = c.put("/disponibilidad/0/2026/4", json={"valor": 97.5})
    assert r.status_code == 403


def test_observador_global_no_puede_fijar_disponibilidad(client, admin):
    client.post("/api/auth/users",
                json={"email": "glob@test.co", "password": "global1234",
                      "role": "observador_global"})
    c = login_client("glob@test.co", "global1234")
    r = c.put("/disponibilidad/0/2026/4", json={"valor": 97.5})
    assert r.status_code == 403


def test_no_autenticado_no_puede_fijar_disponibilidad(client):
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    r = c.put("/disponibilidad/0/2026/4", json={"valor": 97.5})
    assert r.status_code == 401


def test_lectura_de_disponibilidad_sigue_abierta_a_observadores(client, admin):
    """Restringir la ESCRITURA no debe cerrar la LECTURA a quien ve el puerto."""
    assert client.put("/disponibilidad/0/2026/4", json={"valor": 97.5}).status_code == 200
    client.post("/api/auth/users",
                json={"email": "obsr@test.co", "password": "observ1234",
                      "role": "observador", "puerto_id": 0})
    c = login_client("obsr@test.co", "observ1234")
    r = c.get("/disponibilidad/0")
    assert r.status_code == 200, r.text
    assert any(x["year"] == 2026 and x["mes"] == 4 and x["valor"] == 97.5 for x in r.json())


def test_admin_sigue_validando_el_rango(client, admin):
    assert client.put("/disponibilidad/0/2026/4", json={"valor": 150}).status_code == 400
    assert client.put("/disponibilidad/0/2026/4", json={"valor": -5}).status_code == 400
    assert client.put("/disponibilidad/0/2026/4", json={"valor": None}).status_code == 200
