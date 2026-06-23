"""Ventanas de mantenimiento: helper dias_excluidos (unit) + API (integración)."""
from datetime import date

import database
import mantenimiento as mant
from models import VentanaMantenimiento
from conftest import login_client


# ── Helpers ─────────────────────────────────────────────────
def _add_ventana(puerto_id, tipo, ini, fin):
    db = database.SessionLocal()
    try:
        db.add(VentanaMantenimiento(puerto_id=puerto_id, tipo=tipo,
                                    fecha_inicio=ini, fecha_fin=fin))
        db.commit()
    finally:
        db.close()


# ── Unit: dias_excluidos ────────────────────────────────────
def test_ventana_cerrada_dentro_del_mes(client):
    _add_ventana(0, "programado", date(2025, 3, 10), date(2025, 3, 12))
    db = database.SessionLocal()
    try:
        assert mant.dias_excluidos(db, 0, 2025, 3) == {10, 11, 12}
    finally:
        db.close()


def test_ventana_fuera_del_mes_set_vacio(client):
    _add_ventana(0, "programado", date(2025, 1, 5), date(2025, 1, 9))
    db = database.SessionLocal()
    try:
        assert mant.dias_excluidos(db, 0, 2025, 3) == set()
    finally:
        db.close()


def test_ventana_cruza_inicio_de_mes(client):
    # del 27-feb al 2-mar: solo 1 y 2 caen en marzo
    _add_ventana(0, "falla_tecnica", date(2025, 2, 27), date(2025, 3, 2))
    db = database.SessionLocal()
    try:
        assert mant.dias_excluidos(db, 0, 2025, 3) == {1, 2}
    finally:
        db.close()


def test_ventana_abierta_cubre_hasta_fin_de_mes(client):
    # fecha_fin NULL (abierta) iniciada el 20 → cubre 20..31 de marzo
    _add_ventana(0, "falla_tecnica", date(2025, 3, 20), None)
    db = database.SessionLocal()
    try:
        assert mant.dias_excluidos(db, 0, 2025, 3) == set(range(20, 32))
    finally:
        db.close()


def test_ventanas_solapadas_se_unen(client):
    _add_ventana(0, "programado", date(2025, 3, 5), date(2025, 3, 10))
    _add_ventana(0, "falla_tecnica", date(2025, 3, 8), date(2025, 3, 12))
    db = database.SessionLocal()
    try:
        assert mant.dias_excluidos(db, 0, 2025, 3) == set(range(5, 13))
    finally:
        db.close()


def test_mes_totalmente_en_mantenimiento(client):
    _add_ventana(0, "programado", date(2025, 3, 1), date(2025, 3, 31))
    db = database.SessionLocal()
    try:
        assert mant.mes_totalmente_en_mantenimiento(db, 0, 2025, 3) is True
        assert mant.mes_totalmente_en_mantenimiento(db, 0, 2025, 4) is False
    finally:
        db.close()


# ── Integración: API ────────────────────────────────────────
def test_crear_listar_mantenimiento_admin(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    r = client.post("/mantenimiento/0", json={"tipo": "programado",
                    "fecha_inicio": "2025-03-10", "fecha_fin": "2025-03-12",
                    "motivo": "mantenimiento del escáner"})
    assert r.status_code == 200, r.text
    assert r.json()["abierta"] is False
    lst = client.get("/mantenimiento/0").json()
    assert len(lst) == 1 and lst[0]["tipo"] == "programado"


def test_tipo_invalido_rechazado(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    r = client.post("/mantenimiento/0", json={"tipo": "vacaciones",
                    "fecha_inicio": "2025-03-10"})
    assert r.status_code == 422


def test_fecha_fin_anterior_rechazada(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    r = client.post("/mantenimiento/0", json={"tipo": "programado",
                    "fecha_inicio": "2025-03-10", "fecha_fin": "2025-03-05"})
    assert r.status_code == 422


def test_cerrar_ventana_abierta(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    vid = client.post("/mantenimiento/0", json={"tipo": "falla_tecnica",
                      "fecha_inicio": "2025-03-20"}).json()["id"]
    r = client.patch(f"/mantenimiento/{vid}", json={"cerrar": True})
    assert r.status_code == 200 and r.json()["abierta"] is False


def test_no_admin_no_crea(client, admin, feeder):
    # feeder (no admin) no puede crear ventanas de mantenimiento
    assert feeder.post("/mantenimiento/0", json={"tipo": "programado",
                       "fecha_inicio": "2025-03-10"}).status_code == 403


def test_observador_de_otro_puerto_no_ve(client, admin):
    client.post("/api/auth/users", json={"email": "obs@test.co", "password": "observ1234",
                "role": "observador", "puerto_id": 1})
    c = login_client("obs@test.co", "observ1234")
    assert c.get("/mantenimiento/0").status_code == 403


def test_crear_mantenimiento_audita(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    client.post("/mantenimiento/0", json={"tipo": "programado",
                "fecha_inicio": "2025-03-10", "fecha_fin": "2025-03-12"})
    eventos = client.get("/api/audit?limit=20").json()
    assert any(e["accion"] == "create_mantenimiento" for e in eventos)
    assert client.get("/api/audit/verify").json()["ok"] is True
