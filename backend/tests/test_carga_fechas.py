"""Correcciones de carga que destaparon los archivos reales de julio:
  • period_from_filename entiende fechas con nombre de mes ("1-jul-26").
  • alias de enrutamiento SMR/SPIA/BAQ/TC Buen.
  • anclaje de día cuando el contenido trae la fecha volteada/US (caso SPB).
"""
import main
import database
from database import PUERTOS_SEED
from routing import route_file
from parsers.dates import period_from_filename
from models import EscaneosDiarios
from conftest import standard_xlsx, XLSX_CT


# ── period_from_filename ────────────────────────────────────
def test_periodo_nombre_con_mes_texto():
    assert period_from_filename("Informe de Pto. SPB 1-jul-26.xlsx") == (2026, 7, 1)
    assert period_from_filename("escaneos de Pto. BAQ. 02-jul-2026.xls") == (2026, 7, 2)
    # El "#2-376" (nº de escáner) no se confunde con una fecha.
    assert period_from_filename(
        "Informe de Pto. Ant. escaner #2-376 2-jul-26.xlsx") == (2026, 7, 2)


def test_periodo_nombre_numerico_sigue_funcionando():
    assert period_from_filename("SPR Buenaventura 05-04-2026.xlsx") == (2026, 4, 5)


def test_periodo_nombre_sin_fecha_es_none():
    assert period_from_filename("TCBUEN reporte de julio.xlsx") is None


# ── Alias de enrutamiento ───────────────────────────────────
def test_alias_de_puerto_en_nombre():
    casos = [
        ("Informe de Pto. SMR 1-jul-26.xlsx", 6),      # Santa Marta
        ("escaneos de Pto. BAQ. 01-jul-2026.xlsx", 5),  # Barranquilla
        ("Informe de Pto. SPIA 1-jul-26.xlsx", 1),      # Aguadulce
        ("Informe de TC Buen 1-jul-26.xlsx", 2),        # TCBUEN
    ]
    for name, pid in casos:
        rows = main.read_excel_rows(standard_xlsx(["2026-07-01 10:00"]), name)
        d = route_file(rows, name, PUERTOS_SEED)
        assert d["puerto_id"] == pid, f"{name} -> {d['puerto_id']} (esperado {pid})"


# ── Anclaje de día por fecha volteada (caso SPB) ────────────
def _dias(puerto_id, year, mes):
    db = database.SessionLocal()
    try:
        return {e.dia: e.total for e in db.query(EscaneosDiarios)
                .filter_by(puerto_id=puerto_id, year=year, mes=mes).all()}
    finally:
        db.close()


def test_ancla_dia_cuando_contenido_esta_volteado(client, admin):
    # Contenido en enero (fecha US/volteada); el nombre dice 1-jul → debe anclar
    # todo a julio, día 1 (no enero día 7).
    b = standard_xlsx(["2026-01-07 10:00", "2026-01-07 11:00", "2026-01-07 12:00"])
    name = "Informe de Pto. SPB 1-jul-2026.xlsx"
    r = client.post("/upload/0/2026/7", files={"file": (name, b, XLSX_CT)})
    assert r.status_code == 200, r.text
    assert _dias(0, 2026, 7) == {1: 3}


def test_no_ancla_cuando_contenido_coincide(client, admin):
    # Contenido en julio coherente con el nombre → se conserva el día real de cada
    # fila (no se colapsa todo al día del nombre).
    b = standard_xlsx(["2026-07-01 10:00", "2026-07-02 11:00"])
    name = "Informe de Pto. SPB 1-jul-2026.xlsx"
    r = client.post("/upload/0/2026/7", files={"file": (name, b, XLSX_CT)})
    assert r.status_code == 200, r.text
    assert _dias(0, 2026, 7) == {1: 1, 2: 1}
