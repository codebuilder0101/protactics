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


WORKFLOW_COL   = "Estado de flujo de trabajo"
NUMERIC_STATUS = ("100", "102")


def _cells(row):
    return list(row) if isinstance(row, (list, tuple)) else list(row.values())


def _is_numeric_status(value) -> bool:
    """True si el valor es un estado numérico de TCBUEN (100/102, admite .0)."""
    if value is None or isinstance(value, bool):
        return False
    s = str(value).strip()
    return bool(s) and s.split(".")[0] in NUMERIC_STATUS


def _workflow_has_numeric_status(rows) -> bool:
    """Distingue TCBUEN de Miniatura/Standard cuando ambos traen la columna
    'Estado de flujo de trabajo'. TCBUEN usa estados numéricos (100/102);
    Miniatura usa texto ('Completado'), así que devuelve False para ese caso."""
    if rows and isinstance(rows[0], dict):
        return any(_is_numeric_status(r.get(WORKFLOW_COL)) for r in rows)

    # Filas tipo lista: ubicar la columna por el encabezado y muestrear valores.
    col = header_row = None
    for i, row in enumerate(rows[:60]):
        for j, v in enumerate(_cells(row)):
            if WORKFLOW_COL in str(v):
                col, header_row = j, i
                break
        if col is not None:
            break
    if col is None:
        return False
    for row in rows[header_row + 1: header_row + 2001]:
        cells = _cells(row)
        if col < len(cells) and _is_numeric_status(cells[col]):
            return True
    return False


def detect_format(rows: list) -> str:
    if not rows:
        return "standard"

    # Rapiscan: reportes de escaneo individual. La columna de fecha puede venir
    # como "Scan Date & Time" (export clásico) o como "Escaneos Individuales".
    for row in rows[:60]:
        flat = " ".join(_row_tokens(row))
        if any(kw in flat for kw in ("Scan Date", "Total Inspected",
                                     "Cargo Inspection", "Escaneos Individuales")):
            return "rapiscan"

    # TCBUEN vs Standard/Miniatura: comparten encabezados (incluida la columna
    # 'Estado de flujo de trabajo'). Lo que los distingue es el VALOR de esa
    # columna: TCBUEN trae estados numéricos (100/102); Miniatura trae texto.
    if any(WORKFLOW_COL in " ".join(_row_tokens(row)) for row in rows[:60]):
        return "tcbuen" if _workflow_has_numeric_status(rows) else "standard"

    return "standard"


def parse_file(rows: list, port_name: str, month_name: str,
               filter_year: int, filter_month: int) -> dict:
    fmt = detect_format(rows)
    if fmt == "rapiscan":
        return rapiscan.parse(rows, port_name, month_name, filter_year, filter_month)
    if fmt == "tcbuen":
        return tcbuen.parse(rows, port_name, month_name, filter_year, filter_month)
    return standard.parse(rows, port_name, month_name, filter_year, filter_month)
