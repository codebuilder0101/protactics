"""Parser Formato A — Standard (inspecciones por 'Fecha de creación').

Una inspección = una fila con 'Fecha de creación' válida. Soporta fecha ISO,
DD/MM/YYYY am/pm y serial de Excel. Produce un desglose por día (by_day) para
poder acumular reportes diarios sin perder los días ya cargados.
"""
import re
from parsers.dates import to_ymdh, DayBuckets

_DATE_LIKE = re.compile(r"^\s*\d{1,4}[-/]\d{1,2}[-/]\d{1,4}")


def _is_empty(v) -> bool:
    return v is None or str(v).strip() in ("", "nan", "None", "NaT")


def _clean_operator(val):
    op = str(val or "").strip()
    if _DATE_LIKE.match(op):
        return None
    return op or "Desconocido"


def parse(rows: list, port_name: str, month_name: str,
          filter_year: int = None, filter_month: int = None) -> dict:
    scans = [r for r in rows if not _is_empty(r.get("Fecha de creación"))]

    buckets = DayBuckets()
    for r in scans:
        y, mo, day, hour = to_ymdh(r.get("Fecha de creación"), filter_month)
        if filter_year and y and y != filter_year:
            continue
        if filter_month and mo and mo != filter_month:
            continue
        op = _clean_operator(r.get("Nombre de Usuario"))
        buckets.add(day, hour, op)

    return buckets.result(port_name, month_name, "standard")
