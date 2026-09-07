"""
PROTACTICS — Validación de la miniatura de cada escaneo
─────────────────────────────────────────────────────────────────
Un reporte de detalle trae, en la columna «Miniatura», la imagen del escaneo.
Cuando esa imagen NO es un escaneo de camión/contenedor (una foto de la cabina,
una banda oscura, una captura parcial), el registro NO es un escaneo válido y
no debe contarse en los totales del sistema.

Este módulo hace tres cosas, todas independientes de la base de datos:

  1. EXTRAER    las imágenes incrustadas y saber a qué FILA pertenece cada una.
                .xls  → OLE2 + registros Escher (ancla fila/columna por forma).
                .xlsx → ZIP  + xl/drawings/*.xml (ancla <xdr:from><xdr:row>).
  2. MEDIR      rasgos baratos y deterministas de cada imagen.
  3. CLASIFICAR camion / no_camion / indeterminado.

REGLA DE ORO: una imagen que no se puede leer NUNCA es un fallo. Se marca
«indeterminado» y el registro se cuenta como válido. Excluir por incertidumbre
subestima sistemáticamente la operación de un puerto y no sería defendible en
una auditoría.
"""
import io
import logging
import zipfile
import xml.etree.ElementTree as ET

log = logging.getLogger("protactics.imagenes")

# ── Veredictos ─────────────────────────────────────────────
CAMION        = "camion"          # escaneo válido → cuenta
NO_CAMION     = "no_camion"       # no es un escaneo de camión → NO cuenta
INDETERMINADO = "indeterminado"   # no se pudo evaluar → cuenta (y se revisa)

# ── Umbrales ───────────────────────────────────────────────
# Calibrados sobre un export real (288 filas; 8 marcadas en amarillo por el
# cliente). Cada uno se puede ajustar sin tocar la lógica.
#
#   ANCHO_MAX    Las miniaturas de un escaneo real miden 192–207 px de ancho;
#                las capturas que no lo son miden 316–339 px. Hueco de 109 px
#                sin nada en medio: es el rasgo MÁS fiable y el único con
#                margen holgado.
#   TOP_MIN      Brillo medio de la franja superior (el aire sobre el vehículo).
#                En un escaneo real es casi blanco y muy estable: mediana
#                252.73, y de 280 miniaturas válidas solo una baja de 250
#                (229.27). Las fotos oscuras dan 204.11 / 224.70 / 226.66.
#                Umbral centrado entre 226.66 y 229.27 → margen ±1.3.
#                ⚠ Es el margen ESTRECHO del sistema: valídalo con más archivos
#                antes de pasar de modo sombra a exclusión real.
#   TOP_MAX      Un marco con relleno blanco puro satura en 255.00 exacto,
#                frente a un máximo real de 254.08. Hoy es REDUNDANTE (las tres
#                miniaturas que lo activan ya sobran por ancho); se conserva por
#                si aparece una captura saturada de tamaño normal.
ANCHO_MAX = 250.0
TOP_MIN   = 228.0
TOP_MAX   = 254.5
TOP_FRAC  = 0.15     # fracción superior de la imagen que se promedia

# Firma PNG y terminador COMPLETO del chunk IEND (longitud 0 + tipo + CRC fijo).
# Se busca el terminador de 12 bytes y NO el literal "IEND": esos 4 bytes
# aparecen por azar dentro de los datos comprimidos, y cortar ahí produce un PNG
# truncado que los decodificadores devuelven EN BLANCO, sin lanzar error. Un
# blanco así es indistinguible de un escaneo fallido: sería un falso positivo.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_FIN = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"


