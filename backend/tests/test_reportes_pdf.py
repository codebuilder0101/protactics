"""Endpoints de informe PDF (por puerto y nacional): estructura, permisos por
alcance, período vacío y auditoría."""
import database
from models import EscaneosDiarios


def _seed(puerto_id, year, mes, n=5):
    db = database.SessionLocal()
    try:
        for dia in range(1, n + 1):
            db.add(EscaneosDiarios(puerto_id=puerto_id, year=year, mes=mes,
                                   dia=dia, total=100 + dia))
        db.commit()
    finally:
        db.close()


def _assert_pdf(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 800


# ── Informe de puerto ───────────────────────────────────────
def test_pdf_puerto_ok(client, admin):
    _seed(0, 2026, 6)
    r = client.get("/reportes/pdf/puerto/0/2026/6")
    _assert_pdf(r)
    assert "PROTACTICS" in r.headers["content-disposition"]
    assert "2026-06" in r.headers["content-disposition"]


def test_pdf_puerto_sin_sesion_401(client):
    r = client.get("/reportes/pdf/puerto/0/2026/6")
    assert r.status_code == 401


def test_pdf_puerto_periodo_vacio_es_pdf(client, admin):
    # Sin datos → PDF válido "sin cargas", NO 404 ni 500 (RN-3.3).
    r = client.get("/reportes/pdf/puerto/0/2026/1")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_pdf_puerto_mes_invalido_400(client, admin):
    r = client.get("/reportes/pdf/puerto/0/2026/13")
    assert r.status_code == 400


def test_pdf_puerto_inexistente_404(client, admin):
    r = client.get("/reportes/pdf/puerto/999/2026/6")
    assert r.status_code == 404


def test_pdf_puerto_ultimo_usa_ultimo_periodo(client, admin):
    _seed(0, 2026, 6)
    _seed(0, 2026, 7, n=3)
    r = client.get("/reportes/pdf/puerto/0")
    _assert_pdf(r)
    assert "2026-07" in r.headers["content-disposition"]   # el más reciente


# ── Permisos por alcance ────────────────────────────────────
def test_pdf_puerto_feeder_su_puerto_ok(client, admin, feeder):
    _seed(0, 2026, 6)
    r = feeder.get("/reportes/pdf/puerto/0/2026/6")     # feeder es del puerto 0
    _assert_pdf(r)


def test_pdf_puerto_feeder_otro_puerto_403(client, admin, feeder):
    _seed(2, 2026, 6)
    r = feeder.get("/reportes/pdf/puerto/2/2026/6")
    assert r.status_code == 403


# ── Informe nacional ────────────────────────────────────────
def test_pdf_nacional_admin_ok(client, admin):
    _seed(0, 2026, 6)
    _seed(1, 2026, 6)
    r = client.get("/reportes/pdf/nacional/2026/6")
    _assert_pdf(r)
    assert "nacional_2026-06" in r.headers["content-disposition"]


def test_pdf_nacional_ultimo_ok(client, admin):
    _seed(0, 2026, 6)
    r = client.get("/reportes/pdf/nacional")
    _assert_pdf(r)


def test_pdf_nacional_feeder_403(client, admin, feeder):
    _seed(0, 2026, 6)
    assert feeder.get("/reportes/pdf/nacional/2026/6").status_code == 403
    assert feeder.get("/reportes/pdf/nacional").status_code == 403


def test_pdf_nacional_sin_sesion_401(client):
    assert client.get("/reportes/pdf/nacional/2026/6").status_code == 401


# ── Auditoría ───────────────────────────────────────────────
def test_pdf_genera_auditoria(client, admin):
    _seed(0, 2026, 6)
    client.get("/reportes/pdf/puerto/0/2026/6")
    eventos = client.get("/api/audit?limit=20").json()
    reporte = [e for e in eventos if e["accion"] == "reporte_pdf"]
    assert reporte and reporte[0]["entidad"] == "reporte"
    assert client.get("/api/audit/verify").json()["ok"] is True
