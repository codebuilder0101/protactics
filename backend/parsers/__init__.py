"""Auto-detector de formato y dispatcher de parsers"""
from parsers import standard, rapiscan, tcbuen


def detect_format(rows: list) -> str:
    if not rows:
        return "standard"

    # Check for Rapiscan signatures in first 60 rows
    for row in rows[:60]:
        vals = list(row) if isinstance(row, (list, tuple)) else list(row.values())
        flat = " ".join(str(v) for v in vals if v)
        if any(kw in flat for kw in ("Scan Date", "Total Inspected", "Cargo Inspection")):
            return "rapiscan"

    # Check for TCBUEN: Estado column with numeric 100/102
    if rows and isinstance(rows[0], dict):
        estado_vals = [str(r.get("Estado de flujo de trabajo", "")).strip() for r in rows[:10]]
        if any(v in ("100", "102", "100.0", "102.0") for v in estado_vals):
            return "tcbuen"

    return "standard"


def parse_file(rows: list, port_name: str, month_name: str,
               filter_year: int, filter_month: int) -> dict:
    fmt = detect_format(rows)
    if fmt == "rapiscan":
        return rapiscan.parse(rows, port_name, month_name, filter_year, filter_month)
    if fmt == "tcbuen":
        return tcbuen.parse(rows, port_name, month_name)
    return standard.parse(rows, port_name, month_name)
