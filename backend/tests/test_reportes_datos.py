"""Agregación de datos para los informes PDF (`reportes/datos.py`).

Lógica pura de consulta: totales, día pico/valle, variación MoM/YoY, ranking
nacional, trazabilidad y exclusión de disponibilidad. Es el grueso de la
cobertura numérica del milestone.
"""
import database
from reportes import datos as D
from models import (EscaneosDiarios, EscaneosHorarios, Operadores,
                    EscaneoFila, IndiceIdentificador)


def _seed_diarios(puerto_id, year, mes, por_dia):
    db = database.SessionLocal()
    try:
        for dia, total in por_dia.items():
            db.add(EscaneosDiarios(puerto_id=puerto_id, year=year, mes=mes,
                                   dia=dia, total=total))
        db.commit()
    finally:
        db.close()


def _datos_puerto(puerto_id, year, mes):
    db = database.SessionLocal()
    try:
        return D.datos_puerto(db, puerto_id, year, mes)
    finally:
        db.close()


def _datos_nacional(year, mes, ids=None):
    db = database.SessionLocal()
    try:
        return D.datos_nacional(db, year, mes, ids)
    finally:
        db.close()


# ── datos_puerto ────────────────────────────────────────────
def test_datos_puerto_basico(client):
    _seed_diarios(0, 2026, 6, {1: 100, 2: 200, 3: 0})
    d = _datos_puerto(0, 2026, 6)
    assert d["sin_datos"] is False
    assert d["total"] == 300
    assert d["dias_activos"] == 2                     # el día 3 (=0) no cuenta
    assert d["promedio_diario"] == 150
    assert d["dia_pico"] == {"dia": 2, "total": 200}
    assert d["dia_valle"] == {"dia": 1, "total": 100}
    assert len(d["serie_diaria"]) == 30               # junio: 30 días
    assert len(d["horaria"]) == 24
    assert "disponibilidad" not in d                  # excluida (RN-1.2)


def test_datos_puerto_sin_datos(client):
    d = _datos_puerto(0, 2026, 1)
    assert d["sin_datos"] is True
    assert d["total"] == 0
    assert len(d["serie_diaria"]) == 31               # enero: 31 días
    assert d["dia_pico"] is None


def test_horaria_y_operadores(client):
    _seed_diarios(0, 2026, 6, {1: 50})
    db = database.SessionLocal()
    try:
        # dos días con la misma hora → se acumulan
        db.add(EscaneosHorarios(puerto_id=0, year=2026, mes=6, dia=1, hora=9, total=20))
        db.add(EscaneosHorarios(puerto_id=0, year=2026, mes=6, dia=2, hora=9, total=30))
        db.add(Operadores(puerto_id=0, year=2026, mes=6, dia=1, nombre="Ana", total=30))
        db.add(Operadores(puerto_id=0, year=2026, mes=6, dia=2, nombre="Ana", total=20))
        db.add(Operadores(puerto_id=0, year=2026, mes=6, dia=1, nombre="Luis", total=10))
        db.commit()
    finally:
        db.close()
    d = _datos_puerto(0, 2026, 6)
    assert d["horaria"][9]["total"] == 50             # 20 + 30
    assert d["operadores_distintos"] == 2
    assert d["operadores"][0] == {"nombre": "Ana", "total": 50}   # ordenado desc


def test_variacion_mensual_e_interanual(client):
    _seed_diarios(0, 2026, 5, {d: 10 for d in range(1, 11)})   # 100
    _seed_diarios(0, 2026, 6, {d: 20 for d in range(1, 11)})   # 200
    _seed_diarios(0, 2025, 6, {d: 5 for d in range(1, 11)})    # 50
    d = _datos_puerto(0, 2026, 6)
    assert d["variacion"]["mensual"]["delta_pct"] == 100.0     # (200-100)/100
    assert d["variacion"]["interanual"]["delta_pct"] == 300.0  # (200-50)/50


def test_variacion_base_none(client):
    # Solo el mes actual: no hay base previa → n/d (None), sin división por cero.
    _seed_diarios(0, 2026, 6, {1: 100})
    d = _datos_puerto(0, 2026, 6)
    assert d["variacion"]["mensual"]["base"] is None
    assert d["variacion"]["mensual"]["delta_pct"] is None
    assert d["variacion"]["interanual"]["delta_pct"] is None


def test_trazabilidad(client):
    _seed_diarios(0, 2026, 6, {1: 10})
    db = database.SessionLocal()
    try:
        f = EscaneoFila(puerto_id=0, formato="tcbuen", filename="r", fila_idx=0,
                        year=2026, mes=6, dia=1)
        db.add(f)
        db.flush()
        db.add(IndiceIdentificador(fila_id=f.id, puerto_id=0, tipo="contenedor",
                                   valor="MSGU9035797", valido=True))
        db.add(IndiceIdentificador(fila_id=f.id, puerto_id=0, tipo="contenedor",
                                   valor="NOISO", valido=False))
        db.add(IndiceIdentificador(fila_id=f.id, puerto_id=0, tipo="placa",
                                   valor="TLK300", valido=None, tipo_placa="delantera"))
        db.commit()
    finally:
        db.close()
    d = _datos_puerto(0, 2026, 6)
    assert d["trazabilidad"] == {"contenedores": 2, "contenedores_validos": 1, "placas": 1}


def test_datos_puerto_deterministico(client):
    _seed_diarios(0, 2026, 6, {1: 10, 2: 20})
    assert _datos_puerto(0, 2026, 6) == _datos_puerto(0, 2026, 6)


# ── datos_nacional ──────────────────────────────────────────
def test_ranking_nacional_y_cuota(client):
    _seed_diarios(0, 2026, 6, {1: 100})
    _seed_diarios(1, 2026, 6, {1: 300})
    _seed_diarios(2, 2026, 6, {1: 200})
    d = _datos_nacional(2026, 6)
    assert d["total_nacional"] == 600
    assert [r["puerto_id"] for r in d["ranking"][:3]] == [1, 2, 0]   # 300,200,100
    assert d["ranking"][0]["cuota_pct"] == 50.0
    assert d["puertos_con_dato"] == 3
    assert len(d["puertos_sin_carga"]) == 4          # 7 puertos sembrados, 3 con dato
    assert "disponibilidad" not in d


def test_ranking_empate_por_puerto_id(client):
    _seed_diarios(2, 2026, 6, {1: 100})
    _seed_diarios(5, 2026, 6, {1: 100})
    d = _datos_nacional(2026, 6)
    # Empate a 100 → desempata por puerto_id ascendente (2 antes que 5).
    top2 = [r["puerto_id"] for r in d["ranking"] if r["total"] == 100]
    assert top2 == [2, 5]


def test_nacional_alcance_parcial(client):
    _seed_diarios(0, 2026, 6, {1: 100})
    _seed_diarios(1, 2026, 6, {1: 300})
    d = _datos_nacional(2026, 6, ids=[0])           # solo puerto 0 visible
    assert d["total_nacional"] == 100
    assert [r["puerto_id"] for r in d["ranking"]] == [0]


def test_serie_anual_tiene_12_meses(client):
    _seed_diarios(0, 2026, 6, {1: 100})
    d = _datos_nacional(2026, 6)
    assert [x["mes"] for x in d["serie_anual"]] == list(range(1, 13))
    assert d["serie_anual"][5]["total"] == 100      # junio (índice 5)
