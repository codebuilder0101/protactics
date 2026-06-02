"""Parser Formato A — Standard (basado en inspecciones / 'Fecha de creación').

Una inspección = una fila con 'Fecha de creación' válida. Antes se contaba por
la columna 'Miniatura' (la imagen del camión), que casi siempre va vacía y por
eso subcontaba a unas pocas filas. La fecha puede venir en dos formatos:
    ISO:         2026-03-01 05:02:18
    DD/MM/YYYY:  01/03/2026 05:02:18 a. m.
"""
import re

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})")
_DMY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_HMS = re.compile(r"(\d{1,2}):(\d{2})")
# Un operador real no empieza por una fecha; algunas filas traen basura ahí.
_DATE_LIKE = re.compile(r"^\s*\d{1,4}[-/]\d{1,2}[-/]\d{1,4}")


def _is_empty(v) -> bool:
    return v is None or str(v).strip() in ("", "nan", "None", "NaT")


def _day_hour(raw):
    """Extrae (día, hora 0-23) soportando formato ISO y DD/MM/YYYY am/pm."""
    s = str(raw or "").strip()
    if not s:
        return None, None
    m = _ISO.search(s)
    if m:
        return int(m.group(3)), int(m.group(4))   # ISO: la hora ya es 24h
    day = None
    dm = _DMY.search(s)
    if dm:
        day = int(dm.group(1))
    hour = None
    hm = _HMS.search(s)
    if hm:
        hour = int(hm.group(1))
        if re.search(r"p\.?\s?m", s, re.I) and hour < 12:
            hour += 12
        if re.search(r"a\.?\s?m", s, re.I) and hour == 12:
            hour = 0
    return day, hour


def _clean_operator(val):
    """Nombre del operador; None si parece basura (una fecha)."""
    op = str(val or "").strip()
    if _DATE_LIKE.match(op):
        return None
    return op or "Desconocido"


def parse(rows: list, port_name: str, month_name: str) -> dict:
    # Una inspección = fila con 'Fecha de creación' presente.
    scans = [r for r in rows if not _is_empty(r.get("Fecha de creación"))]

    daily, hourly, operators = {}, {}, {}

    for r in scans:
        day, hour = _day_hour(r.get("Fecha de creación"))
        if day is not None:
            daily[day] = daily.get(day, 0) + 1
        if hour is not None:
            hourly[hour] = hourly.get(hour, 0) + 1
        op = _clean_operator(r.get("Nombre de Usuario"))
        if op:
            operators[op] = operators.get(op, 0) + 1

    total = len(scans)
    days  = len(daily)
    peak  = max(daily.values(), default=0)
    avg   = round(total / days) if days else 0

    return dict(port_name=port_name, month_name=month_name, total_scans=total,
                days_active=days, peak_day=peak, avg_daily=avg,
                daily=daily, hourly=hourly, operators=operators, format="standard")
