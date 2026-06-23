"""
PROTACTICS — Motor de detección de anomalías
─────────────────────────────────────────────────────────────────
Detecta comportamientos anómalos en los escaneos diarios de un puerto y los
registra como alertas, de forma idempotente y excluyendo los días de
mantenimiento (no generan ni cuentan para anomalías).

Métodos:
  1. Mediana móvil + MAD por DÍA DE LA SEMANA — un lunes se compara con lunes.
  2. Carta de control EWMA — caídas/picos SOSTENIDOS (no baches de un día).
  3. Días en cero dentro de un mes activo (huecos entre actividad).
  4. Caída del número de operadores frente al histórico.

Toda la estadística (median, mad, ewma, _flag_*) son funciones PURAS, testeables
sin base de datos. `evaluar_mes` es la única que escribe alertas.
"""
import calendar
from datetime import datetime, date

from sqlalchemy.orm import Session

from models import EscaneosDiarios, Operadores
import mantenimiento as mant
from alert_store import upsert_alerta, resolver_obsoletas

# ── Parámetros (configurables) ─────────────────────────────
PARAMS = {
    "ventana_dia_semana": 8,   # nº de ocurrencias previas del mismo día de semana
    "min_muestra": 4,          # mínimo de puntos para evaluar (si no, insuficiente)
    "k_mad": 3.5,              # nº de desviaciones (MAD escalado) para anomalía
    "abs_min": 3.0,            # piso absoluto de desviación (ignora ruido pequeño)
    "rel_min": 0.15,          # piso relativo: desviación ≥ 15% de la mediana
    "ewma_lambda": 0.3,        # factor de suavizado EWMA
    "ewma_L": 3.0,            # ancho de los límites de control (en sigmas)
    "ewma_sostenido": 2,       # días consecutivos fuera de límite para disparar
    "ewma_min_puntos": 8,      # mínimo de puntos para correr la carta EWMA
    "ops_min_meses": 3,        # mínimo de meses de historia para evaluar operadores
    "ops_caida_pct": 0.40,     # caída ≥ 40% del nº de operadores → alerta
}

MAD_SCALE = 1.4826             # MAD → desviación estándar (distribución normal)

TIPOS_ANOMALIA = ("anomaly_low", "anomaly_high", "ewma_drop", "ewma_spike",
                  "zero_day", "operator_drop")

MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


# ══════════════════════════════════════════════════════════════
#  Estadística pura
# ══════════════════════════════════════════════════════════════
def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def mad(xs, med=None):
    """Desviación absoluta mediana."""
    if not xs:
        return None
    if med is None:
        med = median(xs)
    return median([abs(x - med) for x in xs])


def ewma(values, lam):
    """Serie EWMA: z_t = λ·x_t + (1−λ)·z_{t−1}, z_0 = x_0."""
    z = None
    out = []
    for x in values:
        z = x if z is None else lam * x + (1 - lam) * z
        out.append(z)
    return out


def _flag_punto(value, sample, p=PARAMS):
    """¿`value` es anómalo frente a `sample` (mismo día de semana)?

    Devuelve None si no es anómalo o no hay muestra suficiente; si lo es, un dict
    con mediana, mad, score (nº de sigmas) y signo. Requiere significancia
    estadística (> k·sigma) Y un piso práctico de desviación (evita disparar por
    ruido cuando MAD≈0)."""
    if len(sample) < p["min_muestra"]:
        return None
    med = median(sample)
    m = mad(sample, med)
    sigma = m * MAD_SCALE
    desv = abs(value - med)
    floor = max(p["abs_min"], p["rel_min"] * med)
    if desv < floor:
        return None  # desviación demasiado pequeña para ser relevante
    if sigma > 0 and desv <= p["k_mad"] * sigma:
        return None  # dentro del rango estadístico normal
    score = desv / sigma if sigma > 0 else None
    signo = "low" if value < med else "high"
    sev = "critical" if (score is not None and score >= 1.5 * p["k_mad"]) else "warning"
    return {"mediana": med, "mad": m, "score": round(score, 2) if score else None,
            "signo": signo, "valor": value, "severidad": sev}


