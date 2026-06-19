"""Features 4+5 — auto-enrutamiento: puerto y período deducidos del archivo."""
import main
from database import PUERTOS_SEED
from routing import route_file, detect_port
from conftest import standard_xlsx, tcbuen_xlsx, rapiscan_xlsx


def _rows(b, name):
    return main.read_excel_rows(b, name)


def test_puerto_y_fecha_desde_nombre(client):
    b = standard_xlsx(["2026-04-05 10:00", "2026-04-06 11:00"])
    name = "SPR Buenaventura 05-04-2026.xlsx"
    d = route_file(_rows(b, name), name, PUERTOS_SEED)
    assert d["puerto_id"] == 0                       # SPR Buenaventura
    assert (d["year"], d["mes"]) == (2026, 4)
    assert d["period_source"] == "filename"
    assert d["confidence"] == "high"


def test_fecha_desde_contenido_cuando_nombre_no_la_trae(client):
    b = tcbuen_xlsx(["2026-03-10 09:00", "2026-03-11 09:00"])
    name = "TCBUEN reporte marzo.xlsx"               # sin fecha en el nombre
    d = route_file(_rows(b, name), name, PUERTOS_SEED)
    assert d["puerto_id"] == 2                        # TCBUEN
    assert (d["year"], d["mes"]) == (2026, 3)
    assert d["period_source"] == "content"
    assert d["confidence"] == "high"


def test_rapiscan_enruta_a_aguadulce(client):
    b = rapiscan_xlsx(["2026-05-02 08:00", "2026-05-03 08:00"])
    name = "Aguadulce mayo.xlsx"
    d = route_file(_rows(b, name), name, PUERTOS_SEED)
    assert d["format"] == "rapiscan"
    assert d["puerto_id"] == 1                        # Aguadulce
    assert (d["year"], d["mes"]) == (2026, 5)


def test_puerto_desconocido_necesita_revision(client):
    b = standard_xlsx(["2026-04-05 10:00"])
    name = "reporte generico 05-04-2026.xlsx"         # sin nombre de puerto
    d = route_file(_rows(b, name), name, PUERTOS_SEED)
    assert d["puerto_id"] is None
    assert d["confidence"] == "low"


def test_archivo_multimes_usa_mes_dominante(client):
    b = standard_xlsx(["2026-04-05 10:00", "2026-04-06 10:00", "2026-05-02 10:00"])
    name = "SPR Buenaventura.xlsx"
    d = route_file(_rows(b, name), name, PUERTOS_SEED)
    assert d["multi_month"] is not None
    assert d["mes"] == 4                              # 2 filas abril vs 1 mayo
    assert d["multi_month"]["dominante"]["mes"] == 4


# ── Detección de puerto (incl. nombres concatenados) ────────
def test_detect_port_nombre_concatenado_en_archivo(client):
    # "...ESCANERPTOTCBUEN.xlsx" no tiene separadores, pero contiene 'tcbuen'.
    b = tcbuen_xlsx(["2026-06-10 09:00"])
    name = "REPORTE10062026ESCANERPTOTCBUEN.xlsx"
    assert detect_port(_rows(b, name), name, PUERTOS_SEED) == 2

    b2 = rapiscan_xlsx(["2026-06-10 09:00"])
    name2 = "REPORTE10062026ESCANERPTOAGUADULCE.xlsx"
    assert detect_port(_rows(b2, name2), name2, PUERTOS_SEED) == 1


def test_detect_port_ambiguo_devuelve_none(client):
    b = standard_xlsx(["2026-06-10 09:00"])
    name = "reporte generico.xlsx"
    assert detect_port(_rows(b, name), name, PUERTOS_SEED) is None


# ── Desambiguación de escáner (Antioquia E1 vs E2) ──────────
def test_enruta_antioquia_escaner_1_y_2_por_separado(client):
    # Ambos archivos comparten el token 'antioquia'; solo el nº de escáner del
    # nombre los distingue. Deben ir a puertos DISTINTOS (3 = E1, 4 = E2).
    b = standard_xlsx(["2026-06-10 09:00"])
    n1 = "REPORTE16062026ESCANER1PTOANTIOQUIA.xlsx"
    n2 = "REPORTE16062026ESCANER2PTOANTIOQUIA.xlsx"
    d1 = route_file(_rows(b, n1), n1, PUERTOS_SEED)
    d2 = route_file(_rows(b, n2), n2, PUERTOS_SEED)
    assert (d1["puerto_id"], d1["confidence"]) == (3, "high")
    assert (d2["puerto_id"], d2["confidence"]) == (4, "high")


def test_enruta_antioquia_escaner_p1(client):
    # Variante de nombre "...ESCANERP1PTO..." (la 'p' antes del dígito).
    b = standard_xlsx(["2026-06-10 09:00"])
    name = "REPORTE16062026ESCANERP1PTOANTIOQUIA.xlsx"
    assert detect_port(_rows(b, name), name, PUERTOS_SEED) == 3


# ── Alias/abreviatura de puerto (SPB → SPR Buenaventura) ────
def test_enruta_spb_a_buenaventura(client):
    # "SPB" (Sociedad Portuaria de Buenaventura) es abreviatura, no coincide con el
    # nombre oficial "SPR Buenaventura"; aun así debe enrutarse al puerto 0.
    b = standard_xlsx(["2026-06-10 09:00"])
    name = "REPORTE16062026ESCANERPTOSPB.xlsx"
    d = route_file(_rows(b, name), name, PUERTOS_SEED)
    assert (d["puerto_id"], d["confidence"]) == (0, "high")
