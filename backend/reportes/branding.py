"""Marca (branding) centralizada de los informes PDF.

Fuente única de verdad para título, logo, paleta y pie. Cambiar la marca aquí no
exige tocar la composición del PDF (RNF-1.16). Valores confirmados por el cliente.
"""
import os
from datetime import datetime, timedelta, timezone

# ── Textos ─────────────────────────────────────────────────
TITULO = "Informe de Gestión — Sistema de Inspección No Intrusiva"
MARCA = "Protactics"
PIE_CONFIDENCIAL = "Información confidencial – Prohibida su reproducción"
NOTA_AUTOMATICA = "Documento generado automáticamente"

# ── Paleta (azul corporativo del logo + blanco) ────────────
# Primario #002069: muestreado directamente del logo del cliente
# (frontend/assets/protactics-logo.jpeg). Se mezcla con blanco para las tintas.
AZUL       = (0, 32, 105)       # #002069 — primario (navy del logo)
AZUL_MEDIO = (30, 60, 134)      # #1E3C86
AZUL_CLARO = (90, 106, 170)     # #5A6AAA
GRIS       = (110, 116, 140)    # texto secundario
GRIS_SUAVE = (244, 246, 251)    # relleno de filas alternas
NEGRO      = (24, 26, 34)       # texto principal
BLANCO     = (255, 255, 255)

# Rampa monocroma de azules (navy → blanco) para series de gráficos (RNF-1.16).
RAMPA = [(0, 32, 105), (30, 60, 134), (74, 99, 168),
         (138, 155, 203), (195, 203, 230)]

# Color por severidad de alerta (se mezcla con la marca, no la reemplaza).
SEVERIDAD_COLOR = {
    "critical": (192, 57, 43),
    "warning":  (196, 145, 40),
    "info":     (58, 70, 166),
}

# ── Zona horaria de presentación: América/Bogotá (UTC−5, sin DST) ──
TZ_BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# ── Logo ───────────────────────────────────────────────────
# Se busca un logo dedicado en frontend/assets. `favicon.png` NO se usa (es un
# gráfico oscuro que no encaja sobre fondo blanco). Si no existe un logo apto,
# el encabezado cae a un texto con la marca (sin romper).
_ASSETS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "assets"))
# PNG transparente primero (se integra sin recuadro sobre el fondo blanco del PDF);
# el JPEG queda como respaldo.
_LOGO_CANDIDATOS = ("protactics-logo.png", "protactics-logo.jpeg",
                    "protactics-logo.jpg", "logo-protactics.png", "logo.png")


def logo_path():
    """Ruta a un logo apto para el PDF, o None si no hay ninguno disponible."""
    for nombre in _LOGO_CANDIDATOS:
        p = os.path.join(_ASSETS_DIR, nombre)
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            return p
    return None


def logo_size():
    """(ancho, alto) en píxeles del logo, o None si no hay logo/PIL. Sirve para
    respetar la proporción del logo en el encabezado sin deformarlo."""
    p = logo_path()
    if not p:
        return None
    try:
        from PIL import Image
        with Image.open(p) as im:
            return im.size
    except Exception:
        return None


def nombre_mes(mes: int) -> str:
    return MESES[mes - 1] if 1 <= mes <= 12 else str(mes)


def _a_bogota(dt: datetime) -> datetime:
    """Convierte un datetime (UTC naive o aware) a hora de Bogotá."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)   # utcnow() es naive → se asume UTC
    return dt.astimezone(TZ_BOGOTA)


def fecha_bogota(dt) -> str:
    """Fecha 'YYYY-MM-DD' en hora de Bogotá, o '' si dt es None."""
    if dt is None:
        return ""
    return _a_bogota(dt).strftime("%Y-%m-%d")


def sello_generacion(actor_email=None, ahora_utc: datetime = None) -> str:
    """Línea de sello: fecha/hora de generación en Bogotá + actor. Determinista
    salvo la propia hora (RNF-1.15: es lo único que puede variar entre dos PDFs
    del mismo período)."""
    ahora_utc = ahora_utc or datetime.utcnow()
    stamp = _a_bogota(ahora_utc).strftime("%Y-%m-%d %H:%M")
    quien = f" · {actor_email}" if actor_email else ""
    return f"Generado el {stamp} (hora de Bogotá){quien} · {NOTA_AUTOMATICA}"
