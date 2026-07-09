"""Agregación de datos para los informes PDF (SIN disponibilidad).

Funciones de consulta puras (reciben `Session` + parámetros ya validados por el
llamador). Separadas de la composición del PDF para poder probarlas sin generar
archivos. La DISPONIBILIDAD queda excluida por decisión del cliente (RN-1.2); el
contenido se basa en volumen de escaneos y el catálogo RN-1.2b.
"""
import calendar

from sqlalchemy import func

from models import (EscaneosDiarios, EscaneosHorarios, Operadores, Puerto,
                    EscaneoFila, IndiceIdentificador, Alerta)

# Tipos de alerta de VOLUMEN — excluye las de disponibilidad/SLA (RN-1.2b/1.5).
TIPOS_ALERTA_VOLUMEN = ("anomaly_low", "anomaly_high", "ewma_drop", "ewma_spike",
                        "zero_day", "operator_drop")
_ESTADOS_ABIERTOS = ("open", "acknowledged")


# ── Helpers de período ─────────────────────────────────────
def _prev_mes(year: int, mes: int):
    return (year, mes - 1) if mes > 1 else (year - 1, 12)


def _total_o_none(db, puerto_id, year, mes):
    """SUM(escaneos) del mes, o None si el mes NO tiene ningún registro.

    Distingue 'sin carga' (None) de '0 escaneos reales' (0), clave para que la
    variación no divida por cero ni invente una base (RN-2.3)."""
    return db.query(func.sum(EscaneosDiarios.total))\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).scalar()


def _variacion(actual: int, base):
    """MoM/YoY (RN-1.3). base None → todo None; base 0 → delta_pct None."""
    if base is None:
        return {"actual": actual, "base": None, "delta_abs": None, "delta_pct": None}
    delta_abs = actual - base
    delta_pct = None if base == 0 else round((actual - base) / base * 100, 1)
    return {"actual": actual, "base": base, "delta_abs": delta_abs,
            "delta_pct": delta_pct}


def _trazabilidad(db, puerto_id, year, mes) -> dict:
    """Conteo de contenedores/placas escaneados del puerto-mes (0 si no hay
    reporte de detalle). Une el índice de identificadores con su fila de escaneo
    para filtrar por período."""
    filas = db.query(IndiceIdentificador.tipo, IndiceIdentificador.valido)\
        .join(EscaneoFila, IndiceIdentificador.fila_id == EscaneoFila.id)\
        .filter(EscaneoFila.puerto_id == puerto_id,
                EscaneoFila.year == year, EscaneoFila.mes == mes).all()
    cont = val = placa = 0
    for tipo, valido in filas:
        if tipo == "contenedor":
            cont += 1
            if valido:
                val += 1
        elif tipo == "placa":
            placa += 1
    return {"contenedores": cont, "contenedores_validos": val, "placas": placa}


def _operadores_distintos(db, puerto_id, year, mes) -> int:
    return int(db.query(func.count(func.distinct(Operadores.nombre)))
               .filter_by(puerto_id=puerto_id, year=year, mes=mes).scalar() or 0)


def _alertas_volumen(db, puerto_id, year, mes) -> list:
    rows = db.query(Alerta).filter(
        Alerta.puerto_id == puerto_id, Alerta.year == year, Alerta.mes == mes,
        Alerta.tipo.in_(TIPOS_ALERTA_VOLUMEN),
        Alerta.estado.in_(_ESTADOS_ABIERTOS)).all()
    rows.sort(key=lambda a: (a.severidad, a.tipo))
    return [{"tipo": a.tipo, "severidad": a.severidad, "mensaje": a.mensaje,
             "fecha": a.creada_en} for a in rows]