# ══════════════════════════════════════════════════════════════
#  Acceso a datos
# ══════════════════════════════════════════════════════════════
def _serie_diaria(db, puerto_id):
    """{date: total} de todos los escaneos diarios del puerto."""
    rows = db.query(EscaneosDiarios).filter_by(puerto_id=puerto_id).all()
    return {date(r.year, r.mes, r.dia): r.total for r in rows}


def _fechas_excluidas(db, puerto_id, meses):
    out = set()
    for (y, m) in meses:
        for d in mant.dias_excluidos(db, puerto_id, y, m):
            out.add(date(y, m, d))
    return out


def _ultimo_dia_considerado(year, mes):
    """Último día evaluable del mes: hoy si es el mes en curso, si no el fin de mes.
    Devuelve 0 si el mes es futuro (nada que evaluar)."""
    today = datetime.utcnow()
    if (year, mes) > (today.year, today.month):
        return 0
    if year == today.year and mes == today.month:
        return today.day
    return calendar.monthrange(year, mes)[1]


# ══════════════════════════════════════════════════════════════
#  Detectores (devuelven listas de hallazgos, sin escribir)
# ══════════════════════════════════════════════════════════════
def detectar_dia_semana(serie, excluidas, year, mes, p=PARAMS):
    """Anomalías por mediana móvil + MAD según día de la semana."""
    hallazgos = []
    last = _ultimo_dia_considerado(year, mes)
    for d in range(1, last + 1):
        dt = date(year, mes, d)
        if dt in excluidas or dt not in serie:
            continue
        # Muestra: ocurrencias previas del mismo día de la semana, no excluidas.
        sample_fechas = sorted(
            (f for f in serie
             if f.weekday() == dt.weekday() and f < dt and f not in excluidas),
            reverse=True)[:p["ventana_dia_semana"]]
        sample = [serie[f] for f in sample_fechas]
        flag = _flag_punto(serie[dt], sample, p)
        if flag:
            hallazgos.append({"dia": d, **flag})
    return hallazgos


def detectar_ewma(serie, excluidas, year, mes, p=PARAMS):
    """Caídas/picos SOSTENIDOS vía carta de control EWMA."""
    last = _ultimo_dia_considerado(year, mes)
    if last == 0:
        return []
    fin_mes = date(year, mes, last)
    # Serie elegible cronológica hasta el fin del mes objetivo.
    fechas = sorted(f for f in serie if f not in excluidas and f <= fin_mes)
    valores = [serie[f] for f in fechas]
    if len(valores) < p["ewma_min_puntos"]:
        return []
    centro = median(valores)
    sigma = mad(valores, centro) * MAD_SCALE
    if sigma <= 0:
        return []  # sin variación → no hay carta
    lam = p["ewma_lambda"]
    limite = p["ewma_L"] * sigma * (lam / (2 - lam)) ** 0.5   # límite del EWMA
    limite_raw = p["ewma_L"] * sigma                          # banda Shewhart (datos crudos)
    z = ewma(valores, lam)
    cruda = {f: v for f, v in zip(fechas, valores)}

    # Una racha = días consecutivos del mes objetivo con el EWMA fuera de límite.
    # Para DISTINGUIR una caída/pico SOSTENIDO de un bache de un solo día (que el
    # EWMA arrastra varios días por su memoria), se exige además que al menos
    # `ewma_sostenido` días de la racha tengan el DATO CRUDO fuera de la banda.
    hallazgos = []
    run_signo = None
    run_inicio = None
    run_len = 0
    run_peor = 0.0
    run_crudos = 0

    def cerrar_run():
        nonlocal run_signo, run_inicio, run_len, run_peor, run_crudos
        if (run_signo and run_len >= p["ewma_sostenido"]
                and run_crudos >= p["ewma_sostenido"]):
            tipo = "ewma_drop" if run_signo == "drop" else "ewma_spike"
            sev = "critical" if run_crudos >= 2 * p["ewma_sostenido"] else "warning"
            hallazgos.append({"tipo": tipo, "dia": run_inicio.day, "dias": run_len,
                              "severidad": sev, "centro": round(centro, 1),
                              "limite": round(limite, 1), "z": round(run_peor, 1)})
        run_signo = None
        run_inicio = None
        run_len = 0
        run_peor = 0.0
        run_crudos = 0

    for f, zt in zip(fechas, z):
        if f.month != mes or f.year != year:
            continue
        fuera = abs(zt - centro) > limite
        signo = "drop" if zt < centro else "spike"
        crudo_fuera = abs(cruda[f] - centro) > limite_raw and \
            (("drop" if cruda[f] < centro else "spike") == signo)
        if fuera and (run_signo is None or run_signo == signo):
            if run_signo is None:
                run_signo = signo
                run_inicio = f
            run_len += 1
            if crudo_fuera:
                run_crudos += 1
            if abs(zt - centro) > abs(run_peor - centro):
                run_peor = zt
        else:
            cerrar_run()
            if fuera:
                run_signo = signo
                run_inicio = f
                run_len = 1
                run_crudos = 1 if crudo_fuera else 0
                run_peor = zt
    cerrar_run()
    return hallazgos


