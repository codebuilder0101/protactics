"""Motor de anomalías: estadística pura, detectores y evaluación con BD."""
from datetime import date

import database
import anomalies
from models import EscaneosDiarios, Operadores, Alerta


# ── Helpers de siembra ──────────────────────────────────────
def _seed_dias(puerto_id, year, mes, totals: dict):
    db = database.SessionLocal()
    try:
        for dia, total in totals.items():
            db.add(EscaneosDiarios(puerto_id=puerto_id, year=year, mes=mes,
                                   dia=dia, total=total))
        db.commit()
    finally:
        db.close()


def _seed_ops(puerto_id, year, mes, nombres):
    db = database.SessionLocal()
    try:
        for n in nombres:
            db.add(Operadores(puerto_id=puerto_id, year=year, mes=mes, dia=1,
                              nombre=n, total=1))
        db.commit()
    finally:
        db.close()


def _alertas(puerto_id, tipo=None, estado="open"):
    db = database.SessionLocal()
    try:
        q = db.query(Alerta).filter_by(puerto_id=puerto_id)
        if tipo:
            q = q.filter_by(tipo=tipo)
        if estado:
            q = q.filter_by(estado=estado)
        return q.all()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
#  Estadística pura
# ══════════════════════════════════════════════════════════════
def test_median():
    assert anomalies.median([3, 1, 2]) == 2
    assert anomalies.median([1, 2, 3, 4]) == 2.5
    assert anomalies.median([]) is None


def test_mad():
    assert anomalies.mad([2, 2, 2]) == 0
    assert anomalies.mad([1, 2, 3, 4, 5]) == 1


def test_ewma_constante():
    assert anomalies.ewma([5, 5, 5], 0.3) == [5, 5, 5]


def test_flag_muestra_insuficiente():
    # menos de min_muestra (4) puntos → no evalúa
    assert anomalies._flag_punto(0, [100, 100, 100]) is None


def test_flag_detecta_caida():
    f = anomalies._flag_punto(10, [100, 98, 102, 101, 99, 100])
    assert f and f["signo"] == "low" and f["severidad"] == "critical"


def test_flag_detecta_pico():
    f = anomalies._flag_punto(400, [100, 98, 102, 101, 99, 100])
    assert f and f["signo"] == "high"


def test_flag_ignora_ruido_con_mad_cero():
    # serie perfectamente estable; una desviación de 1 no debe disparar
    assert anomalies._flag_punto(101, [100, 100, 100, 100, 100]) is None


def test_flag_sin_falso_positivo_en_serie_estable():
    assert anomalies._flag_punto(100, [100, 101, 99, 100, 102, 98]) is None


# ══════════════════════════════════════════════════════════════
#  Detectores puros (sobre serie construida, sin BD)
# ══════════════════════════════════════════════════════════════
def test_dias_cero_agrupa_racha():
    # días 1,2,3 activos, 4 y 5 sin registro (cero), 6 activo
    serie = {date(2025, 3, 1): 10, date(2025, 3, 2): 12,
             date(2025, 3, 3): 11, date(2025, 3, 6): 9}
    h = anomalies.detectar_dias_cero(serie, set(), 2025, 3)
    assert len(h) == 1
    assert h[0]["desde"] == 4 and h[0]["hasta"] == 5 and h[0]["dias"] == 2


def test_dias_cero_excluye_mantenimiento():
    serie = {date(2025, 3, 1): 10, date(2025, 3, 2): 12,
             date(2025, 3, 3): 11, date(2025, 3, 6): 9}
    excl = {date(2025, 3, 4), date(2025, 3, 5)}
    assert anomalies.detectar_dias_cero(serie, excl, 2025, 3) == []


def test_dias_cero_no_marca_antes_del_primer_activo():
    # primer activo es el día 5; días 1-4 no deben contar
    serie = {date(2025, 3, 5): 10, date(2025, 3, 6): 11, date(2025, 3, 7): 9}
    assert anomalies.detectar_dias_cero(serie, set(), 2025, 3) == []


def test_ewma_caida_sostenida_dispara():
    # febrero con variación realista (~100±3), marzo cae a 10 sostenido 4 días
    serie = {date(2025, 2, d): 100 + (d % 7) for d in range(1, 21)}
    for d in range(1, 5):
        serie[date(2025, 3, d)] = 10
    h = anomalies.detectar_ewma(serie, set(), 2025, 3)
    assert any(x["tipo"] == "ewma_drop" for x in h)