# ══════════════════════════════════════════════════════════════
#  Medición y clasificación (funciones puras)
# ══════════════════════════════════════════════════════════════
def medir(png: bytes) -> dict | None:
    """Rasgos de una imagen PNG, o None si no se puede decodificar."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(png)) as im:
            im = im.convert("RGB")
            w, h = im.size
            if w <= 0 or h <= 0:
                return None
            filas = max(1, int(round(h * TOP_FRAC)))
            pix = im.crop((0, 0, w, filas)).convert("L").tobytes()
            if not pix:
                return None
            return {"ancho": w, "alto": h, "top": sum(pix) / len(pix)}
    except Exception as e:
        log.debug("Miniatura ilegible: %s", e)
        return None


def clasificar(m: dict | None) -> tuple[str, str]:
    """(veredicto, motivo) a partir de los rasgos. Función pura."""
    if not m:
        return INDETERMINADO, "imagen ilegible"
    if m["ancho"] > ANCHO_MAX:
        return NO_CAMION, f"ancho {m['ancho']}px fuera del rango de escaneo"
    if m["top"] < TOP_MIN:
        return NO_CAMION, f"franja superior oscura ({m['top']:.1f})"
    if m["top"] > TOP_MAX:
        return NO_CAMION, f"franja superior saturada ({m['top']:.1f})"
    return CAMION, "escaneo de camion"


# ══════════════════════════════════════════════════════════════
#  Extracción de los PNG incrustados
# ══════════════════════════════════════════════════════════════
def _blobs_png(data: bytes) -> list:
    """PNG incrustados, EN ORDEN de aparición (bytes exactos de cada uno).

    El orden importa: el almacén de imágenes los guarda de forma consecutiva y
    ese orden es el índice (blip) que referencian las formas del .xls.
    """
    out, i = [], 0
    while True:
        p = data.find(_PNG_MAGIC, i)
        if p < 0:
            return out
        f = data.find(_PNG_FIN, p + 8)
        if f < 0:
            return out
        out.append(data[p:f + len(_PNG_FIN)])
        i = f + len(_PNG_FIN)


# ── .xls (BIFF8 + Escher) ──────────────────────────────────
def _escher(buf: bytes, ini: int = 0, fin=None):
    """Recorre los registros Escher, entrando en los contenedores.

    Cabecera de 8 bytes: verInstance(2) | tipo(2) | longitud(4), todo LE.
    Es contenedor cuando los 4 bits bajos de verInstance valen 0xF.
    Produce (tipo, instancia, offset_datos, longitud_datos).
    """
    if fin is None:
        fin = len(buf)
    pos = ini
    while pos + 8 <= fin:
        v = int.from_bytes(buf[pos:pos + 2], "little")
        tipo = int.from_bytes(buf[pos + 2:pos + 4], "little")
        largo = int.from_bytes(buf[pos + 4:pos + 8], "little")
        d0 = pos + 8
        if d0 + largo > fin:
            return
        yield tipo, v >> 4, d0, largo
        if (v & 0x0F) == 0x0F:                      # contenedor → sus hijos
            yield from _escher(buf, d0, d0 + largo)
        pos = d0 + largo


def _formas_xls(dibujo: bytes) -> dict:
    """{blip_index: fila_0based} leyendo cada forma del flujo de dibujo.

    De cada contenedor de forma (0xF004) se toman dos cosas:
      • OPT (0xF00B), propiedad 0x0104 «pib» = índice de la imagen (1-based).
      • ClientAnchor (0xF010), campo row1 = fila donde está anclada.

    Si dos formas reutilizaran la MISMA imagen, aquí solo queda la última fila y
    la otra se queda sin veredicto. Es el lado seguro del error: una fila sin
    veredicto cuenta como válida, nunca como fallo.
    """
    fila_de = {}
    for tipo, _inst, d0, dl in _escher(dibujo):
        if tipo != 0xF004:                          # SpContainer
            continue
        pib = fila = None
        for t2, inst2, q0, ql in _escher(dibujo, d0, d0 + dl):
            if t2 == 0xF00B:                        # OPT
                for k in range(inst2):
                    o = q0 + k * 6
                    if o + 6 > q0 + ql:
                        break
                    opid = int.from_bytes(dibujo[o:o + 2], "little") & 0x3FFF
                    if opid == 0x0104:
                        pib = int.from_bytes(dibujo[o + 2:o + 6], "little")
            elif t2 == 0xF010 and ql >= 8:          # ClientAnchor
                fila = int.from_bytes(dibujo[q0 + 6:q0 + 8], "little")
        if pib is not None and fila is not None:
            fila_de[pib] = fila
    return fila_de


def _biff_concat(flujo: bytes, objetivo: int, hoja=None) -> bytes:
    """Reensambla el contenido de los registros `objetivo` + sus CONTINUE.

    Devuelve SOLO los datos, SIN las cabeceras BIFF de 4 bytes. Esto es
    imprescindible y no cosmético: un registro BIFF no puede pasar de ~8 KB, así
    que tanto el dibujo como el almacén de imágenes se parten en registros
    CONTINUE. Si se leyera el flujo en crudo, la cabecera de cada CONTINUE
    quedaría INCRUSTADA dentro de los datos comprimidos de un PNG y lo
    corrompería (los decodificadores tolerantes lo aceptan y devuelven píxeles
    basura, sin avisar). Reensamblando así, los 288 PNG del archivo de
    referencia decodifican con su CRC correcto.

    `hoja` None = no filtrar (el almacén de imágenes vive en la subcorriente
    global). Con un número, se limita a esa hoja: las subcorrientes se delimitan
    con BOF (0x0809), la primera es la global y las siguientes son las hojas, en
    el mismo orden que expone xlrd.

    ⚠ Particularidad de BIFF8: pasadas las primeras formas, Excel deja de emitir
    un MSODRAWING por forma y continúa el dibujo en registros CONTINUE
    INTERCALADOS con los OBJ (0x005D) de cada objeto. Un OBJ no interrumpe esa
    continuación, así que se trata como transparente; si se dejara que
    reiniciara el registro «dueño» se perderían todas las formas a partir de ahí
    (en el archivo de referencia, 228 de 288).
    """
    buf = bytearray()
    pos, sub, previo, n = 0, -1, 0, len(flujo)
    while pos + 4 <= n:
        tipo = int.from_bytes(flujo[pos:pos + 2], "little")
        largo = int.from_bytes(flujo[pos + 2:pos + 4], "little")
        d0 = pos + 4
        if d0 + largo > n:
            break
        if tipo == 0x0809:                          # BOF → nueva subcorriente
            sub += 1
        vale = hoja is None or sub - 1 == hoja      # sub 0 = global, hoja 0 = sub 1
        if tipo == objetivo:
            previo = tipo
            if vale:
                buf += flujo[d0:d0 + largo]
        elif tipo == 0x003C:                        # CONTINUE
            if previo == objetivo and vale:
                buf += flujo[d0:d0 + largo]
        elif tipo != 0x005D:                        # OBJ: transparente (ver arriba)
            previo = tipo
        pos = d0 + largo
    return bytes(buf)


def _imagenes_xls(contenido: bytes, hoja: int) -> dict:
    """{fila_0based: png} de un libro .xls."""
    import olefile
    if not olefile.isOleFile(io.BytesIO(contenido)):
        return {}
    ole = olefile.OleFileIO(io.BytesIO(contenido))
    try:
        nombre = next((n for n in ("Workbook", "Book") if ole.exists(n)), None)
        if nombre is None:
            return {}
        flujo = ole.openstream(nombre).read()
    finally:
        ole.close()

    # Las imágenes viven en el almacén (MSODRAWINGGROUP, subcorriente global) y
    # las anclas en el dibujo de la hoja (MSODRAWING). Ambos se reensamblan.
    pngs = _blobs_png(_biff_concat(flujo, 0x00EB))
    if not pngs:
        return {}
    fila_de = _formas_xls(_biff_concat(flujo, 0x00EC, hoja))
    return {fila_de[i + 1]: png for i, png in enumerate(pngs)
            if (i + 1) in fila_de}


# ── .xlsx (ZIP + DrawingML) ────────────────────────────────
_NS_XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
_NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_NS_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _rels(z: zipfile.ZipFile, parte: str) -> dict:
    """{Id: Target} del .rels de una parte del paquete."""
    carpeta, _, base = parte.rpartition("/")
    ruta = f"{carpeta}/_rels/{base}.rels" if carpeta else f"_rels/{base}.rels"
    try:
        raiz = ET.fromstring(z.read(ruta))
    except (KeyError, ET.ParseError):
        return {}
    return {r.get("Id"): r.get("Target")
            for r in raiz.findall(f"{_NS_PR}Relationship")}


def _resolver(base: str, destino: str) -> str:
    """Resuelve un Target relativo (admite ../) contra la carpeta de la parte."""
    if destino.startswith("/"):
        return destino.lstrip("/")
    partes = base.rpartition("/")[0].split("/") if "/" in base else []
    for tramo in destino.split("/"):
        if tramo == "..":
            if partes:
                partes.pop()
        elif tramo not in ("", "."):
            partes.append(tramo)
    return "/".join(partes)


def _imagenes_xlsx(contenido: bytes, hoja: int) -> dict:
    """{fila_0based: png} de un libro .xlsx."""
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        nombres = set(z.namelist())
        libro = "xl/workbook.xml"
        if libro not in nombres:
            return {}

        raiz = ET.fromstring(z.read(libro))
        hojas = raiz.findall(f"{_NS_S}sheets/{_NS_S}sheet")
        if hoja >= len(hojas):
            return {}
        rel_libro = _rels(z, libro)
        destino_hoja = rel_libro.get(hojas[hoja].get(f"{_NS_R}id"))
        if not destino_hoja:
            return {}
        parte_hoja = _resolver(libro, destino_hoja)
        if parte_hoja not in nombres:
            return {}

        # hoja → dibujo
        destino_dib = next((t for t in _rels(z, parte_hoja).values()
                            if t and "drawing" in t), None)
        if not destino_dib:
            return {}
        parte_dib = _resolver(parte_hoja, destino_dib)
        if parte_dib not in nombres:
            return {}

        rel_dib = _rels(z, parte_dib)
        raiz_dib = ET.fromstring(z.read(parte_dib))

        out = {}
        for etiqueta in ("twoCellAnchor", "oneCellAnchor"):
            for anc in raiz_dib.findall(f"{_NS_XDR}{etiqueta}"):
                desde = anc.find(f"{_NS_XDR}from/{_NS_XDR}row")
                blip = anc.find(f".//{_NS_A}blip")
                if desde is None or blip is None:
                    continue
                destino_img = rel_dib.get(blip.get(f"{_NS_R}embed"))
                if not destino_img:
                    continue
                medio = _resolver(parte_dib, destino_img)
                if medio in nombres:
                    try:
                        out[int(desde.text)] = z.read(medio)
                    except (ValueError, TypeError, KeyError):
                        continue
        return out


# ══════════════════════════════════════════════════════════════
#  API pública
# ══════════════════════════════════════════════════════════════
def extraer(contenido: bytes, filename: str, hoja: int = 0) -> dict:
    """{fila_0based: png} del libro. {} si el formato no trae imágenes."""
    try:
        if (filename or "").lower().endswith(".xls"):
            return _imagenes_xls(contenido, hoja)
        return _imagenes_xlsx(contenido, hoja)
    except Exception as e:
        log.error("No se pudieron extraer las miniaturas de %s: %s", filename, e)
        return {}


def resumen_vacio() -> dict:
    """Resumen a cero: lo usa quien no evalúa imágenes (modo off, sin bytes)."""
    return {"con_imagen": 0, CAMION: 0, NO_CAMION: 0, INDETERMINADO: 0}


def evaluar(contenido: bytes, filename: str, hoja: int = 0) -> dict:
    """Clasifica la miniatura de cada fila del archivo.

    Devuelve:
      {"filas":     {fila_0based: {veredicto, motivo, ancho, alto, top}},
       "excluidas": {filas con veredicto no_camion},
       "resumen":   {con_imagen, camion, no_camion, indeterminado}}

    Nunca lanza: ante cualquier fallo devuelve un resultado vacío y el archivo
    se procesa como hasta ahora (todas las filas cuentan).
    """
    filas, excluidas, resumen = {}, set(), resumen_vacio()
    try:
        for fila, png in extraer(contenido, filename, hoja).items():
            m = medir(png)
            veredicto, motivo = clasificar(m)
            filas[fila] = {
                "veredicto": veredicto, "motivo": motivo,
                "ancho": m["ancho"] if m else None,
                "alto": m["alto"] if m else None,
                "top": round(m["top"], 1) if m else None,
            }
            resumen["con_imagen"] += 1
            resumen[veredicto] += 1
            if veredicto == NO_CAMION:
                excluidas.add(fila)
    except Exception as e:
        log.error("Fallo al evaluar miniaturas de %s: %s", filename, e)
        return {"filas": {}, "excluidas": set(), "resumen": resumen_vacio()}
    return {"filas": filas, "excluidas": excluidas, "resumen": resumen}
