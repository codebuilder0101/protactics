"""Parser Formato C — TCBUEN (Estado numérico 100 = completado)"""
from datetime import datetime, timezone, timedelta


def _to_dt(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, (int, float)):
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(raw))
        except Exception:
            return None
    try:
        return datetime.fromisoformat(str(raw)[:19])
    except Exception:
        return None


def parse(rows: list[dict], port_name: str, month_name: str) -> dict:
    scans = [r for r in rows
             if str(r.get("Estado de flujo de trabajo", "")).strip() in ("100", "100.0")]

    daily, hourly, operators = {}, {}, {}

    for r in scans:
        dt = _to_dt(r.get("Fecha de creación"))
        if not dt:
            continue
        day  = dt.day
        hour = dt.hour
        daily[day]   = daily.get(day, 0) + 1
        hourly[hour] = hourly.get(hour, 0) + 1
        op = str(r.get("Nombre de Usuario") or "Desconocido").strip()
        operators[op] = operators.get(op, 0) + 1

    total = len(scans)
    days  = len(daily)
    peak  = max(daily.values(), default=0)
    avg   = round(total / days) if days else 0

    return dict(port_name=port_name, month_name=month_name, total_scans=total,
                days_active=days, peak_day=peak, avg_daily=avg,
                daily=daily, hourly=hourly, operators=operators,
                operatorCount=len(operators), format="tcbuen")