def test_ewma_bache_de_un_dia_no_dispara():
    serie = {date(2025, 2, d): 100 + (d % 7) for d in range(1, 21)}
    serie[date(2025, 3, 1)] = 10                       # un solo día caído
    for d in range(2, 12):
        serie[date(2025, 3, d)] = 100 + (d % 7)        # recuperado y estable
    h = anomalies.detectar_ewma(serie, set(), 2025, 3)
    assert all(x["tipo"] != "ewma_drop" for x in h)


# ══════════════════════════════════════════════════════════════
#  Evaluación con BD (idempotencia, exclusión, auto-resolución)
# ══════════════════════════════════════════════════════════════
def _vary(dias, base=100):
    """Totales con variación pequeña (MAD>0) para datos de prueba realistas."""
    return {d: base + (d % 7) for d in dias}


def test_evaluar_genera_anomalia_y_es_idempotente(client):
    # Historia (feb + marzo) ~100 con variación; el día 25 de marzo cae a 5.
    # Febrero da suficientes ocurrencias previas de cada día de la semana.
    _seed_dias(0, 2025, 2, _vary(range(1, 29)))
    _seed_dias(0, 2025, 3, {**_vary(range(1, 25)), 25: 5})
    db = database.SessionLocal()
    try:
        anomalies.evaluar_mes(db, 0, 2025, 3)
        db.commit()
    finally:
        db.close()
    n1 = len(_alertas(0, estado="open"))
    assert n1 >= 1
    # Reejecutar no debe duplicar
    db = database.SessionLocal()
    try:
        anomalies.evaluar_mes(db, 0, 2025, 3)
        db.commit()
    finally:
        db.close()
    assert len(_alertas(0, estado="open")) == n1


def test_anomalia_en_mantenimiento_no_genera_alerta(client):
    from models import VentanaMantenimiento
    _seed_dias(0, 2025, 2, _vary(range(1, 29)))
    _seed_dias(0, 2025, 3, {**_vary(range(1, 25)), 25: 5})
    # marcar el día 25 como mantenimiento
    db = database.SessionLocal()
    try:
        db.add(VentanaMantenimiento(puerto_id=0, tipo="falla_tecnica",
                                    fecha_inicio=date(2025, 3, 25),
                                    fecha_fin=date(2025, 3, 25)))
        db.commit()
        anomalies.evaluar_mes(db, 0, 2025, 3)
        db.commit()
    finally:
        db.close()
    # el día 25 estaba excluido → ninguna anomalía de tipo bajo/alto por ese día
    bajos = _alertas(0, tipo="anomaly_low")
    assert all(a.dia != 25 for a in bajos)


def test_anomalia_se_autoresuelve_al_corregir(client):
    _seed_dias(0, 2025, 2, _vary(range(1, 29)))
    _seed_dias(0, 2025, 3, {**_vary(range(1, 25)), 25: 5})
    db = database.SessionLocal()
    try:
        anomalies.evaluar_mes(db, 0, 2025, 3)
        db.commit()
    finally:
        db.close()
    assert len(_alertas(0, tipo="anomaly_low", estado="open")) >= 1
    # corregir el día 25 a un valor normal
    db = database.SessionLocal()
    try:
        row = db.query(EscaneosDiarios).filter_by(puerto_id=0, year=2025, mes=3, dia=25).first()
        row.total = 100
        db.commit()
        anomalies.evaluar_mes(db, 0, 2025, 3)
        db.commit()
    finally:
        db.close()
    assert len(_alertas(0, tipo="anomaly_low", estado="open")) == 0


def test_caida_operadores(client):
    _seed_ops(0, 2026, 1, ["A", "B", "C", "D", "E"])
    _seed_ops(0, 2026, 2, ["A", "B", "C", "D", "E"])
    _seed_ops(0, 2026, 3, ["A", "B", "C", "D", "E"])
    _seed_ops(0, 2026, 4, ["A", "B"])     # caída de 5 → 2
    db = database.SessionLocal()
    try:
        co = anomalies.detectar_caida_operadores(db, 0, 2026, 4)
    finally:
        db.close()
    assert co and co["actual"] == 2 and co["mediana_historica"] == 5


def test_caida_operadores_sin_historia_suficiente(client):
    _seed_ops(0, 2026, 1, ["A", "B", "C", "D", "E"])
    _seed_ops(0, 2026, 2, ["A", "B"])
    db = database.SessionLocal()
    try:
        # solo 1 mes previo (< ops_min_meses=3) → no evalúa
        assert anomalies.detectar_caida_operadores(db, 0, 2026, 2) is None
    finally:
        db.close()
