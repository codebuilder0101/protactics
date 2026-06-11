"""Utilidades de fecha compartidas por los parsers.

Soporta:
  • Serial de Excel (float) — fecha real, sin ambigüedad.
  • ISO  2026-04-06 23:56:00
  • DD/MM/YYYY  01/03/2026 05:02:18 a. m.

Algunos reportes vienen en formato AÑO-DÍA-MES (p. ej. SPB exporta
"2026-04-06" para el 4 de junio). Como el mes lo elige el usuario al subir el
archivo, usamos ese mes (filter_month) para resolver la ambigüedad: si el mes
leído no coincide pero el día sí coincide con el mes elegido, se intercambian.
"""
import re
from datetime import datetime, timedelta

_ISO_DT = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})")
_ISO_D  = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DMY    = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_HM     = re.compile(r"(\d{1,2}):(\d{2})")
# Fecha en el nombre del archivo, p. ej. "... 04-06-2026.xlsx" = 4 de junio 2026.
_FNAME  = re.compile(r"(\d{1,2})[-_.](\d{1,2})[-_.](\d{4})")


def period_from_filename(filename: str):
    """Devuelve (año, mes, día) leído del nombre del archivo, o None.

    Asume formato DD-MM-YYYY (convención en español). Es la fuente más fiable de
    la fecha del reporte, porque las fechas dentro del archivo a veces vienen con
    el día y el mes intercambiados.
    """
    if not filename:
        return None
    m = _FNAME.search(filename)
    if not m:
        return None
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    day, month = a, b            # DD-MM por defecto
    if month > 12 and day <= 12:  # si el "mes" no es válido, estaba como MM-DD
        day, month = b, a
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    return y, month, day


def _invert(year, month, day, hour, filter_month):
    """Corrige el orden DÍA/MES en formatos ISO ambiguos (AÑO-DÍA-MES)."""
    if filter_month and month != filter_month and day == filter_month and 1 <= month <= 12:
        month, day = day, month
    return year, month, day, hour


def to_ymdh(raw, filter_month=None):
    """Devuelve (año, mes, día, hora) o (None, None, None, None).

    Aplica la corrección DÍA/MES (inversión) a todas las fuentes, porque algunos
    exportadores guardan la fecha con el día y el mes intercambiados (el 4 de
    junio queda como datetime(2026, 4, 6) = 6 de abril). El mes elegido al subir
    el archivo resuelve la ambigüedad.
    """
    if raw is None or isinstance(raw, bool):
        return None, None, None, None

    # Serial de Excel → fecha real.
    if isinstance(raw, (int, float)):
        try:
            dt = datetime(1899, 12, 30) + timedelta(days=float(raw))
            return _invert(dt.year, dt.month, dt.day, dt.hour, filter_month)
        except Exception:
            return None, None, None, None

    if isinstance(raw, datetime):
        return _invert(raw.year, raw.month, raw.day, raw.hour, filter_month)

    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "nat", "total", "date"):
        return None, None, None, None

    m = _ISO_DT.search(s)
    if m:
        return _invert(int(m[1]), int(m[2]), int(m[3]), int(m[4]), filter_month)

    md = _ISO_D.search(s)
    if md:
        h = 0
        hm = _HM.search(s[md.end():])
        if hm:
            h = int(hm[1])
        return _invert(int(md[1]), int(md[2]), int(md[3]), h, filter_month)

    dm = _DMY.search(s)
    if dm:
        d, mo, y = int(dm[1]), int(dm[2]), int(dm[3])
        h = 0
        hm = _HM.search(s)
        if hm:
            h = int(hm[1])
            if re.search(r"p\.?\s?m", s, re.I) and h < 12:
                h += 12
            if re.search(r"a\.?\s?m", s, re.I) and h == 12:
                h = 0
        return _invert(y, mo, d, h, filter_month)

    return None, None, None, None


class DayBuckets:
    """Acumula escaneos por día → {dia: {total, hourly{h}, operators{nombre}}}."""

    def __init__(self):
        self.by_day = {}

    def add(self, day, hour=None, operator=None):
        if day is None:
            return
        d = self.by_day.setdefault(day, {"total": 0, "hourly": {}, "operators": {}})
        d["total"] += 1
        if hour is not None:
            d["hourly"][hour] = d["hourly"].get(hour, 0) + 1
        if operator:
            d["operators"][operator] = d["operators"].get(operator, 0) + 1

    def result(self, port_name, month_name, fmt):
        """Estructura compatible con el resto del sistema + by_day para acumular."""
        by_day = self.by_day
        daily = {d: v["total"] for d, v in by_day.items()}
        hourly, operators = {}, {}
        for v in by_day.values():
            for h, c in v["hourly"].items():
                hourly[h] = hourly.get(h, 0) + c
            for n, c in v["operators"].items():
                operators[n] = operators.get(n, 0) + c
        total = sum(daily.values())
        days  = len(daily)
        peak  = max(daily.values(), default=0)
        avg   = round(total / days) if days else 0
        return dict(port_name=port_name, month_name=month_name, total_scans=total,
                    days_active=days, peak_day=peak, avg_daily=avg,
                    daily=daily, hourly=hourly, operators=operators,
                    operatorCount=len(operators), format=fmt, by_day=by_day)
