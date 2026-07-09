"""Snapshot ligero de los informes PDF: renderiza la página 1 a imagen y la
compara contra una base guardada (`tests/snapshots/`). Detecta regresiones de
layout/marca que las aserciones de estructura no ven (logo, gráficos, tablas).

Notas:
  • El sello de generación (fecha/hora) se neutraliza con monkeypatch para que la
    página sea determinista; el resto del PDF ya lo es dado el mismo dato.
  • La comparación tolera pequeñas diferencias de antialiasing (MAD < umbral).
  • Regenerar la base: `UPDATE_SNAPSHOTS=1 pytest tests/test_reportes_snapshot.py`.
"""
import os
from pathlib import Path

import pytest

pdfium = pytest.importorskip("pypdfium2")   # dep de pruebas; se salta si falta
from PIL import Image, ImageChops, ImageStat  # noqa: E402  (Pillow viene con fpdf2)

import database                               # noqa: E402
from reportes import datos as rep_datos, pdf as rep_pdf, branding  # noqa: E402
from models import EscaneosDiarios, EscaneosHorarios, Operadores    # noqa: E402

SNAP_DIR = Path(__file__).parent / "snapshots"
SCALE = 1.5           # A4 @ ~108 dpi → imagen liviana (~892×1263)
UMBRAL_MAD = 5.0      # diferencia media por canal tolerada (antialiasing)


def _seed():
    """Datos fijos y deterministas para los tres primeros puertos."""
    db = database.SessionLocal()
    try:
        for pid, base in [(0, 300), (1, 220), (2, 140)]:
            for dia in range(1, 31):
                db.add(EscaneosDiarios(puerto_id=pid, year=2026, mes=6, dia=dia,
                                       total=base + dia * 3 + pid * 7))
            for h in range(6, 20):
                db.add(EscaneosHorarios(puerto_id=pid, year=2026, mes=6, dia=1,
                                        hora=h, total=(h - 5) * 4 + pid))
            for nombre in ["Juan Perez", "Ana Gomez", "Luis Roa"]:
                db.add(Operadores(puerto_id=pid, year=2026, mes=6, dia=1,
                                  nombre=nombre, total=100 + pid * 10))
        # Mes previo (puerto 0) para que la variación mensual tenga base.
        for dia in range(1, 31):
            db.add(EscaneosDiarios(puerto_id=0, year=2026, mes=5, dia=dia,
                                   total=250 + dia * 2))
        db.commit()
    finally:
        db.close()


def _render_pagina1(pdf_bytes: bytes) -> Image.Image:
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return doc[0].render(scale=SCALE).to_pil().convert("RGB")
    finally:
        doc.close()


def _comparar(img: Image.Image, nombre: str):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    base_path = SNAP_DIR / nombre
    if os.getenv("UPDATE_SNAPSHOTS") or not base_path.exists():
        img.save(base_path)
        pytest.skip(f"snapshot base generada: {nombre}")
    base = Image.open(base_path).convert("RGB")
    assert img.size == base.size, (
        f"{nombre}: tamaño {img.size} != base {base.size} (cambió el layout)")
    mad = sum(ImageStat.Stat(ImageChops.difference(img, base)).mean) / 3.0
    assert mad < UMBRAL_MAD, (
        f"{nombre}: la página difiere de la base (MAD={mad:.2f} ≥ {UMBRAL_MAD}). "
        f"Revisa el cambio; si es intencional regenera con UPDATE_SNAPSHOTS=1.")


@pytest.fixture()
def _sello_fijo(monkeypatch):
    """Fija el sello de generación para que la página sea determinista."""
    monkeypatch.setattr(branding, "sello_generacion",
                        lambda *a, **k: "Generado (snapshot de prueba) - hora de Bogota")


def test_snapshot_informe_puerto(client, _sello_fijo):
    _seed()
    db = database.SessionLocal()
    try:
        datos = rep_datos.datos_puerto(db, 0, 2026, 6)
    finally:
        db.close()
    pdf_bytes = rep_pdf.informe_puerto(datos, "SPR Buenaventura", 2026, 6,
                                       actor_email="admin@protactics.co")
    _comparar(_render_pagina1(pdf_bytes), "informe_puerto.png")


def test_snapshot_informe_nacional(client, _sello_fijo):
    _seed()
    db = database.SessionLocal()
    try:
        datos = rep_datos.datos_nacional(db, 2026, 6, None)
    finally:
        db.close()
    pdf_bytes = rep_pdf.informe_nacional(datos, 2026, 6,
                                         actor_email="admin@protactics.co")
    _comparar(_render_pagina1(pdf_bytes), "informe_nacional.png")
