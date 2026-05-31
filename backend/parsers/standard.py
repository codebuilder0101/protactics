"""Parser Formato A — Standard (Miniatura-based)"""
import re
from datetime import datetime


def parse(rows: list[dict], port_name: str, month_name: str) -> dict:
    scans = [r for r in rows if r.get("Miniatura") not in (None, "", "nan")]

    daily, hourly, operators = {}, {}, {}

    for r in scans:
        raw = str(r.get("Fecha de creación", "") or "")
        dm = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw)
        hm = re.search(r"(\d{2}):(\d{2}):(\d{2})", raw)
        is_pm = bool(re.search(r"p\.?\s?m", raw, re.I))
        is_am = bool(re.search(r"a\.?\s?m", raw, re.I))

        if dm:
            day = int(dm.group(1))
            daily[day] = daily.get(day, 0) + 1

        if hm:
            h = int(hm.group(1))
            if is_pm and h < 12:
                h += 12
            if is_am and h == 12:
                h = 0
            hourly[h] = hourly.get(h, 0) + 1

        op = str(r.get("Nombre de Usuario") or "Desconocido").strip()
        operators[op] = operators.get(op, 0) + 1

    total = len(scans)
    days  = len(daily)
    peak  = max(daily.values(), default=0)
    avg   = round(total / days) if days else 0

    return dict(port_name=port_name, month_name=month_name, total_scans=total,
                days_active=days, peak_day=peak, avg_daily=avg,
                daily=daily, hourly=hourly, operators=operators, format="standard")
