"""
PROTACTICS — Auto-enrutamiento de archivos
─────────────────────────────────────────────────────────────
Deduce a qué (puerto, año, mes) pertenece un archivo Excel a partir de SU
CONTENIDO y nombre, sin que el usuario lo indique. 100% determinista (no usa IA):

  • Puerto  → coincidencia de tokens del nombre del puerto contra el nombre del
              archivo y las primeras filas del contenido.
  • Período → fecha del nombre del archivo si la trae (fuente más fiable); si no,
              el mes/año dominante leído de la columna de fecha del archivo.

Si algo queda ambiguo, se devuelve confianza baja y candidatos, para que la carga
masiva lo marque como `needs_review` en vez de archivarlo mal.
"""
import re
import unicodedata
from collections import Counter

from parsers import detect_format
from parsers import rapiscan
from parsers.dates import to_ymdh, period_from_filename

# Palabras genéricas (ya normalizadas) que no distinguen un puerto de otro.
_STOP = {"puerto", "puertos", "soc", "sociedad", "portuaria", "regional",
         "terminal", "de", "del", "la", "el", "industrial", "contenedores",
         "escaner", "pto", "sa", "s", "y", "con"}


def _norm(s) -> str:
    """minúsculas, sin acentos, no-alfanumérico → espacios."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _tokens(s) -> list:
    return [t for t in _norm(s).split() if t and t not in _STOP]


def _content_blob(raw_rows, limit_rows: int = 30) -> str:
    parts = []
    for row in raw_rows[:limit_rows]:
        cells = row if isinstance(row, (list, tuple)) else list(row.values())
        for c in cells:
            if c is not None:
                parts.append(str(c))
    return _norm(" ".join(parts))


def _score_ports(blob_tokens: set, puertos) -> list:
    """Puntúa cada puerto por nº de tokens distintivos presentes en el texto."""
    scored = []
    for p in puertos:
        pid = getattr(p, "id", None) if not isinstance(p, dict) else p.get("id")
        corto = getattr(p, "nombre_corto", None) if not isinstance(p, dict) else p.get("nombre_corto")
        largo = getattr(p, "nombre", None) if not isinstance(p, dict) else p.get("nombre")
        port_tokens = set(_tokens(corto)) | set(_tokens(largo))
        score = sum(1 for t in port_tokens if t in blob_tokens)
        scored.append({"id": pid, "nombre_corto": corto, "score": score,
                       "tokens": sorted(port_tokens)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _extract_periods(raw_rows, fmt) -> list:
    """Lista de (año, mes) leídos de la COLUMNA de fecha propia del formato."""
    out = []
    if not raw_rows:
        return out

    if fmt == "rapiscan":
        hi = rapiscan._find_header(raw_rows)
        if hi != -1:
            header = rapiscan._vals(raw_rows[hi])
            dcol = next((i for i, v in enumerate(header)
                         if any(h in str(v) for h in rapiscan.DATE_HEADERS)), None)
            if dcol is not None:
                for row in raw_rows[hi + 1:]:
                    vals = rapiscan._vals(row)
                    if dcol < len(vals):
                        y, mo, _, _ = to_ymdh(vals[dcol])
                        if y and mo:
                            out.append((y, mo))
        if not out:  # resumen legacy: (fecha, total) en la primera columna
            for row in raw_rows:
                vals = rapiscan._vals(row)
                if vals:
                    y, mo, _, _ = to_ymdh(vals[0])
                    if y and mo:
                        out.append((y, mo))
        return out

    # standard / tcbuen: encabezado en la primera fila, columna 'Fecha de creación'.
    first = raw_rows[0]
    header = list(first) if isinstance(first, (list, tuple)) else None
    if header is not None:
        dcol = next((i for i, v in enumerate(header)
                     if "Fecha de creaci" in str(v)), None)
        if dcol is not None:
            for row in raw_rows[1:]:
                if isinstance(row, (list, tuple)) and dcol < len(row):
                    y, mo, _, _ = to_ymdh(row[dcol])
                    if y and mo:
                        out.append((y, mo))
    return out


def route_file(raw_rows, filename, puertos) -> dict:
    """Resuelve (puerto_id, year, mes) de un archivo. Función pura y testeable.

    `puertos`: iterable de Puerto (ORM) o dicts con id/nombre/nombre_corto.
    Devuelve un dict con la decisión, candidatos, fuente del período y confianza
    ('high' | 'low'): 'low' significa "marcar para revisión, no archivar solo".
    """
    fmt = detect_format(raw_rows)

    # ── Puerto ───────────────────────────────────────────────
    blob = set(_content_blob(raw_rows).split()) | set(_norm(filename).split())
    scored = _score_ports(blob, puertos)
    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None
    port_ok = bool(best and best["score"] > 0 and
                   (second is None or best["score"] > second["score"]))
    puerto_id = best["id"] if port_ok else None

    # ── Período: nombre de archivo (preferente) → contenido ──
    period_source = None
    year = mes = None
    fname_period = period_from_filename(filename)
    content_periods = _extract_periods(raw_rows, fmt)
    counts = Counter(content_periods)
    dominant = counts.most_common(1)[0][0] if counts else None

    if fname_period:
        year, mes = fname_period[0], fname_period[1]
        period_source = "filename"
    elif dominant:
        year, mes = dominant
        period_source = "content"

    # ── Multi-mes: el archivo abarca varios meses ────────────
    multi_month = None
    if len(counts) > 1:
        total = sum(counts.values())
        top = counts.most_common(1)[0][1]
        multi_month = {
            "dominante": {"year": dominant[0], "mes": dominant[1],
                          "filas": top, "fraccion": round(top / total, 3)},
            "desglose": [{"year": y, "mes": m, "filas": n}
                         for (y, m), n in counts.most_common()],
        }

    # ── Confianza ────────────────────────────────────────────
    period_ok = year is not None and mes is not None
    if port_ok and period_ok:
        confidence = "high"
        reason = "puerto y período resueltos"
    else:
        confidence = "low"
        missing = []
        if not port_ok:
            missing.append("puerto ambiguo o desconocido")
        if not period_ok:
            missing.append("no se pudo determinar el período")
        reason = "; ".join(missing)

    return {
        "format": fmt,
        "puerto_id": puerto_id,
        "puerto_candidatos": [{"id": s["id"], "nombre_corto": s["nombre_corto"],
                               "score": s["score"]}
                              for s in scored if s["score"] > 0][:3],
        "year": year,
        "mes": mes,
        "period_source": period_source,
        "multi_month": multi_month,
        "confidence": confidence,
        "reason": reason,
    }