def detectar_dias_cero(serie, excluidas, year, mes):
    """Días en cero (o sin registro) dentro del rango activo del mes, agrupados
    por racha consecutiva. No marca días futuros ni días en mantenimiento."""
    last = _ultimo_dia_considerado(year, mes)
    if last == 0:
        return []
    activos = [d for d in range(1, last + 1)
               if date(year, mes, d) in serie and serie[date(year, mes, d)] > 0]
    if not activos:
        return []  # mes sin actividad: lo gestiona el SLA (no_upload), no anomalías
    primer, ultimo = min(activos), max(activos)
    hallazgos = []
    run_inicio = None
    run_len = 0
    for d in range(primer, ultimo + 1):
        dt = date(year, mes, d)
        es_cero = dt not in excluidas and (dt not in serie or serie[dt] == 0)
        if es_cero:
            if run_inicio is None:
                run_inicio = d
            run_len += 1
        else:
            if run_inicio is not None:
                hallazgos.append({"dia": run_inicio, "desde": run_inicio,
                                  "hasta": run_inicio + run_len - 1, "dias": run_len})
                run_inicio = None
                run_len = 0
    if run_inicio is not None:
        hallazgos.append({"dia": run_inicio, "desde": run_inicio,
                          "hasta": run_inicio + run_len - 1, "dias": run_len})
    return hallazgos


def detectar_caida_operadores(db, puerto_id, year, mes, p=PARAMS):
    """Caída del nº de operadores distintos del mes frente a la mediana histórica."""
    def n_ops(y, m):
        return db.query(Operadores.nombre).filter_by(
            puerto_id=puerto_id, year=y, mes=m).distinct().count()

    actual = n_ops(year, mes)
    if actual == 0:
        return None
    # Meses previos con operadores registrados.
    previos = db.query(Operadores.year, Operadores.mes).filter(
        (Operadores.puerto_id == puerto_id) &
        ((Operadores.year < year) | ((Operadores.year == year) & (Operadores.mes < mes)))
    ).distinct().all()
    counts = [n_ops(y, m) for (y, m) in previos]
    counts = [c for c in counts if c > 0]
    if len(counts) < p["ops_min_meses"]:
        return None
    med = median(counts)
    if med and actual < (1 - p["ops_caida_pct"]) * med:
        return {"actual": actual, "mediana_historica": med}
    return None


