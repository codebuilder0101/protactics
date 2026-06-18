"""Parser Formato B — Rapiscan.

Soporta dos variantes:
  • DETALLE  (reporte diario "Escaneos Individuales"): una fila por escaneo, con
    columnas tipo 'Scan Date & Time' y 'User Name'. Es el formato que el cliente
    envía a diario (p. ej. SPB). Puede traer un encabezado de título arriba.
  • RESUMEN  (legacy mensual): filas (fecha, total) por encima del encabezado.

Produce desglose por día (by_day) para acumular reportes diarios.
"""
from parsers.dates import to_ymdh, DayBuckets

# Rótulos posibles para la columna de fecha del detalle. "Scan Date & Time" es
# el export clásico; "Escaneos Individuales" es la variante que usa ese título
# como cabecera de la columna de fecha.
DATE_HEADERS   = ("Scan Date", "Escaneos Individuales")
# Columnas que solo aparecen en la fila de encabezado REAL del detalle (no en
# los títulos superiores). Sirven para no confundir un título con el encabezado.
DETAIL_MARKERS = ("User Name", "Usuario", "Filename")


def _vals(row):
    return list(row) if isinstance(row, (list, tuple)) else list(row.values())


def _has(cells, needles):
    return any(any(n in str(v) for n in needles) for v in cells)


def _find_header(rows) -> int:
    """Índice de la fila de encabezado del detalle.

    Prefiere la fila que tiene a la vez un rótulo de fecha y una columna de
    detalle (User Name / Filename) — así elige el encabezado real y no un título
    superior que repite "Escaneos Individuales". Si no la halla, cae a la primera
    fila que tenga cualquier rótulo de fecha.
    """
    for i, row in enumerate(rows):
        cells = _vals(row)
        if _has(cells, DATE_HEADERS) and _has(cells, DETAIL_MARKERS):
            return i
    for i, row in enumerate(rows):
        if _has(_vals(row), DATE_HEADERS):
            return i
    return -1


def parse(rows: list, port_name: str, month_name: str,
          filter_year: int = None, filter_month: int = None) -> dict:

    # Localizar la fila de encabezado del detalle (fecha + columnas de detalle).
    header_idx = _find_header(rows)

    buckets = DayBuckets()

    # --- DETALLE: una fila por escaneo, debajo del encabezado ---
    if header_idx != -1:
        header = _vals(rows[header_idx])
        date_col = next((i for i, v in enumerate(header)
                         if any(h in str(v) for h in DATE_HEADERS)), None)
        user_col = next((i for i, v in enumerate(header)
                         if "User Name" in str(v) or "Usuario" in str(v)), None)
        if date_col is not None:
            for row in rows[header_idx + 1:]:
                vals = _vals(row)
                if len(vals) <= date_col:
                    continue
                raw = vals[date_col]
                if raw is None or str(raw).strip() == "":
                    continue
                y, mo, day, hour = to_ymdh(raw)
                if day is None:
                    continue
                op = None
                if user_col is not None and len(vals) > user_col:
                    op = str(vals[user_col] or "").strip() or None
                buckets.add(day, hour, op or "Operador")

    # --- RESUMEN legacy: filas (fecha, total) arriba del encabezado ---
    # Solo se usa si el detalle no aportó nada (archivo de puro resumen).
    if not buckets.by_day:
        summary_end = header_idx if header_idx != -1 else len(rows)
        for i in range(summary_end):
            vals = _vals(rows[i])
            if len(vals) < 2:
                continue
            raw_date, raw_total = vals[0], vals[1]
            try:
                tot = int(float(str(raw_total).replace(",", "")))
            except Exception:
                continue
            if tot <= 0:
                continue
            y, mo, day, _ = to_ymdh(raw_date)
            if day is None:
                continue
            d = buckets.by_day.setdefault(day, {"total": 0, "hourly": {}, "operators": {}})
            d["total"] += tot

    res = buckets.result(port_name, month_name, "rapiscan")
    # En resumen legacy no hay operadores reales; deja un marcador agregado.
    if not res["operators"] and res["total_scans"]:
        res["operators"] = {"Operador": res["total_scans"]}
    return res
