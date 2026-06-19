"""Validación de período en carga DIRIGIDA: el archivo debe ser del mes elegido."""
from conftest import standard_xlsx, tcbuen_xlsx, XLSX_CT


def test_rechaza_mes_equivocado(feeder):
    # Archivo con datos de JUNIO 2026 cargado en ABRIL 2026 → 400 con mensaje claro.
    b = standard_xlsx(["2026-06-10 10:00", "2026-06-11 11:00"])
    r = feeder.post("/upload/0/2026/4", files={"file": ("f.xlsx", b, XLSX_CT)})
    assert r.status_code == 400
    assert "Junio 2026" in r.json()["detail"]


def test_rechaza_anio_equivocado(feeder):
    # Mismo mes pero año distinto (agosto 2025 cargado en agosto 2026) → 400.
    b = standard_xlsx(["2025-08-03 09:00", "2025-08-04 09:00"])
    r = feeder.post("/upload/0/2026/8", files={"file": ("f.xlsx", b, XLSX_CT)})
    assert r.status_code == 400
    assert "Agosto 2025" in r.json()["detail"]


def test_acepta_mes_correcto(feeder):
    b = standard_xlsx(["2026-04-05 10:00", "2026-04-06 11:00"])
    r = feeder.post("/upload/0/2026/4", files={"file": ("f.xlsx", b, XLSX_CT)})
    assert r.status_code == 200, r.text


def test_acepta_mes_dominante_con_pocas_filas_de_otro_mes(feeder):
    # Mayoría abril + una fila suelta de mayo → el período dominante es abril → OK.
    b = standard_xlsx(["2026-04-05 10:00", "2026-04-06 11:00",
                       "2026-04-07 12:00", "2026-05-01 09:00"])
    r = feeder.post("/upload/0/2026/4", files={"file": ("f.xlsx", b, XLSX_CT)})
    assert r.status_code == 200, r.text
