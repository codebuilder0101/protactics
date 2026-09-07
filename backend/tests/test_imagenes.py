"""Validación de la miniatura de cada escaneo (imagenes.py).

Un registro cuya imagen NO es un escaneo de camión no es un escaneo válido y no
debe contarse en los totales. Aquí se comprueban las tres piezas por separado:

  • la clasificación pura (sin archivos),
  • la extracción con su ancla de fila (con un .xlsx construido al vuelo, y con
    el .xls real del cliente si está disponible),
  • el efecto sobre el RECUENTO al cargar, en modo sombra y en modo estricto.
"""
import io
import os

import openpyxl
import pytest
from openpyxl.drawing.image import Image as XLImage
from PIL import Image

import imagenes
import main
from models import EscaneosDiarios
from conftest import XLSX_CT


# ══════════════════════════════════════════════════════════════
#  Utilidades: miniaturas sintéticas
# ══════════════════════════════════════════════════════════════
def _png(ancho=192, alto=62, top=252, cuerpo=90) -> bytes:
    """Miniatura de prueba: franja superior a `top` y un cuerpo oscuro debajo.

    La franja superior es lo que mide `imagenes.TOP_FRAC`; el cuerpo solo existe
    para que la imagen no sea uniforme.
    """
    im = Image.new("RGB", (ancho, alto), (top, top, top))
    for y in range(int(alto * 0.4), int(alto * 0.9)):
        for x in range(int(ancho * 0.1), int(ancho * 0.9)):
            im.putpixel((x, y), (cuerpo, cuerpo, cuerpo))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _xlsx_con_imagenes(fechas, imgs) -> bytes:
    """Libro formato Standard con una miniatura anclada en la columna B.

    `imgs` es {índice_de_fecha: png}. La fecha i ocupa la fila de hoja i+2, así
    que su ancla es "B{i+2}" y su fila 0-based es i+1.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Fecha de creación", "Miniatura", "Nombre de Usuario"])
    for f in fechas:
        ws.append([f, None, "Juan"])
    for i, png in imgs.items():
        img = XLImage(io.BytesIO(png))
        ws.add_image(img, f"B{i + 2}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════
#  Clasificación (función pura)
# ══════════════════════════════════════════════════════════════
def test_clasificar_camion_normal():
    v, _ = imagenes.clasificar({"ancho": 192, "alto": 62, "top": 252.7})
    assert v == imagenes.CAMION


def test_clasificar_ancho_fuera_de_rango():
    v, motivo = imagenes.clasificar({"ancho": 339, "alto": 110, "top": 245.2})
    assert v == imagenes.NO_CAMION
    assert "ancho" in motivo


def test_clasificar_franja_superior_oscura():
    v, motivo = imagenes.clasificar({"ancho": 192, "alto": 62, "top": 204.1})
    assert v == imagenes.NO_CAMION
    assert "oscura" in motivo


def test_clasificar_franja_superior_saturada():
    v, _ = imagenes.clasificar({"ancho": 192, "alto": 62, "top": 255.0})
    assert v == imagenes.NO_CAMION


def test_imagen_ilegible_es_indeterminada_no_fallo():
    """REGLA DE ORO: lo que no se puede leer NUNCA se marca como fallo."""
    assert imagenes.medir(b"esto no es un png") is None
    v, _ = imagenes.clasificar(None)
    assert v == imagenes.INDETERMINADO
    assert v != imagenes.NO_CAMION


def test_los_limites_son_excluyentes():
    """Justo en el umbral todavía es un camión; pasado, no."""
    assert imagenes.clasificar({"ancho": int(imagenes.ANCHO_MAX), "alto": 62,
                                "top": 252.0})[0] == imagenes.CAMION
    assert imagenes.clasificar({"ancho": imagenes.ANCHO_MAX, "alto": 62,
                                "top": imagenes.TOP_MIN})[0] == imagenes.CAMION
    assert imagenes.clasificar({"ancho": 192, "alto": 62,
                                "top": imagenes.TOP_MIN - 0.1})[0] == imagenes.NO_CAMION


# ══════════════════════════════════════════════════════════════
#  Extracción y ancla de fila (.xlsx)
# ══════════════════════════════════════════════════════════════
def test_extrae_xlsx_y_ancla_a_la_fila_correcta():
    contenido = _xlsx_con_imagenes(
        ["2026-07-01 10:00", "2026-07-01 11:00", "2026-07-01 12:00"],
        {0: _png(), 2: _png(ancho=330, alto=106)},
    )
    imgs = imagenes.extraer(contenido, "x.xlsx", 0)
    assert set(imgs) == {1, 3}, "las anclas son filas 0-based de la hoja"
    assert imagenes.medir(imgs[1])["ancho"] == 192
    assert imagenes.medir(imgs[3])["ancho"] == 330


def test_evaluar_xlsx_marca_solo_la_mala():
    contenido = _xlsx_con_imagenes(
        ["2026-07-01 10:00", "2026-07-01 11:00", "2026-07-01 12:00"],
        {0: _png(), 1: _png(top=200), 2: _png()},
    )
    res = imagenes.evaluar(contenido, "x.xlsx", 0)
    assert res["excluidas"] == {2}          # fila de hoja 3 → 0-based 2
    assert res["resumen"]["con_imagen"] == 3
    assert res["resumen"][imagenes.NO_CAMION] == 1
    assert res["resumen"][imagenes.CAMION] == 2


def test_archivo_sin_imagenes_no_excluye_nada():
    from conftest import standard_xlsx
    res = imagenes.evaluar(standard_xlsx(["2026-07-01 10:00"]), "x.xlsx", 0)
    assert res["excluidas"] == set()
    assert res["resumen"]["con_imagen"] == 0


def test_contenido_corrupto_no_lanza():
    res = imagenes.evaluar(b"no soy un libro de excel", "x.xlsx", 0)
    assert res["excluidas"] == set()
    assert res["resumen"] == imagenes.resumen_vacio()


# ══════════════════════════════════════════════════════════════
#  Efecto sobre el RECUENTO al cargar
# ══════════════════════════════════════════════════════════════
FECHAS = ["2026-07-01 08:00", "2026-07-01 09:00", "2026-07-01 10:00"]


def _subir(client, contenido, nombre="SPR Buenaventura 01-07-2026.xlsx"):
    return client.post("/upload/0/2026/7",
                       files={"file": (nombre, contenido, XLSX_CT)})


def test_modo_estricto_descuenta_la_fila_mala(client, admin, monkeypatch):
    monkeypatch.setattr(main, "VALIDACION_IMAGENES", "estricto")
    contenido = _xlsx_con_imagenes(FECHAS, {0: _png(), 1: _png(top=200), 2: _png()})
    r = _subir(client, contenido)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imagenes"]["no_camion"] == 1
    assert body["imagenes"]["descartadas"] == 1
    assert body["total_escaneos"] == 2, "la fila no-camión no cuenta"
    # Y el total persistido tampoco la incluye.
    from database import SessionLocal
    db = SessionLocal()
    try:
        total = sum(e.total for e in db.query(EscaneosDiarios)
                    .filter_by(puerto_id=0, year=2026, mes=7).all())
    finally:
        db.close()
    assert total == 2


def test_modo_sombra_informa_pero_no_descuenta(client, admin, monkeypatch):
    monkeypatch.setattr(main, "VALIDACION_IMAGENES", "sombra")
    contenido = _xlsx_con_imagenes(FECHAS, {0: _png(), 1: _png(top=200), 2: _png()})
    r = _subir(client, contenido)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imagenes"]["no_camion"] == 1, "se detecta"
    assert body["imagenes"]["descartadas"] == 0, "pero no se aplica"
    assert body["total_escaneos"] == 3, "el recuento no cambia en modo sombra"


def test_modo_off_ni_siquiera_evalua(client, admin, monkeypatch):
    monkeypatch.setattr(main, "VALIDACION_IMAGENES", "off")
    contenido = _xlsx_con_imagenes(FECHAS, {0: _png(), 1: _png(top=200), 2: _png()})
    r = _subir(client, contenido)
    assert r.status_code == 200, r.text
    assert r.json()["imagenes"]["con_imagen"] == 0
    assert r.json()["total_escaneos"] == 3


def test_archivo_sin_miniaturas_cuenta_todo_en_estricto(client, admin, monkeypatch):
    """Los formatos que no traen imagen no se pueden evaluar: cuentan igual."""
    from conftest import standard_xlsx
    monkeypatch.setattr(main, "VALIDACION_IMAGENES", "estricto")
    r = _subir(client, standard_xlsx(FECHAS))
    assert r.status_code == 200, r.text
    assert r.json()["total_escaneos"] == 3
    assert r.json()["imagenes"]["descartadas"] == 0


def test_todas_las_filas_malas_da_error_explicito(client, admin, monkeypatch):
    monkeypatch.setattr(main, "VALIDACION_IMAGENES", "estricto")
    contenido = _xlsx_con_imagenes(
        FECHAS, {0: _png(top=200), 1: _png(top=200), 2: _png(top=200)})
    r = _subir(client, contenido)
    assert r.status_code == 400
    assert "imagen de escaneo de camión" in r.json()["detail"]


# ══════════════════════════════════════════════════════════════
#  Archivo real del cliente (si está disponible)
# ══════════════════════════════════════════════════════════════
# Export real de 288 filas. El propio libro trae la verdad: el cliente pintó de
# amarillo (color 13 de la paleta, RGB 255,255,0) las 8 filas erróneas. Estas
# son sus filas 0-based. La prueba se omite si el archivo no está en el equipo.
XLS_REAL = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "test", "1.xls")
FILAS_AMARILLAS = {98, 99, 146, 148, 164, 205, 225, 260}


@pytest.mark.skipif(not os.path.exists(XLS_REAL),
                    reason="hace falta test/1.xls (export real del cliente)")
def test_xls_real_coincide_con_las_filas_marcadas_por_el_cliente():
    contenido = open(XLS_REAL, "rb").read()
    res = imagenes.evaluar(contenido, "1.xls", 0)
    assert res["resumen"]["con_imagen"] == 288, "una miniatura por fila de datos"
    assert res["resumen"][imagenes.INDETERMINADO] == 0, "todas deben decodificar"
    assert res["excluidas"] == FILAS_AMARILLAS
