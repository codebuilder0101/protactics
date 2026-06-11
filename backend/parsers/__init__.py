"""Auto-detector de formato y dispatcher de parsers"""
from parsers import standard, rapiscan, tcbuen
from parsers.dates import period_from_filename  # re-exportado para main.py


def _row_tokens(row):
    # Incluye claves y valores para que la detección funcione tanto con filas
    # tipo lista (el nombre de columna está en la celda) como tipo dict (el
    # nombre de columna es la clave).
    if isinstance(row, (list, tuple)):
        return [str(v) for v in row if v not in (None, "")]
    toks = [str(k) for k in row.keys()]
    toks += [str(v) for v in row.values() if v not in (None, "")]
    return toks


def detect_format(rows: list) -> str:
    if not rows:
        return "standard"

    # Funciona con filas tipo lista o tipo dict (mira las primeras 60).
    for row in rows[:60]:
        flat = " ".join(_row_tokens(row))
        if any(kw in flat for kw in ("Scan Date", "Total Inspected", "Cargo Inspection")):
            return "rapiscan"
        if "Estado de flujo de trabajo" in flat:
            return "tcbuen"

    return "standard"


def parse_file(rows: list, port_name: str, month_name: str,
               filter_year: int, filter_month: int) -> dict:
    fmt = detect_format(rows)
    if fmt == "rapiscan":
        return rapiscan.parse(rows, port_name, month_name, filter_year, filter_month)
    if fmt == "tcbuen":
        return tcbuen.parse(rows, port_name, month_name, filter_year, filter_month)
    return standard.parse(rows, port_name, month_name, filter_year, filter_month)
