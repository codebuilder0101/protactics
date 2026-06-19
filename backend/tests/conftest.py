"""Configuración de pruebas PROTACTICS.

Las pruebas se ejecutan contra SQLite (no hay Postgres en CI local). El código de
producción es Postgres; las piezas exclusivas de Postgres (trigger de
inmutabilidad de auditoría, JSONB, TIMESTAMPTZ) están protegidas por dialecto y
se documentan en sus respectivas pruebas.

IMPORTANTE: las variables de entorno se fijan ANTES de importar database/main,
porque el engine de SQLAlchemy se crea al importar el módulo.
"""
import io
import os
import sys

# Permite importar los módulos del backend (database, main, models, ...).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Entorno de prueba (debe ir antes de importar la app) ──────────
os.environ["DATABASE_URL"] = "sqlite:///./_test_protactics.db"
os.environ["SEED_DEMO_USERS"] = "false"
os.environ["REGISTRATION_ENABLED"] = "true"

import openpyxl  # noqa: E402
import pytest     # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

import database   # noqa: E402
import main       # noqa: E402
from models import Base  # noqa: E402


# ══════════════════════════════════════════════════════════════
#  Constructores de Excel de muestra (uno por formato)
# ══════════════════════════════════════════════════════════════
def make_xlsx(rows: list) -> bytes:
    """Crea un .xlsx en memoria a partir de una lista de filas (la 1ª es header)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def standard_xlsx(dates: list, operador="Juan") -> bytes:
    """Formato Standard/Miniatura: una fila por escaneo con 'Fecha de creación'."""
    rows = [["Fecha de creación", "Nombre de Usuario", "Estado"]]
    for d in dates:
        rows.append([d, operador, "Completado"])
    return make_xlsx(rows)


def tcbuen_xlsx(dates: list, estado="100", operador="Ana") -> bytes:
    """Formato TCBUEN: incluye 'Estado de flujo de trabajo' con estado numérico."""
    rows = [["Fecha de creación", "Nombre de Usuario", "Estado de flujo de trabajo"]]
    for d in dates:
        rows.append([d, operador, estado])
    return make_xlsx(rows)


def rapiscan_xlsx(dates: list, operador="Op1") -> bytes:
    """Formato Rapiscan (detalle): encabezado con 'Scan Date & Time' y 'User Name'."""
    rows = [["Reporte de Escaneos Individuales", None, None],
            ["Scan Date & Time", "User Name", "Filename"]]
    for d in dates:
        rows.append([d, operador, "img.jpg"])
    return make_xlsx(rows)


# ══════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════
@pytest.fixture()
def client():
    """Cliente con esquema LIMPIO por prueba (drop+create+seed puertos)."""
    Base.metadata.drop_all(bind=database.engine)
    database.init_db()
    with TestClient(main.app) as c:
        yield c
    Base.metadata.drop_all(bind=database.engine)


@pytest.fixture()
def admin(client):
    """Primer usuario = admin auto-aprobado y con sesión iniciada en `client`."""
    r = client.post("/api/auth/register",
                    json={"email": "admin@test.co", "password": "admin1234",
                          "nombre": "Admin"})
    assert r.status_code == 200, r.text
    return r.json()


def login_client(email: str, password: str) -> TestClient:
    """Devuelve un TestClient independiente autenticado con esas credenciales."""
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def feeder(client, admin):
    """Crea un alimentador del puerto 0 y devuelve un cliente autenticado como él."""
    r = client.post("/api/auth/users",
                    json={"email": "feeder@test.co", "password": "feeder1234",
                          "nombre": "Feeder", "role": "alimentador", "puerto_id": 0})
    assert r.status_code == 200, r.text
    return login_client("feeder@test.co", "feeder1234")
