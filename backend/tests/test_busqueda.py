"""Búsqueda y trazabilidad de contenedores/vehículos: ingesta del detalle,
endpoints de búsqueda/trayecto, permisos por puerto, idempotencia y auditoría."""
import os

import pytest

import database
import identificadores as ID
import main
from models import EscaneoFila, IndiceIdentificador

REF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "reference")
REF_FILE = "REPORTE16062026ESCANERPTOTCBUEN.xlsx"


def _detalle(contenedor="MSGU9035797", placa="TLK300",
             fecha="2026-06-16 12:20:10", extra=None):
    rows = [
        ["ID del Contenedor", "Matrícula Delantera", "Fecha de creación",
         "Nombre de Usuario", "Estado de flujo de trabajo"],
        [contenedor, placa, fecha, "Humberto", "100"],
    ]
    if extra:
        rows.extend(extra)
    return rows


def _guardar(puerto_id, rows, year=2026, mes=6, filename="rep.xlsx", formato="tcbuen"):
    db = database.SessionLocal()
    try:
        return main.guardar_detalle(db, puerto_id, year, mes, rows, filename, formato)
    finally:
        db.close()


def _count(model, **kw):
    db = database.SessionLocal()
    try:
        return db.query(model).filter_by(**kw).count() if kw else db.query(model).count()
    finally:
        db.close()


# ── Ingesta ─────────────────────────────────────────────────
def test_ingesta_guarda_detalle_e_indice(client):
    rows = _detalle(extra=[["MRKU7253344, HASU1234567", "TT339",
                            "2026-06-17 23:53:28", "Anderson", "100"]])
    n = _guardar(0, rows)
    assert n == 2
    assert _count(EscaneoFila, puerto_id=0) == 2
    # 3 contenedores (MSGU, MRKU, HASU) + 2 placas (TLK300, TT339).
    assert _count(IndiceIdentificador, tipo="contenedor") == 3
    assert _count(IndiceIdentificador, tipo="placa") == 2


def test_ingesta_resumen_no_guarda_nada(client):
    rows = [["Equipo", "FECHA", "Total escaneados", "Sin ID de Contenedor"],
            ["RAPISCAN", "2026-06-01 00:00:00", "324", "0"]]
    assert _guardar(4, rows) == 0
    assert _count(EscaneoFila) == 0


def test_ingesta_idempotente(client):
    rows = _detalle()
    _guardar(0, rows)
    _guardar(0, rows)                                   # recarga del mismo día
    assert _count(EscaneoFila, puerto_id=0) == 1
    assert _count(IndiceIdentificador, tipo="contenedor", valor="MSGU9035797") == 1


# ── Búsqueda (API) ──────────────────────────────────────────
def test_buscar_contenedor(client, admin):
    _guardar(0, _detalle())
    r = client.get("/buscar?q=MSGU9035797")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    res = body["resultados"][0]
    assert res["valor"] == "MSGU9035797" and res["puerto_id"] == 0
    assert res["valido"] is True


def test_buscar_normaliza_la_consulta(client, admin):
    _guardar(0, _detalle())
    # minúsculas + espacios → debe encontrar igual
    assert client.get("/buscar?q=msgu 9035797").json()["total"] == 1


def test_buscar_minimo_3_caracteres(client, admin):
    assert client.get("/buscar?q=ab").status_code == 400


def test_buscar_por_placa(client, admin):
    _guardar(0, _detalle())
    body = client.get("/buscar?q=TLK300&tipo=placa").json()
    assert body["total"] == 1 and body["resultados"][0]["tipo"] == "placa"


# ── Trayecto / itinerario ───────────────────────────────────
def test_trayecto_cruza_dos_puertos(client, admin):
    _guardar(0, _detalle(fecha="2026-06-16 08:00:00"))   # Buenaventura primero
    _guardar(2, _detalle(fecha="2026-06-18 10:00:00"))   # TCBUEN después
    body = client.get("/contenedor/MSGU9035797/trayecto").json()
    assert body["valido"] is True
    assert [p["puerto_id"] for p in body["puertos"]] == [0, 2]   # orden cronológico
    assert len(body["pasos"]) == 2
    # Cobertura: los puertos sin detalle aparecen como no rastreables.
    sin = {p["puerto_id"] for p in body["cobertura"]["puertos_sin_detalle"]}
    assert 5 in sin                                       # Barranquilla, sin detalle


# ── Permisos ────────────────────────────────────────────────
def test_alimentador_solo_ve_su_puerto(client, admin, feeder):
    _guardar(0, _detalle())                              # puerto del feeder
    _guardar(2, _detalle())                              # puerto ajeno
    # admin ve los dos
    assert client.get("/buscar?q=MSGU9035797").json()["total"] == 2
    # feeder (puerto 0) solo ve el suyo
    assert feeder.get("/buscar?q=MSGU9035797").json()["total"] == 1
    # y su trayecto no revela el puerto ajeno
    tray = feeder.get("/contenedor/MSGU9035797/trayecto").json()
    assert [p["puerto_id"] for p in tray["puertos"]] == [0]


def test_busqueda_sin_sesion_401(client):
    assert client.get("/buscar?q=MSGU9035797").status_code == 401


# ── Ficha de escaneo ────────────────────────────────────────
def test_escaneo_detalle_devuelve_todas_las_columnas(client, admin):
    _guardar(0, _detalle())
    fid = client.get("/buscar?q=MSGU9035797").json()["resultados"][0]["fila_id"]
    body = client.get(f"/escaneo/{fid}").json()
    assert body["datos"]["Nombre de Usuario"] == "Humberto"
    assert body["datos"]["Estado de flujo de trabajo"] == "100"
    assert "MSGU9035797" in body["contenedores"]
    assert any(p["valor"] == "TLK300" for p in body["placas"])


# ── Auditoría ───────────────────────────────────────────────
def test_busqueda_se_audita(client, admin):
    _guardar(0, _detalle())
    client.get("/buscar?q=MSGU9035797")
    eventos = client.get("/api/audit?limit=20").json()
    assert any(e["accion"] == "buscar_identificador" for e in eventos)
    assert client.get("/api/audit/verify").json()["ok"] is True


# ── Extremo a extremo con un archivo REAL ───────────────────
def test_e2e_archivo_real(client, admin):
    """Ingesta un reporte real → busca un contenedor real → trayecto → ficha,
    todo por el camino HTTP. Guarda la cadena completa sobre datos reales."""
    path = os.path.join(REF_DIR, REF_FILE)
    if not os.path.exists(path):
        pytest.skip("archivo de referencia ausente")
    with open(path, "rb") as fh:
        rows = main.read_excel_rows(fh.read(), REF_FILE)

    # Ingesta directa (puerto 2 = TCBUEN) y elige un contenedor ISO real del archivo.
    main.guardar_detalle(database.SessionLocal(), 2, 2026, 6, rows, REF_FILE, "tcbuen")
    cont = next(c for f in ID.extraer_filas(rows, 2026, 6)
                for c in f["contenedores"] if ID.validar_iso6346(c))

    body = client.get("/buscar?q=" + cont).json()
    assert body["total"] >= 1
    fila_id = body["resultados"][0]["fila_id"]

    tray = client.get(f"/contenedor/{cont}/trayecto").json()
    assert tray["valido"] is True
    assert any(p["puerto_id"] == 2 for p in tray["puertos"])

    ficha = client.get(f"/escaneo/{fila_id}").json()
    assert cont in ficha["contenedores"]
    assert ficha["datos"]            # conserva todas las columnas del Excel
