"""Composición de los informes PDF con fpdf2.

Marca centralizada en `branding`. Los gráficos se dibujan con primitivos de la
propia librería (rectángulos/líneas), sin matplotlib (RNF-1.11). Todo el texto se
sanea a latin-1 (`_t`) porque las fuentes core de fpdf2 no son Unicode: así ni un
carácter suelto (— · ✓) rompe la generación.
"""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from . import branding

# ── Saneo de texto a latin-1 (fuentes core) ────────────────
_REPL = {
    "—": "-", "–": "-", "‒": "-", "−": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "•": "-", "✓": "OK", "✗": "X",
    "⚠": "!", " ": " ", " ": " ", " ": " ",
}


def _t(s) -> str:
    s = str(s)
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _n(x) -> str:
    """Entero con separador de miles estilo es-CO (punto)."""
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(x)


def _pct(v) -> str:
    """Porcentaje de variación con signo, o 'n/d' si es None."""
    if v is None:
        return "n/d"
    return f"{v:+.1f}%".replace(".", ",")


def _pctval(v) -> str:
    """Porcentaje sin signo (cuota)."""
    if v is None:
        return "n/d"
    return f"{v:.1f}%".replace(".", ",")


def _trunc(s, n) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


# ══════════════════════════════════════════════════════════════
class _Informe(FPDF):
    def __init__(self, subtitulo: str, actor_email=None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._subtitulo = subtitulo
        # Sello fijado una vez → idéntico en todas las páginas (RNF-1.15).
        self._sello = branding.sello_generacion(actor_email)
        self.set_title(_t(branding.TITULO))
        self.set_author(_t(branding.MARCA))
        self.set_creator(_t(branding.MARCA))
        self.set_margins(12, 12, 12)
        self.set_auto_page_break(auto=True, margin=16)

    # ── Encabezado / pie ───────────────────────────────────
    def header(self):
        # Logo a la izquierda (respetando su proporción); título/subtítulo a la
        # derecha del logo. Si no hay logo o falla, el título ocupa desde el margen.
        tx = self.l_margin
        lp = branding.logo_path()
        if lp:
            try:
                alto = 11
                size = branding.logo_size()
                ancho = (alto * size[0] / size[1]) if size and size[1] else 40.0
                ancho = min(ancho, 55)                     # tope de seguridad
                self.image(lp, x=self.l_margin, y=9, h=alto)
                tx = self.l_margin + ancho + 6
            except Exception:
                tx = self.l_margin
        avail = self.l_margin + self.epw - tx
        self.set_xy(tx, 10)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*branding.AZUL)
        self.cell(avail, 6, _t(branding.TITULO), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(tx, 16)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*branding.GRIS)
        self.cell(avail, 5, _t(self._subtitulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*branding.AZUL)
        self.set_line_width(0.4)
        self.line(self.l_margin, 24, self.l_margin + self.epw, 24)
        self.set_y(28)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*branding.AZUL_CLARO)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.l_margin + self.epw, self.get_y())
        self.ln(1)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*branding.GRIS)
        self.multi_cell(0, 3.4, _t(branding.PIE_CONFIDENCIAL + "\n" + self._sello),
                        align="C", new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_y(-14)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 3.4, _t(f"Pág. {self.page_no()}"), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.TOP)

    # ── Utilidades de layout ───────────────────────────────
    def asegurar(self, alto: float):
        """Salta de página si no caben `alto` mm antes del pie."""
        if self.get_y() + alto > self.page_break_trigger:
            self.add_page()

    def titulo_seccion(self, txt: str):
        self.asegurar(14)
        self.ln(1)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*branding.AZUL)
        self.cell(0, 6, _t(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*branding.AZUL_CLARO)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(self.l_margin, y, self.l_margin + self.epw, y)
        self.ln(2)

    def parrafo(self, txt: str, size=9, color=None):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*(color or branding.NEGRO))
        self.multi_cell(0, 4.6, _t(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def kpi_grid(self, items, por_fila=4):
        gap, ch = 3, 15
        cw = (self.epw - gap * (por_fila - 1)) / por_fila
        for start in range(0, len(items), por_fila):
            fila = items[start:start + por_fila]
            self.asegurar(ch + gap)
            top = self.get_y()
            for j, (label, value) in enumerate(fila):
                x = self.l_margin + j * (cw + gap)
                self.set_fill_color(*branding.GRIS_SUAVE)
                self.set_draw_color(*branding.AZUL_CLARO)
                self.set_line_width(0.2)
                self.rect(x, top, cw, ch, style="DF")
                self.set_xy(x + 2, top + 2)
                self.set_font("Helvetica", "", 7)
                self.set_text_color(*branding.GRIS)
                self.cell(cw - 4, 3.5, _t(_trunc(label, 26)),
                          new_x=XPos.LMARGIN, new_y=YPos.TOP)
                self.set_xy(x + 2, top + 6.6)
                self.set_font("Helvetica", "B", 12.5)
                self.set_text_color(*branding.AZUL)
                self.cell(cw - 4, 6, _t(value), new_x=XPos.LMARGIN, new_y=YPos.TOP)
            self.set_y(top + ch + gap)

    def tabla(self, headers, rows, widths, aligns=None):
        aligns = aligns or ["L"] * len(headers)
        self.asegurar(6.5 + 5.6)
        self.set_font("Helvetica", "B", 8.5)
        self.set_fill_color(*branding.AZUL)
        self.set_text_color(*branding.BLANCO)
        for h, w, a in zip(headers, widths, aligns):
            self.cell(w, 6.5, _t(h), align=a, fill=True,
                      new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.ln(6.5)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*branding.NEGRO)
        fill = False
        for row in rows:
            self.asegurar(5.6)
            self.set_fill_color(*(branding.GRIS_SUAVE if fill else branding.BLANCO))
            for val, w, a in zip(row, widths, aligns):
                self.cell(w, 5.6, _t(val), align=a, fill=True,
                          new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.ln(5.6)
            fill = not fill
        self.ln(1)

    def grafico_barras(self, labels, values, alto=42, etiqueta_cada=1,
                       color=None, unidad=""):
        color = color or branding.AZUL
        self.asegurar(alto + 4)
        x0, w, top = self.l_margin, self.epw, self.get_y()
        label_h = 5
        plot_h = alto - label_h
        baseline = top + plot_h
        n = max(1, len(values))
        mx = max((v or 0) for v in values) if values else 0
        mx = mx if mx > 0 else 1
        slot = w / n
        bar_w = min(slot * 0.62, 14)
        # referencia del máximo
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*branding.GRIS)
        self.set_xy(x0, top - 1)
        ref = f"máx {_n(mx)}" + (f" {unidad}" if unidad else "")
        self.cell(w, 3, _t(ref), align="R", new_x=XPos.LMARGIN, new_y=YPos.TOP)
        # eje base
        self.set_draw_color(*branding.GRIS)
        self.set_line_width(0.2)
        self.line(x0, baseline, x0 + w, baseline)
        # barras
        self.set_fill_color(*color)
        for i, v in enumerate(values):
            bh = ((v or 0) / mx) * (plot_h - 1)
            if bh > 0:
                bx = x0 + i * slot + (slot - bar_w) / 2
                self.rect(bx, baseline - bh, bar_w, bh, style="F")
        # etiquetas
        self.set_font("Helvetica", "", 6)
        self.set_text_color(*branding.GRIS)
        last = len(labels) - 1
        for i, lab in enumerate(labels):
            if etiqueta_cada > 1 and (i % etiqueta_cada) and i != last:
                continue
            self.set_xy(x0 + i * slot, baseline + 0.5)
            self.cell(slot, label_h, _t(_trunc(str(lab), 12)), align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_y(top + alto + 2)

    def grafico_linea(self, labels, values, alto=42, etiqueta_cada=1, color=None):
        color = color or branding.AZUL
        self.asegurar(alto + 4)
        x0, w, top = self.l_margin, self.epw, self.get_y()
        label_h = 5
        plot_h = alto - label_h
        baseline = top + plot_h
        n = len(values)
        mx = max((v or 0) for v in values) if values else 0
        mx = mx if mx > 0 else 1
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*branding.GRIS)
        self.set_xy(x0, top - 1)
        self.cell(w, 3, _t(f"máx {_n(mx)}"), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_draw_color(*branding.GRIS)
        self.set_line_width(0.2)
        self.line(x0, baseline, x0 + w, baseline)
        if n == 1:
            xs = [x0 + w / 2]
        else:
            xs = [x0 + w * i / (n - 1) for i in range(n)]
        ys = [baseline - ((v or 0) / mx) * (plot_h - 1) for v in values]
        self.set_draw_color(*color)
        self.set_line_width(0.5)
        for i in range(1, n):
            self.line(xs[i - 1], ys[i - 1], xs[i], ys[i])
        self.set_fill_color(*color)
        for i in range(n):
            self.rect(xs[i] - 0.6, ys[i] - 0.6, 1.2, 1.2, style="F")
        self.set_font("Helvetica", "", 6)
        self.set_text_color(*branding.GRIS)
        last = n - 1
        for i, lab in enumerate(labels):
            if etiqueta_cada > 1 and (i % etiqueta_cada) and i != last:
                continue
            self.set_xy(xs[i] - 8, baseline + 0.5)
            self.cell(16, label_h, _t(_trunc(str(lab), 8)), align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_y(top + alto + 2)

    def mensaje_sin_datos(self, year, mes):
        self.ln(30)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*branding.GRIS)
        self.cell(0, 10, _t(f"Sin cargas para {branding.nombre_mes(mes)} {year}"),
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, _t("No hay escaneos registrados para este período."),
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ══════════════════════════════════════════════════════════════
#  Informes públicos
# ══════════════════════════════════════════════════════════════
def informe_puerto(datos: dict, nombre: str, year: int, mes: int,
                   actor_email=None) -> bytes:
    sub = f"{nombre} · {branding.nombre_mes(mes)} {year}"
    pdf = _Informe(sub, actor_email)
    pdf.add_page()

    if datos.get("sin_datos"):
        pdf.mensaje_sin_datos(year, mes)
        return bytes(pdf.output())

    v = datos["variacion"]
    tz = datos["trazabilidad"]
    kpis = [
        ("Total de escaneos", _n(datos["total"])),
        ("Promedio diario", _n(datos["promedio_diario"])),
        ("Días activos", _n(datos["dias_activos"])),
        ("Operadores", _n(datos["operadores_distintos"])),
    ]
    if tz["contenedores"] or tz["placas"]:
        kpis += [
            ("Contenedores", _n(tz["contenedores"])),
            ("Conten. válidos", _n(tz["contenedores_validos"])),
            ("Placas", _n(tz["placas"])),
        ]
    if datos["dia_pico"]:
        p = datos["dia_pico"]
        kpis.append(("Día pico", f"{p['dia']} ({_n(p['total'])})"))

    pdf.titulo_seccion("Indicadores del mes")
    pdf.kpi_grid(kpis)
    pdf.parrafo(
        f"Variación mensual: {_pct(v['mensual']['delta_pct'])}      "
        f"Variación interanual: {_pct(v['interanual']['delta_pct'])}",
        size=9, color=branding.GRIS)

    pdf.titulo_seccion("Escaneos por día")
    pdf.grafico_barras([x["dia"] for x in datos["serie_diaria"]],
                       [x["total"] for x in datos["serie_diaria"]],
                       alto=42, etiqueta_cada=2, unidad="escaneos")

    pdf.titulo_seccion("Distribución por hora del día")
    pdf.grafico_barras([f"{x['hora']:02d}" for x in datos["horaria"]],
                       [x["total"] for x in datos["horaria"]],
                       alto=38, etiqueta_cada=2, color=branding.AZUL_MEDIO)
    if any(x["total"] for x in datos["horaria"]):
        hp = max(datos["horaria"], key=lambda x: x["total"])
        pdf.parrafo(f"Hora pico: {hp['hora']:02d}:00 h con {_n(hp['total'])} escaneos.",
                    size=8.5, color=branding.GRIS)

    if datos["operadores"]:
        pdf.titulo_seccion("Productividad por operador")
        rows = [[o["nombre"], _n(o["total"])] for o in datos["operadores"][:15]]
        pdf.tabla(["Operador", "Escaneos"], rows, [150, 40], ["L", "R"])

    pdf.titulo_seccion("Alertas de volumen")
    if datos["alertas"]:
        rows = [[a["tipo"], a["severidad"], branding.fecha_bogota(a["fecha"]),
                 _trunc(a["mensaje"], 58)] for a in datos["alertas"]]
        pdf.tabla(["Tipo", "Severidad", "Fecha", "Mensaje"],
                  rows, [34, 24, 24, 108], ["L", "L", "L", "L"])
    else:
        pdf.parrafo("Sin alertas de volumen abiertas para el período.",
                    color=branding.GRIS)

    return bytes(pdf.output())


def informe_nacional(datos: dict, year: int, mes: int, actor_email=None) -> bytes:
    sub = f"Consolidado nacional · {branding.nombre_mes(mes)} {year}"
    pdf = _Informe(sub, actor_email)
    pdf.add_page()

    if datos.get("sin_datos"):
        pdf.mensaje_sin_datos(year, mes)
        return bytes(pdf.output())

    v = datos["variacion"]
    kpis = [
        ("Escaneos nacionales", _n(datos["total_nacional"])),
        ("Promedio diario", _n(datos["promedio_diario"])),
        ("Puertos con datos", _n(datos["puertos_con_dato"])),
        ("Operadores", _n(datos["operadores_distintos"])),
        ("Contenedores", _n(datos["contenedores"])),
        ("Var. mensual", _pct(v["mensual"]["delta_pct"])),
        ("Var. interanual", _pct(v["interanual"]["delta_pct"])),
    ]
    pdf.titulo_seccion("Indicadores nacionales del mes")
    pdf.kpi_grid(kpis)
    if datos["puertos_sin_carga"]:
        pdf.parrafo("Puertos sin carga del mes: "
                    + ", ".join(datos["puertos_sin_carga"]),
                    size=8.5, color=branding.GRIS)

    pdf.titulo_seccion("Ranking de puertos por escaneos")
    rows = [[str(r["posicion"]), r["nombre"], _n(r["total"]), _pctval(r["cuota_pct"])]
            for r in datos["ranking"]]
    pdf.tabla(["#", "Puerto", "Escaneos", "Cuota"],
              rows, [12, 90, 50, 38], ["C", "L", "R", "R"])
    pdf.grafico_barras([r["nombre"] for r in datos["ranking"]],
                       [r["total"] for r in datos["ranking"]],
                       alto=45, etiqueta_cada=1, unidad="escaneos")

    pdf.titulo_seccion(f"Evolución mensual del año {year}")
    pdf.grafico_linea([branding.MESES[x["mes"] - 1][:3] for x in datos["serie_anual"]],
                      [x["total"] for x in datos["serie_anual"]],
                      alto=42, etiqueta_cada=1)

    pdf.titulo_seccion("Detalle por puerto")
    rows = [[p["nombre"], _n(p["total"]), _n(p["promedio_diario"]), _n(p["operadores"]),
             _n(p["contenedores"]), _n(p["placas"]), _n(p["alertas"])]
            for p in datos["por_puerto"]]
    pdf.tabla(["Puerto", "Escaneos", "Prom/día", "Oper.", "Conten.", "Placas", "Alertas"],
              rows, [46, 28, 24, 20, 24, 24, 24],
              ["L", "R", "R", "R", "R", "R", "R"])

    return bytes(pdf.output())
