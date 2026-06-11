"""Parser Formato C — TCBUEN (Estado de flujo de trabajo == 100 = completado).

Solo cuenta los escaneos con Estado 100. Produce desglose por día (by_day) para
acumular reportes diarios.
"""
from parsers.dates import to_ymdh, DayBuckets


def parse(rows: list, port_name: str, month_name: str,
          filter_year: int = None, filter_month: int = None) -> dict:
    scans = [r for r in rows
             if str(r.get("Estado de flujo de trabajo", "")).strip() in ("100", "100.0")]

    buckets = DayBuckets()
    for r in scans:
        y, mo, day, hour = to_ymdh(r.get("Fecha de creación"), filter_month)
        if filter_year and y and y != filter_year:
            continue
        if filter_month and mo and mo != filter_month:
            continue
        op = str(r.get("Nombre de Usuario") or "Desconocido").strip()
        buckets.add(day, hour, op)

    return buckets.result(port_name, month_name, "tcbuen")