# ── Datos de un puerto-mes ─────────────────────────────────
def datos_puerto(db, puerto_id: int, year: int, mes: int) -> dict:
    """Reúne todos los datos del informe de un puerto-mes. Si el período no tiene
    escaneos, devuelve `sin_datos=True` (el PDF muestra 'sin cargas', RN-3.3)."""
    diarios = db.query(EscaneosDiarios)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes)\
        .order_by(EscaneosDiarios.dia).all()

    dias_mes = calendar.monthrange(year, mes)[1]

    if not diarios:
        return {
            "sin_datos": True, "year": year, "mes": mes,
            "total": 0, "promedio_diario": 0, "dias_activos": 0,
            "dia_pico": None, "dia_valle": None,
            "serie_diaria": [{"dia": d, "total": 0} for d in range(1, dias_mes + 1)],
            "horaria": [{"hora": h, "total": 0} for h in range(24)],
            "operadores": [], "operadores_distintos": 0,
            "trazabilidad": {"contenedores": 0, "contenedores_validos": 0, "placas": 0},
            "variacion": {"mensual": _variacion(0, _total_o_none(db, puerto_id, *_prev_mes(year, mes))),
                          "interanual": _variacion(0, _total_o_none(db, puerto_id, year - 1, mes))},
            "alertas": _alertas_volumen(db, puerto_id, year, mes),
        }

    por_dia = {d.dia: (d.total or 0) for d in diarios}
    total = sum(por_dia.values())
    dias_activos = sum(1 for t in por_dia.values() if t > 0)
    promedio = round(total / dias_activos) if dias_activos else 0

    # Día pico / valle: solo entre días CON actividad (>0).
    activos = {d: t for d, t in por_dia.items() if t > 0}
    dia_pico = dia_valle = None
    if activos:
        dp = max(activos, key=lambda d: (activos[d], -d))   # mayor total, día menor
        dv = min(activos, key=lambda d: (activos[d], d))
        dia_pico = {"dia": dp, "total": activos[dp]}
        dia_valle = {"dia": dv, "total": activos[dv]}

    horas = {h: 0 for h in range(24)}
    for h in db.query(EscaneosHorarios)\
            .filter_by(puerto_id=puerto_id, year=year, mes=mes).all():
        if 0 <= h.hora <= 23:
            horas[h.hora] += (h.total or 0)

    ops = {}
    for o in db.query(Operadores)\
            .filter_by(puerto_id=puerto_id, year=year, mes=mes).all():
        ops[o.nombre] = ops.get(o.nombre, 0) + (o.total or 0)
    operadores = sorted(({"nombre": n, "total": t} for n, t in ops.items()),
                        key=lambda x: (-x["total"], x["nombre"]))

    py, pm = _prev_mes(year, mes)
    return {
        "sin_datos": False, "year": year, "mes": mes,
        "total": total, "promedio_diario": promedio, "dias_activos": dias_activos,
        "dia_pico": dia_pico, "dia_valle": dia_valle,
        "serie_diaria": [{"dia": d, "total": por_dia.get(d, 0)}
                         for d in range(1, dias_mes + 1)],
        "horaria": [{"hora": h, "total": horas[h]} for h in range(24)],
        "operadores": operadores, "operadores_distintos": len(ops),
        "trazabilidad": _trazabilidad(db, puerto_id, year, mes),
        "variacion": {
            "mensual": _variacion(total, _total_o_none(db, puerto_id, py, pm)),
            "interanual": _variacion(total, _total_o_none(db, puerto_id, year - 1, mes)),
        },
        "alertas": _alertas_volumen(db, puerto_id, year, mes),
    }


# ── Consolidado nacional ───────────────────────────────────
def _resolver_puertos(db, puerto_ids):
    """puerto_ids None (alcance global) → todos los puertos, ordenados por id."""
    q = db.query(Puerto).order_by(Puerto.id)
    if puerto_ids is not None:
        q = q.filter(Puerto.id.in_(puerto_ids))
    return q.all()


def _total_nacional_mes(db, year, mes, ids):
    """(total, base_none): total de escaneos nacional del mes y su base para
    variación (None si NINGÚN puerto del alcance tiene registro ese mes)."""
    q = db.query(func.sum(EscaneosDiarios.total))\
        .filter(EscaneosDiarios.year == year, EscaneosDiarios.mes == mes)
    if ids is not None:
        q = q.filter(EscaneosDiarios.puerto_id.in_(ids))
    val = q.scalar()
    return (0 if val is None else int(val)), val


