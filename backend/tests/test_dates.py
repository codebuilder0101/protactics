"""Lectura de fechas: la columna de fecha llega en varios formatos reales."""
from parsers.dates import to_ymdh


def test_fecha_us_m_d_y():
    # Export Rapiscan de SPB: "6/16/2026 11:57:07 P. M." es M/D/Y (16 de junio),
    # no D/M/Y. El mes no puede ser 16; debe corregirse a (2026, 6, 16).
    y, mo, d, h = to_ymdh("6/16/2026 11:57:07 P. M.")
    assert (y, mo, d) == (2026, 6, 16)
    assert h == 23                      # 11 P. M. → 23h


def test_fecha_dmy_se_respeta_cuando_es_valida():
    # "16/06/2026" es inequívocamente D/M/Y → 16 de junio.
    assert to_ymdh("16/06/2026 09:00")[:3] == (2026, 6, 16)


def test_fecha_ambigua_se_mantiene_dmy():
    # "01/03/2026": ambos ≤ 12 → se conserva D/M/Y (1 de marzo).
    assert to_ymdh("01/03/2026 05:02")[:3] == (2026, 3, 1)


def test_fecha_iso():
    assert to_ymdh("2026-06-16 23:56:00")[:3] == (2026, 6, 16)
