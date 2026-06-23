"""Integración extremo-a-extremo: subir un Excel dispara los motores y las alertas.

Verifica el hook de carga (process_upload → anomalías + SLA) por la vía real de la
API, no llamando a los motores directamente."""
from conftest import standard_xlsx, XLSX_CT


def _fechas(year, mes, dias, por_dia=1):
    """Lista de fechas 'YYYY-MM-DD' repetidas `por_dia` veces (1 escaneo c/u)."""
    out = []
    for d in dias:
        for _ in range(por_dia):
            out.append(f"{year}-{mes:02d}-{d:02d}")
    return out


def test_upload_pocos_dias_genera_incumplimiento_sla(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    # Marzo 2025 con solo 10 días activos de 31 → ~32% < 95 → incumplimiento.
    xlsx = standard_xlsx(_fechas(2025, 3, range(1, 11)))
    r = client.post("/upload/0/2025/3",
                    files={"file": ("marzo.xlsx", xlsx, XLSX_CT)})
    assert r.status_code == 200, r.text
    # El motor debió abrir una alerta de SLA para el puerto 0.
    alertas = client.get("/alertas?puerto_id=0&estado=open").json()
    assert any(a["tipo"] == "sla_breach" for a in alertas)
    # El resumen para las insignias del mapa también lo refleja.
    resumen = client.get("/alertas/resumen").json()
    assert resumen.get("0", {}).get("warning", 0) + resumen.get("0", {}).get("critical", 0) >= 1


def test_meses_incluye_estado_sla(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    xlsx = standard_xlsx(_fechas(2025, 3, range(1, 32)))   # mes completo → cumple
    client.post("/upload/0/2025/3", files={"file": ("m.xlsx", xlsx, XLSX_CT)})
    meses = client.get("/meses/0").json()
    assert meses and "estado_sla" in meses[0]
    assert meses[0]["estado_sla"]["estado"] in (
        "CUMPLE", "EN_RIESGO", "INCUMPLE", "EN_MANTENIMIENTO", "SIN_DATOS")


def test_mantenimiento_y_recalculo_resuelve_sla(client, admin):
    client.post("/api/auth/login", json={"email": "admin@test.co", "password": "admin1234"})
    # 24 días activos de 31 → incumple.
    xlsx = standard_xlsx(_fechas(2025, 3, range(1, 25)))
    client.post("/upload/0/2025/3", files={"file": ("m.xlsx", xlsx, XLSX_CT)})
    abiertas = client.get("/alertas?puerto_id=0&estado=open").json()
    assert any(a["tipo"] == "sla_breach" for a in abiertas)
    # Marcar los días faltantes (25–31) como mantenimiento y recalcular.
    client.post("/mantenimiento/0", json={"tipo": "programado",
                "fecha_inicio": "2025-03-25", "fecha_fin": "2025-03-31"})
    client.post("/alertas/recalcular/0/2025/3")
    # Ahora 24/24 días elegibles activos → cumple → alerta resuelta.
    abiertas2 = client.get("/alertas?puerto_id=0&estado=open").json()
    assert not any(a["tipo"] == "sla_breach" for a in abiertas2)