def datos_nacional(db, year: int, mes: int, puerto_ids) -> dict:
    """Consolidado nacional del mes: totales, ranking, variación, serie anual y
    tabla por puerto. `puerto_ids` None = todos (alcance global). Sin disponibilidad."""
    puertos = _resolver_puertos(db, puerto_ids)
    ids = [p.id for p in puertos]

    por_puerto = []
    ranking_src = []
    sin_carga = []
    total_nacional = 0
    operadores_distintos = 0
    contenedores = 0

    for p in puertos:
        t = _total_o_none(db, p.id, year, mes)
        total = 0 if t is None else int(t)
        total_nacional += total
        if t is None:
            sin_carga.append(p.nombre_corto)

        dias_activos = db.query(func.count(EscaneosDiarios.id)).filter(
            EscaneosDiarios.puerto_id == p.id, EscaneosDiarios.year == year,
            EscaneosDiarios.mes == mes, EscaneosDiarios.total > 0).scalar() or 0
        prom = round(total / dias_activos) if dias_activos else 0
        ops = _operadores_distintos(db, p.id, year, mes)
        traz = _trazabilidad(db, p.id, year, mes)
        alertas = db.query(func.count(Alerta.id)).filter(
            Alerta.puerto_id == p.id, Alerta.year == year, Alerta.mes == mes,
            Alerta.tipo.in_(TIPOS_ALERTA_VOLUMEN),
            Alerta.estado.in_(_ESTADOS_ABIERTOS)).scalar() or 0

        operadores_distintos += ops
        contenedores += traz["contenedores"]
        por_puerto.append({
            "puerto_id": p.id, "nombre": p.nombre_corto, "total": total,
            "promedio_diario": prom, "operadores": ops,
            "contenedores": traz["contenedores"], "placas": traz["placas"],
            "sin_carga": t is None, "alertas": int(alertas),
        })
        ranking_src.append((p.id, p.nombre_corto, total))

    # Ranking: total desc, empate por puerto_id asc (RN-1.4).
    ranking_src.sort(key=lambda r: (-r[2], r[0]))
    ranking = []
    for pos, (pid, nombre, total) in enumerate(ranking_src, start=1):
        cuota = round(total / total_nacional * 100, 1) if total_nacional else 0.0
        ranking.append({"posicion": pos, "puerto_id": pid, "nombre": nombre,
                        "total": total, "cuota_pct": cuota})

    # Promedio diario nacional = total / días con actividad (distintos) del mes.
    q_dias = db.query(func.count(func.distinct(EscaneosDiarios.dia))).filter(
        EscaneosDiarios.year == year, EscaneosDiarios.mes == mes,
        EscaneosDiarios.total > 0)
    if ids:
        q_dias = q_dias.filter(EscaneosDiarios.puerto_id.in_(ids))
    dias_activos_nac = q_dias.scalar() or 0
    promedio_nac = round(total_nacional / dias_activos_nac) if dias_activos_nac else 0

    # Variación nacional MoM/YoY.
    py, pm = _prev_mes(year, mes)
    _, base_mom = _total_nacional_mes(db, py, pm, ids)
    _, base_yoy = _total_nacional_mes(db, year - 1, mes, ids)

    # Serie mensual del año (para el gráfico de tendencia).
    serie_anual = []
    for m in range(1, 13):
        tot, _ = _total_nacional_mes(db, year, m, ids)
        serie_anual.append({"mes": m, "total": tot})

    puertos_con_dato = len(puertos) - len(sin_carga)
    return {
        "sin_datos": total_nacional == 0 and puertos_con_dato == 0,
        "year": year, "mes": mes,
        "total_nacional": total_nacional, "promedio_diario": promedio_nac,
        "puertos_con_dato": puertos_con_dato, "puertos_sin_carga": sin_carga,
        "operadores_distintos": operadores_distintos, "contenedores": contenedores,
        "ranking": ranking, "por_puerto": por_puerto,
        "variacion": {
            "mensual": _variacion(total_nacional,
                                  None if base_mom is None else int(base_mom)),
            "interanual": _variacion(total_nacional,
                                     None if base_yoy is None else int(base_yoy)),
        },
        "serie_anual": serie_anual,
    }
