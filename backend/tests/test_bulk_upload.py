"""Feature 3 — carga masiva: éxito mixto, fallo parcial, tope y aislamiento de permisos."""
from conftest import standard_xlsx, tcbuen_xlsx, rapiscan_xlsx, XLSX_CT


def test_lote_multiple_ok(client, admin):
    files = [
        ("files", ("SPR Buenaventura 05-04-2026.xlsx",
                   standard_xlsx(["2026-04-05 10:00", "2026-04-06 11:00"]), XLSX_CT)),
        ("files", ("TCBUEN 10-04-2026.xlsx",
                   tcbuen_xlsx(["2026-04-10 09:00"]), XLSX_CT)),
    ]
    r = client.post("/upload/bulk", files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["ok"] == 2
    assert data["total"] == 2


def test_fallo_parcial_no_aborta_el_lote(client, admin):
    files = [
        ("files", ("SPR Buenaventura 05-04-2026.xlsx",
                   standard_xlsx(["2026-04-05 10:00"]), XLSX_CT)),
        ("files", ("SPR Buenaventura corrupto 06-04-2026.xlsx",
                   b"esto no es un excel", XLSX_CT)),
    ]
    r = client.post("/upload/bulk", files=files)
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["ok"] == 1 and s["error"] == 1


def test_archivo_sin_puerto_queda_para_revision(client, admin):
    files = [("files", ("reporte generico 05-04-2026.xlsx",
                        standard_xlsx(["2026-04-05 10:00"]), XLSX_CT))]
    r = client.post("/upload/bulk", files=files)
    assert r.status_code == 200
    res = r.json()
    assert res["summary"]["needs_review"] == 1
    assert res["results"][0]["status"] == "needs_review"


def test_tope_de_archivos(client, admin):
    b = standard_xlsx(["2026-04-05 10:00"])
    files = [("files", (f"SPR Buenaventura 05-04-2026_{i}.xlsx", b, XLSX_CT))
             for i in range(101)]
    r = client.post("/upload/bulk", files=files)
    assert r.status_code == 413


def test_aislamiento_de_permisos_por_archivo(feeder):
    # feeder del puerto 0: un archivo enruta a su puerto (ok) y otro a Aguadulce (error).
    files = [
        ("files", ("SPR Buenaventura 05-04-2026.xlsx",
                   standard_xlsx(["2026-04-05 10:00"]), XLSX_CT)),
        ("files", ("Aguadulce 05-04-2026.xlsx",
                   rapiscan_xlsx(["2026-04-05 10:00"]), XLSX_CT)),
    ]
    r = feeder.post("/upload/bulk", files=files)
    assert r.status_code == 200
    by_name = {i["filename"]: i for i in r.json()["results"]}
    assert by_name["SPR Buenaventura 05-04-2026.xlsx"]["status"] == "ok"
    assert by_name["Aguadulce 05-04-2026.xlsx"]["status"] == "error"
