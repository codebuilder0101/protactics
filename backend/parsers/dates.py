"""Utilidades de fecha compartidas por los parsers.

Soporta:
  • Serial de Excel (float) — fecha real, sin ambigüedad.
  • ISO  2026-04-06 23:56:00
  • DD/MM/YYYY  01/03/2026 05:02:18 a. m.

La fecha se lee de forma LITERAL: no se aplica ninguna corrección de orden
día/mes ni filtrado por período. El valor se interpreta tal como viene.
"""
import re
import unicodedata
from datetime import datetime, timedelta

_ISO_DT = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})")
_ISO_D  = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DMY    = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_HM     = re.compile(r"(\d{1,2}):(\d{2})")
# Fecha numérica en el nombre del archivo, p. ej. "... 04-06-2026.xlsx" = 4-jun-2026.
_FNAME  = re.compile(r"(\d{1,2})[-_.](\d{1,2})[-_.](\d{4})")
# Fecha con nombre de mes, p. ej. "... 1-jul-26", "01-jul-2026", "2 jul 2026".
_FNAME_MES = re.compile(r"(\d{1,2})[-_.\s]+([A-Za-zÁÉÍÓÚáéíóú]{3,10})[-_.\s]+(\d{2,4})")

# Meses en español (e inglés por si acaso), comparados por sus 3 primeras letras
# sin acentos: "jul", "ago", "set/sep"...
_MESES = {
    "ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5,
    "jun": 6, "jul": 7, "ago": 8, "aug": 8, "sep": 9, "set": 9, "oct": 10,
    "nov": 11, "dic": 12, "dec": 12,
}


def _mes_num(token: str):
    """Número de mes (1-12) a partir de un nombre de mes, o None."""
    t = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()
    return _MESES.get(t.lower()[:3])


def period_from_filename(filename: str):
    """Devuelve (año, mes, día) leído del nombre del archivo, o None.

    Es la fuente MÁS FIABLE de la fecha del reporte: las fechas dentro del archivo
    a veces vienen con el día y el mes intercambiados o en formato US (M/D). Se
    reconocen dos formas:
      • con nombre de mes: "1-jul-26", "01-jul-2026", "2 jul 2026" (preferida);
      • numérica DD-MM-YYYY: "04-06-2026" (con corrección si venía como MM-DD).
    Los años de 2 dígitos se expanden a 20YY.
    """
    if not filename:
        return None

    # 1) Nombre de mes (no ambiguo respecto al orden día/mes).
    m = _FNAME_MES.search(filename)
    if m:
        day, month, y = int(m[1]), _mes_num(m[2]), int(m[3])
        if month and 1 <= day <= 31:
            if y < 100:
                y += 2000
            return y, month, day

    # 2) Fecha numérica DD-MM-YYYY (o MM-DD si el "mes" no es válido).
    m = _FNAME.search(filename)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        day, month = a, b
        if month > 12 and day <= 12:
            day, month = b, a
        if 1 <= month <= 12 and 1 <= day <= 31:
            return y, month, day
    return None


def to_ymdh(raw):
    """Devuelve (año, mes, día, hora) o (None, None, None, None).

    Lee la fecha de forma LITERAL: no aplica ninguna corrección de orden
    día/mes ni filtra por período. El valor se interpreta tal como viene.
    """
    if raw is None or isinstance(raw, bool):
        return None, None, None, None

    # Serial de Excel → fecha real.
    if isinstance(raw, (int, float)):
        try:
            dt = datetime(1899, 12, 30) + timedelta(days=float(raw))
            return dt.year, dt.month, dt.day, dt.hour
        except Exception:
            return None, None, None, None

    if isinstance(raw, datetime):
        return raw.year, raw.month, raw.day, raw.hour

    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "nat", "total", "date"):
        return None, None, None, None

    m = _ISO_DT.search(s)
    if m:
        return int(m[1]), int(m[2]), int(m[3]), int(m[4])

    md = _ISO_D.search(s)
    if md:
        h = 0
        hm = _HM.search(s[md.end():])
        if hm:
            h = int(hm[1])
        return int(md[1]), int(md[2]), int(md[3]), h

    dm = _DMY.search(s)
    if dm:
        d, mo, y = int(dm[1]), int(dm[2]), int(dm[3])
        # Formato M/D/Y (EE. UU.), p. ej. "6/16/2026": el día y el mes vienen
        # intercambiados. Si el "mes" es > 12 y el "día" es válido como mes, se
        # corrige. Los casos ambiguos (ambos ≤ 12) se dejan como D/M/Y.
        if mo > 12 and d <= 12:
            d, mo = mo, d
        h = 0
        hm = _HM.search(s)
        if hm:
            h = int(hm[1])
            if re.search(r"p\.?\s?m", s, re.I) and h < 12:
                h += 12
            if re.search(r"a\.?\s?m", s, re.I) and h == 12:
                h = 0
        return y, mo, d, h

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
