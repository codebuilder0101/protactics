"""Pruebas del módulo de identificadores (funciones puras) + extracción sobre los
archivos REALES de `reference/`. No requieren base de datos."""
import os

import pytest

import identificadores as ID
import main


REF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "reference")


# ── ISO 6346 ────────────────────────────────────────────────
def test_iso6346_validos():
    # Contenedores reales tomados de los reportes; el dígito de control cuadra.
    for c in ("MSGU9035797", "MCAU6056629", "TEMU9222827", "SUDU8000156"):
        assert ID.validar_iso6346(c), c


def test_iso6346_digito_de_control_incorrecto():
    # Mismo prefijo/serie pero con el dígito de control cambiado → inválido.
    assert not ID.validar_iso6346("MSGU9035790")
    assert not ID.validar_iso6346("MSGU9035798")


def test_iso6346_formato_invalido():
    assert not ID.validar_iso6346("ABC123")          # muy corto
    assert not ID.validar_iso6346("12345678901")     # sin letras
    assert not ID.validar_iso6346("")


def test_normalizar():
    assert ID.normalizar(" msgu 9035797 ") == "MSGU9035797"
    assert ID.normalizar("tlk-300") == "TLK300"
    assert ID.normalizar(None) == ""


def test_separar_multivalor():
    # TCBUEN trae varios contenedores por celda, separados por coma.
    out = ID.separar_contenedores("MRKU7253344, HASU1234567")
    assert out == ["MRKU7253344", "HASU1234567"]
    assert ID.separar_contenedores("") == []
    # No duplica.
    assert ID.separar_contenedores("ABCU1111111, ABCU1111111") == ["ABCU1111111"]


# ── Clasificación de columnas ───────────────────────────────
def test_clasificar_columnas_antioquia():
    header = ["Selección", "Miniatura", "ID del Contenedor",
              "País de la Matrícula Trasera", "Matrícula Trasera",
              "Matrícula Delantera", "Fecha de creación", "Sin ID de Contenedor"]
    cols = ID.clasificar_columnas(header)
    assert cols["contenedor"] == [2]                 # NO el 7 ("Sin ID de Contenedor")
    assert (4, "trasera") in cols["placa"]
    assert (5, "delantera") in cols["placa"]
    # "País de la Matrícula" NO es placa (es un país).
    assert all(i != 3 for i, _ in cols["placa"])
    assert cols["fecha"] == 6


def test_clasificar_columnas_rapiscan():
    header = ["Scan Date & Time", "Filename", "User Name", "Inspect Result",
              "Container 1", "Container 2", "PLACA"]
    cols = ID.clasificar_columnas(header)
    assert cols["contenedor"] == [4, 5]
    assert (6, "placa") in cols["placa"]
    assert cols["fecha"] == 0


def test_clasificar_resumen_no_es_detalle():
    # Cabecera de reporte-resumen (estadística diaria): sin contenedor ni placa.
    header = ["Equipo", "REFERENCIA", "FECHA", "Total escaneados",
              "Sin Imagen de RX", "Sin ID de Contenedor", "comentarios"]
    cols = ID.clasificar_columnas(header)
    assert cols["contenedor"] == []
    assert cols["placa"] == []


# ── Extracción de filas (sintética) ─────────────────────────
def test_extraer_filas_sintetica():
    rows = [
        ["ID del Contenedor", "Matrícula Delantera", "Fecha de creación", "Nombre de Usuario"],
        ["MSGU9035797", "TLK300", "2026-06-16 12:20:10", "Humberto"],
        ["MRKU7253344, HASU1234567", "TT339", "2026-06-17 23:53:28", "Anderson"],
        [None, None, None, None],                    # fila vacía → se omite
    ]
    filas = ID.extraer_filas(rows, 2026, 6)
    assert len(filas) == 2
    assert filas[0]["contenedores"] == ["MSGU9035797"]
    assert filas[0]["dia"] == 16
    assert filas[0]["fecha_hora"].hour == 12
    assert ("TLK300", "delantera") in filas[0]["placas"]
    # Multivalor → dos contenedores.
    assert filas[1]["contenedores"] == ["MRKU7253344", "HASU1234567"]
    # `datos` conserva todas las columnas de texto.
    assert filas[0]["datos"]["Nombre de Usuario"] == "Humberto"


def test_extraer_filas_resumen_devuelve_vacio():
    rows = [
        ["Equipo", "REFERENCIA", "FECHA", "Total escaneados", "Sin ID de Contenedor"],
        ["RAPISCAN", "P60", "2026-06-01 00:00:00", "324", "0"],
    ]
    assert ID.extraer_filas(rows, 2026, 6) == []


# ── Archivos REALES de reference/ ───────────────────────────
# Los 7 reportes traen detalle por escaneo. Los libros de Antioquia E2,
# Barranquilla y Santa Marta tienen DOS hojas (una de estadística agregada y otra
# de detalle "Imágenes de Escaneo"); read_excel_rows elige la de detalle.
TODOS = (
    "REPORTE16062026ESCANER1PTOANTIOQUIA.xlsx",
    "REPORTE16062026ESCANER2PTOANTIOQUIA.xlsx",
    "REPORTE16062026ESCANERPTOAGUADULCE.xlsx",
    "REPORTE16062026ESCANERPTOBARRANQUILLA.xlsx",
    "REPORTE16062026ESCANERPTOSANTAMARTA.xlsx",
    "REPORTE16062026ESCANERPTOSPB.xlsx",
    "REPORTE16062026ESCANERPTOTCBUEN.xlsx",
)


def _leer(nombre):
    path = os.path.join(REF_DIR, nombre)
    if not os.path.exists(path):
        pytest.skip(f"archivo de referencia ausente: {nombre}")
    with open(path, "rb") as fh:
        return main.read_excel_rows(fh.read(), nombre)


@pytest.mark.parametrize("nombre", TODOS)
def test_archivos_reales_extraen_contenedores_validos(nombre):
    rows = _leer(nombre)
    filas = ID.extraer_filas(rows, 2026, 6)
    assert filas, f"{nombre} debería producir filas de detalle"
    contenedores = [c for f in filas for c in f["contenedores"]]
    validos = [c for c in contenedores if ID.validar_iso6346(c)]
    # La gran mayoría de los contenedores reales cumplen ISO 6346 (el OCR del
    # escáner es fiable); exigimos al menos un puñado válido por archivo.
    assert len(validos) >= 10, f"{nombre}: solo {len(validos)} contenedores válidos"
