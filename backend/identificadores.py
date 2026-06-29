"""
PROTACTICS — Identificadores (contenedores ISO 6346 y matrículas)
─────────────────────────────────────────────────────────────────
Funciones PURAS (sin BD) para:
  • normalizar números de contenedor y matrículas,
  • validar el dígito de control ISO 6346,
  • separar celdas multivalor (un escaneo puede traer varios contenedores),
  • clasificar las columnas de un reporte de DETALLE y extraer, por fila, el/los
    contenedor(es), la(s) matrícula(s) y la fecha-hora.

El escáner ya hizo el OCR: estos reportes son su SALIDA. Aquí no se hace OCR, solo
se lee el texto. La extracción es por NOMBRE de columna (con tolerancia a acentos y
a encabezados con encoding dañado), de modo que onboard de un puerto nuevo no exige
tocar código: basta con que su reporte traiga columnas reconocibles.
"""
import re
import unicodedata
from datetime import datetime

from parsers.dates import to_ymdh

# ── Validación ISO 6346 ────────────────────────────────────
_ISO_RE = re.compile(r"^[A-Z]{4}\d{7}$")

# Valor numérico de cada letra (A=10, B=12, …) saltando los múltiplos de 11.
_LETTER_VALUES = {}
_v = 10
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    while _v % 11 == 0:
        _v += 1
    _LETTER_VALUES[_ch] = _v
    _v += 1


def normalizar(s) -> str:
    """MAYÚSCULAS y solo alfanuméricos. Sirve para contenedor y matrícula."""
    if s is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


normalizar_contenedor = normalizar
normalizar_placa = normalizar


def validar_iso6346(s) -> bool:
    """True si `s` es un contenedor ISO 6346 válido (incluye dígito de control)."""
    c = normalizar(s)
    if not _ISO_RE.match(c):
        return False
    total = sum(_LETTER_VALUES[ch] * (2 ** i) for i, ch in enumerate(c[:4]))
    total += sum(int(c[4 + i]) * (2 ** (4 + i)) for i in range(6))
    return (total % 11) % 10 == int(c[10])


def separar_contenedores(raw) -> list:
    """Separa una celda en sus contenedores (TCBUEN trae varios por coma) y los
    normaliza. Descarta vacíos y ruido < 4 caracteres. Mantiene el orden."""
    if raw is None:
        return []
    out, seen = [], set()
    for part in re.split(r"[,;/|\n]+", str(raw)):
        c = normalizar(part)
        if len(c) >= 4 and c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ── Clasificación de columnas / extracción de filas ────────
def _norm_key(s) -> str:
    """Clave de columna comparable: sin acentos (ni � de encoding dañado),
    minúsculas, separadores colapsados."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", s.lower())).strip()


def clasificar_columnas(header) -> dict:
    """Dada la fila de encabezado, devuelve los índices de columna relevantes:
    {'fecha': idx|None, 'contenedor': [idx...], 'placa': [(idx, tipo)...]}.

    Reglas tolerantes a corrupción de acentos:
      • contenedor: contiene 'contenedor'/'container' y NO empieza por 'sin'
        (excluye el contador "Sin ID de Contenedor" de los reportes-resumen).
      • placa: contiene 'matr…' (matrícula) o 'placa', excluyendo 'país de la
        matrícula' (que es un país, no una placa). Tipo: delantera/trasera/placa.
      • fecha: contiene 'fecha' o ('scan' y 'date').
    """
    res = {"fecha": None, "contenedor": [], "placa": []}
    for i, c in enumerate(list(header)):
        if c is None:
            continue
        n = _norm_key(c)
        if not n:
            continue
        if ("contenedor" in n or "container" in n) and not n.startswith("sin"):
            res["contenedor"].append(i)
        elif ("matr" in n and "pais" not in n) or "placa" in n:
            tipo = "delantera" if "delant" in n else "trasera" if "tras" in n else "placa"
            res["placa"].append((i, tipo))
        elif res["fecha"] is None and ("fecha" in n or ("scan" in n and "date" in n)):
            res["fecha"] = i
    return res


def _es_columna_imagen(header) -> bool:
    n = _norm_key(header)
    return "miniatura" in n or "seleccion" in n or "thumbnail" in n


def encontrar_encabezado(rows) -> int:
    """Índice de la fila de encabezado del DETALLE (la que tiene columnas de
    contenedor o matrícula). Devuelve -1 si el archivo no es de detalle (p. ej.
    un reporte-resumen de estadística diaria: no se puede rastrear)."""
    best_idx, best_score = -1, 0
    for i, row in enumerate(rows[:40]):
        cols = clasificar_columnas(row)
        if not (cols["contenedor"] or cols["placa"]):
            continue
        score = (len(cols["contenedor"]) + len(cols["placa"])
                 + (1 if cols["fecha"] is not None else 0))
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx


def extraer_filas(rows: list, year: int, mes: int) -> list:
    """Extrae las filas de detalle de un reporte ya leído (lista de listas).

    Devuelve una lista de dicts:
      {dia, fecha_hora, datos{col:valor}, contenedores[...], placas[(valor,tipo)]}
    `datos` conserva TODAS las columnas de texto (menos miniatura/selección).
    Las fechas se anclan al período validado (year, mes) usando el día/hora de la
    fila. Filas sin fecha y sin identificadores se omiten (vacías/pie de página).
    Si el archivo no es de detalle, devuelve [] (no rastreable)."""
    hidx = encontrar_encabezado(rows)
    if hidx < 0:
        return []
    header = list(rows[hidx])
    cols = clasificar_columnas(header)
    headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(header)]
    img_cols = {i for i, h in enumerate(header) if _es_columna_imagen(h)}

    out = []
    for row in rows[hidx + 1:]:
        cells = list(row)

        day = hour = None
        if cols["fecha"] is not None and cols["fecha"] < len(cells):
            _, _, day, hour = to_ymdh(cells[cols["fecha"]])

        contenedores, seen = [], set()
        for ci in cols["contenedor"]:
            if ci < len(cells):
                for c in separar_contenedores(cells[ci]):
                    if c not in seen:
                        seen.add(c)
                        contenedores.append(c)

        placas, seenp = [], set()
        for pi, tipo in cols["placa"]:
            if pi < len(cells):
                v = normalizar(cells[pi])
                if len(v) >= 3 and v not in seenp:
                    seenp.add(v)
                    placas.append((v, tipo))

        if day is None and not contenedores and not placas:
            continue

        datos = {}
        for i, h in enumerate(headers):
            if i in img_cols or i >= len(cells):
                continue
            val = cells[i]
            if val is None or str(val).strip() == "":
                continue
            datos[h] = str(val).strip()

        fecha_hora = None
        if day is not None:
            try:
                fecha_hora = datetime(year, mes, day, hour or 0)
            except ValueError:
                day = None  # día imposible para el mes (OCR): no ubicable en el tiempo

        out.append({"dia": day, "fecha_hora": fecha_hora, "datos": datos,
                    "contenedores": contenedores, "placas": placas})
    return out