# ══════════════════════════════════════════════════════════════
#  Evaluación (escribe alertas, idempotente)
# ══════════════════════════════════════════════════════════════
def evaluar_mes(db: Session, puerto_id: int, year: int, mes: int,
                actor_id=None) -> dict:
    """Corre todos los detectores sobre (puerto, year, mes) y sincroniza alertas.
    NO hace commit (lo hace el llamador)."""
    serie = _serie_diaria(db, puerto_id)
    meses = {(f.year, f.month) for f in serie} | {(year, mes)}
    excluidas = _fechas_excluidas(db, puerto_id, meses)

    claves_validas = set()
    pref = f"{MONTHS[mes - 1]} {year}"

    # 1. Mediana móvil + MAD por día de la semana
    for h in detectar_dia_semana(serie, excluidas, year, mes):
        tipo = "anomaly_low" if h["signo"] == "low" else "anomaly_high"
        sentido = "por debajo" if h["signo"] == "low" else "por encima"
        mensaje = (f"Escaneos del día {h['dia']} ({h['valor']}) {sentido} de lo "
                   f"esperado para ese día de la semana (mediana {h['mediana']}).")
        upsert_alerta(db, puerto_id=puerto_id, tipo=tipo, severidad=h["severidad"],
                      mensaje=mensaje, year=year, mes=mes, dia=h["dia"],
                      payload={"metodo": "weekday_mad", "valor": h["valor"],
                               "mediana": h["mediana"], "mad": h["mad"],
                               "score": h["score"]})
        claves_validas.add((tipo, h["dia"]))

    # 2. EWMA (sostenido)
    for h in detectar_ewma(serie, excluidas, year, mes):
        verbo = "caída" if h["tipo"] == "ewma_drop" else "pico"
        mensaje = (f"Tendencia con {verbo} sostenida {h['dias']} día(s) desde el "
                   f"{h['dia']} (EWMA {h['z']} vs centro {h['centro']}).")
        upsert_alerta(db, puerto_id=puerto_id, tipo=h["tipo"], severidad=h["severidad"],
                      mensaje=mensaje, year=year, mes=mes, dia=h["dia"],
                      payload={"metodo": "ewma", "dias": h["dias"], "z": h["z"],
                               "centro": h["centro"], "limite": h["limite"]})
        claves_validas.add((h["tipo"], h["dia"]))

    # 3. Días en cero
    for h in detectar_dias_cero(serie, excluidas, year, mes):
        if h["dias"] == 1:
            mensaje = f"Día {h['desde']} sin escaneos dentro de un mes activo ({pref})."
        else:
            mensaje = (f"{h['dias']} días consecutivos sin escaneos (del {h['desde']} "
                       f"al {h['hasta']}) dentro de un mes activo ({pref}).")
        sev = "critical" if h["dias"] >= 3 else "warning"
        upsert_alerta(db, puerto_id=puerto_id, tipo="zero_day", severidad=sev,
                      mensaje=mensaje, year=year, mes=mes, dia=h["dia"],
                      payload={"desde": h["desde"], "hasta": h["hasta"], "dias": h["dias"]})
        claves_validas.add(("zero_day", h["dia"]))

    # 4. Caída de operadores
    co = detectar_caida_operadores(db, puerto_id, year, mes)
    if co:
        mensaje = (f"Caída de operadores en {pref}: {co['actual']} activos frente a "
                   f"una mediana histórica de {co['mediana_historica']}.")
        upsert_alerta(db, puerto_id=puerto_id, tipo="operator_drop", severidad="warning",
                      mensaje=mensaje, year=year, mes=mes, dia=None, payload=co)
        claves_validas.add(("operator_drop", None))

    # Resolver las anomalías que ya no aplican en este mes.
    resolver_obsoletas(db, puerto_id=puerto_id, year=year, mes=mes,
                       tipos=TIPOS_ANOMALIA, claves_validas=claves_validas,
                       actor_id=actor_id)
    return {"puerto_id": puerto_id, "year": year, "mes": mes,
            "anomalias": len(claves_validas)}
