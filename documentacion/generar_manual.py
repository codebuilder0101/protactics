"""Genera el Manual de Usuario de PROTACTICS en PDF.

Reutiliza la paleta y el logo de la marca ya definidos para los informes, de modo
que el manual y los informes que el sistema emite se vean como una misma familia.

Regla de redacción impuesta por el cliente: el texto NO puede contener guiones ni
paréntesis. `T()` lo verifica en tiempo de generación y falla si algo se cuela.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from reportes import branding as B

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "Manual de Usuario PROTACTICS.pdf")

PROHIBIDOS = ("-", "(", ")", "—", "–", "‒", "−")


def T(s: str) -> str:
    """Valida la regla de redacción y saneа el texto a latin-1."""
    for ch in PROHIBIDOS:
        if ch in s:
            raise ValueError(f"Carácter prohibido {ch!r} en: {s[:90]}")
    return s.encode("latin-1", "replace").decode("latin-1")


class Manual(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(True, margin=20)
        self.set_margins(20, 18, 20)
        self.portada_activa = False
        self.set_title("Manual de Usuario PROTACTICS")

    # ── Encabezado y pie ───────────────────────────────────
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("helvetica", "", 7.5)
        self.set_text_color(*B.GRIS)
        self.cell(0, 5, T("PROTACTICS  ·  Manual de Usuario"), align="L")
        self.cell(0, 5, T("Sistema de Inspección No Intrusiva"), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*B.AZUL_CLARO)
        self.set_line_width(0.3)
        self.line(20, self.get_y() + 1, 190, self.get_y() + 1)
        self.ln(6)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font("helvetica", "", 7)
        self.set_text_color(*B.GRIS)
        self.cell(0, 5, T("Información confidencial. Prohibida su reproducción."), align="L")
        self.cell(0, 5, T(f"Página {self.page_no()} de {{nb}}"), align="R")

    # ── Bloques de contenido ───────────────────────────────
    def h1(self, num, txt):
        self.add_page()
        self.set_fill_color(*B.AZUL)
        self.set_text_color(*B.BLANCO)
        self.set_font("helvetica", "B", 13)
        self.cell(0, 11, T(f"   {num}.  {txt.upper()}"), fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self.set_text_color(*B.NEGRO)

    def h2(self, txt):
        self._espacio(16)
        self.ln(2)
        self.set_font("helvetica", "B", 10.5)
        self.set_text_color(*B.AZUL)
        self.multi_cell(0, 6, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*B.NEGRO)
        self.ln(1.5)

    def p(self, txt, size=9.5):
        self.set_font("helvetica", "", size)
        self.set_text_color(*B.NEGRO)
        self.multi_cell(0, 5.2, T(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2.2)

    def puntos(self, items):
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*B.NEGRO)
        for it in items:
            self._espacio(10)
            x = self.get_x()
            self.set_text_color(*B.AZUL_MEDIO)
            self.cell(5, 5.2, T("·"))
            self.set_text_color(*B.NEGRO)
            self.multi_cell(0, 5.2, T(it), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_x(x)
        self.ln(2.2)

    def pasos(self, items):
        self.set_font("helvetica", "", 9.5)
        for i, it in enumerate(items, 1):
            self._espacio(10)
            x = self.get_x()
            self.set_text_color(*B.AZUL)
            self.set_font("helvetica", "B", 9.5)
            self.cell(7, 5.2, T(f"{i}."))
            self.set_font("helvetica", "", 9.5)
            self.set_text_color(*B.NEGRO)
            self.multi_cell(0, 5.2, T(it), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_x(x)
        self.ln(2.2)

    def nota(self, txt):
        self._espacio(20)
        self.set_font("helvetica", "", 9)
        self.set_fill_color(*B.GRIS_SUAVE)
        self.set_text_color(*B.NEGRO)
        self.set_draw_color(*B.AZUL_CLARO)
        y0 = self.get_y()
        self.multi_cell(0, 5, T(txt), fill=True, border=0, padding=3,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_line_width(1.1)
        self.line(20, y0, 20, self.get_y())
        self.set_line_width(0.2)
        self.ln(3)

    def tabla(self, headers, rows, widths, aligns=None):
        # Se reserva la altura estimada de la tabla completa para que no se parta
        # dejando dos filas huérfanas al pie de una página. El tope evita empujar
        # a página nueva una tabla que de todas formas no cabe entera.
        self._espacio(min(14 + len(rows) * 13, 190))
        self.set_font("helvetica", "", 8.6)
        self.set_draw_color(210, 214, 228)
        self.set_line_width(0.2)
        # El color de relleno vigente lo hereda la tabla para las filas alternas,
        # así que hay que dejarlo en el gris suave antes de abrirla. Si queda el
        # azul del título de capítulo, las filas pares salen ilegibles.
        self.set_fill_color(*B.GRIS_SUAVE)
        self.set_text_color(*B.NEGRO)
        estilo = FontFace(emphasis="BOLD", color=B.BLANCO, fill_color=B.AZUL)
        with self.table(col_widths=widths,
                        text_align=aligns or ["LEFT"] * len(headers),
                        headings_style=estilo,
                        line_height=5,
                        padding=(2, 2, 2, 2),
                        cell_fill_color=B.GRIS_SUAVE,
                        cell_fill_mode="ROWS",
                        width=170) as t:
            r = t.row()
            for h in headers:
                r.cell(T(h))
            for fila in rows:
                r = t.row()
                for c in fila:
                    r.cell(T(str(c)))
        self.ln(4)

    def _espacio(self, alto):
        if self.get_y() + alto > self.h - 22:
            self.add_page()


# ══════════════════════════════════════════════════════════
pdf = Manual()
pdf.alias_nb_pages()

# ── PORTADA ───────────────────────────────────────────────
pdf.portada_activa = True
pdf.add_page()
pdf.set_fill_color(*B.AZUL)
pdf.rect(0, 0, 210, 297, "F")

logo = B.logo_path()
if logo:
    try:
        pdf.image(logo, x=82, y=42, w=46)
    except Exception:
        pass

pdf.set_y(105)
pdf.set_text_color(*B.BLANCO)
pdf.set_font("helvetica", "B", 30)
pdf.cell(0, 14, T("PROTACTICS"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_font("helvetica", "", 13)
pdf.cell(0, 8, T("Manual de Usuario"), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.ln(6)
pdf.set_draw_color(255, 215, 0)
pdf.set_line_width(0.8)
pdf.line(80, pdf.get_y(), 130, pdf.get_y())
pdf.ln(10)
pdf.set_font("helvetica", "", 11)
pdf.cell(0, 7, T("Sistema de Inspección No Intrusiva"), align="C",
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.cell(0, 7, T("Tablero de Control Operacional"), align="C",
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.cell(0, 7, T("Puertos de Colombia"), align="C",
         new_x=XPos.LMARGIN, new_y=YPos.NEXT)

pdf.set_y(240)
pdf.set_font("helvetica", "", 9.5)
pdf.cell(0, 6, T("Documento dirigido a las personas que van a usar el sistema."),
         align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.cell(0, 6, T("No se requiere experiencia previa."),
         align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.ln(6)
pdf.set_font("helvetica", "", 8.5)
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
hoy = date.today()
pdf.cell(0, 6, T(f"Versión de {MESES[hoy.month - 1]} de {hoy.year}"),
         align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.portada_activa = False

# ── 1. QUÉ ES ─────────────────────────────────────────────
pdf.h1(1, "Qué es PROTACTICS")
pdf.p("PROTACTICS reúne en una sola pantalla la operación de los siete escáneres de "
      "inspección no intrusiva instalados en los puertos de Colombia.")
pdf.p("Cada puerto genera todos los meses un archivo de Excel con el registro de sus "
      "escaneos. Hasta ahora ese archivo llegaba en un formato distinto según el puerto "
      "y nadie tenía una vista nacional. El sistema recibe esos archivos, los interpreta "
      "de forma automática y los convierte en indicadores, gráficas, avisos e informes "
      "listos para descargar.")

pdf.h2("Qué permite hacer")
pdf.puntos([
    "Ver cuántos contenedores se escanearon en cada puerto, en qué día y a qué hora.",
    "Comparar el desempeño de los siete puertos entre sí.",
    "Detectar caídas de actividad que no son normales para ese puerto.",
    "Consultar por dónde pasó un contenedor y en qué fecha fue escaneado.",
    "Descargar informes de gestión en PDF y en Excel, por puerto o de todo el país.",
    "Saber quién hizo cada cambio y en qué momento.",
])

pdf.h2("Qué no hace el sistema")
pdf.p("El sistema no opera el escáner y no lee las imágenes. Trabaja sobre el archivo "
      "que el propio escáner ya produjo. Si un dato no viene en ese archivo, el sistema "
      "no puede mostrarlo.")

# ── 2. LOS SIETE ESCÁNERES ────────────────────────────────
pdf.h1(2, "Los siete escáneres")
pdf.p("Estos son los puertos que el sistema controla. Los nombres cortos son los que "
      "usted verá en el mapa y en los informes.")
pdf.tabla(
    ["Nombre en el sistema", "Puerto", "Departamento"],
    [
        ["SPR Buenaventura", "Sociedad Portuaria Regional de Buenaventura", "Valle del Cauca"],
        ["Aguadulce", "Puerto Industrial de Aguadulce", "Valle del Cauca"],
        ["TCBUEN", "Terminal de Contenedores de Buenaventura", "Valle del Cauca"],
        ["Pto. Antioquia E1", "Puerto Antioquia, escáner número 1", "Antioquia"],
        ["Pto. Antioquia E2", "Puerto Antioquia, escáner número 2", "Antioquia"],
        ["SPR Barranquilla", "Sociedad Portuaria de Barranquilla", "Atlántico"],
        ["Pto. Santa Marta", "Puerto de Santa Marta", "Magdalena"],
    ],
    widths=(38, 78, 40))
pdf.nota("Puerto Antioquia tiene dos escáneres y en el sistema cada uno es un punto "
         "independiente. Un archivo del escáner 1 no se puede cargar en el escáner 2.")

# ── 3. CÓMO SE NAVEGA ─────────────────────────────────────
pdf.h1(3, "Cómo se navega")
pdf.p("Todo el sistema son tres pantallas encadenadas. Si entiende estas tres, "
      "entiende el sistema completo.")
pdf.h2("Nivel 1. El mapa")
pdf.p("Al entrar verá el mapa de Colombia con los siete puertos marcados. A la derecha "
      "hay una lista con los mismos puertos. Haga clic sobre el puerto que le interesa.")
pdf.h2("Nivel 2. Los meses")
pdf.p("Dentro de un puerto verá los doce meses del año. Cada mes es una tarjeta que le "
      "dice si ya tiene datos cargados y cuántos escaneos registra. Arriba a la derecha "
      "puede cambiar de año.")
pdf.h2("Nivel 3. El tablero del mes")
pdf.p("Al hacer clic en un mes se abre el tablero con los indicadores, las gráficas y "
      "los avisos de ese mes.")
pdf.h2("Cómo volver")
pdf.p("En la parte superior hay una línea que le indica dónde está usted en todo "
      "momento. Haga clic en cualquier tramo de esa línea para regresar. También hay "
      "botones de volver dentro de cada pantalla.")

# ── 4. LOS CUATRO PERFILES ────────────────────────────────
pdf.h1(4, "Los cuatro perfiles de usuario")
pdf.p("Lo que usted ve depende del perfil que el administrador le asignó. Hay cuatro.")
pdf.tabla(
    ["Perfil", "Qué puertos ve", "Qué puede hacer"],
    [
        ["Administrador", "Los siete", "Todo. Además gestiona usuarios, metas, "
         "disponibilidad y mantenimiento."],
        ["Observador global", "Los siete", "Consultar y descargar informes. No modifica nada."],
        ["Observador", "Solo el suyo", "Consultar y descargar el informe de su puerto."],
        ["Alimentador", "Solo el suyo", "Consultar su puerto y cargar sus archivos de Excel."],
    ],
    widths=(32, 32, 106))
pdf.nota("Si intenta abrir un puerto que no le corresponde el sistema se lo impedirá. "
         "Esto no es un error, es la protección de la información de cada terminal.")

# ── 5. CÓMO ENTRAR ────────────────────────────────────────
pdf.h1(5, "Cómo entrar al sistema")
pdf.h2("5.1  Cuentas disponibles hoy")
pdf.p("El sistema viene con una cuenta lista para cada perfil. Sirven para conocer el "
      "sistema y para probar cada tipo de acceso.")
pdf.tabla(
    ["Perfil", "Correo", "Contraseña", "Alcance"],
    [
        ["Administrador", "admin@protactics.co", "admin1234!", "Los siete puertos"],
        ["Observador global", "global@protactics.co", "global1234!", "Los siete puertos"],
        ["Observador", "observador@protactics.co", "observador1234!", "TCBUEN"],
        ["Alimentador", "alimentador@protactics.co", "alimentador1234!", "SPR Buenaventura"],
    ],
    widths=(30, 52, 44, 44))
pdf.nota("Importante. Estas cuatro contraseñas son conocidas porque son de "
         "demostración. Antes de que el sistema entre en operación real el "
         "administrador debe cambiarlas y eliminar las cuentas que no se vayan a usar.")

pdf.h2("5.2  Iniciar sesión")
pdf.pasos([
    "Abra la dirección web del sistema que le entregó su administrador.",
    "Escriba su correo y su contraseña.",
    "Pulse el botón de entrar.",
    "Si los datos son correctos verá el mapa de Colombia con los puertos.",
])

pdf.h2("5.3  Solicitar una cuenta nueva")
pdf.p("Si usted todavía no tiene cuenta puede pedirla desde la misma pantalla de "
      "acceso, en la opción de registro.")
pdf.pasos([
    "Escriba su nombre, su correo y la contraseña que quiere usar.",
    "Elija el perfil que necesita.",
    "Si eligió observador o alimentador, indique además su puerto.",
    "Envíe la solicitud.",
])
pdf.p("Su solicitud queda en espera. Un administrador la revisa y decide si la aprueba. "
      "Mientras tanto usted no podrá entrar. El perfil de administrador no se puede "
      "solicitar, solo lo otorga otro administrador.")

pdf.h2("5.4  Si su cuenta aún está en espera")
pdf.p("Verá un aviso indicando que su cuenta todavía no tiene puerto asignado. No es "
      "una falla. Comuníquese con su administrador para que la apruebe.")

pdf.h2("5.5  Si olvidó su contraseña")
pdf.p("El sistema no envía correos de recuperación. La única forma de recuperar el "
      "acceso es pedirle a un administrador que le asigne una contraseña nueva. Cambie "
      "esa contraseña apenas pueda entrar.")

pdf.h2("5.6  Cerrar sesión")
pdf.p("Use el botón de cerrar sesión que está arriba a la derecha, junto a su nombre. "
      "Hágalo siempre que deje el computador, sobre todo si es compartido.")

# ── 6. ALIMENTADOR ────────────────────────────────────────
pdf.h1(6, "Guía del alimentador")
pdf.p("Este capítulo es para la persona que carga cada mes el archivo de su puerto. Es "
      "la tarea más importante del sistema, porque sin ese archivo no hay nada que ver.")

pdf.h2("6.1  Su rutina mensual")
pdf.pasos([
    "Al terminar el mes, obtenga del escáner el archivo de Excel con los escaneos.",
    "Entre al sistema con su cuenta.",
    "Abra su puerto en el mapa.",
    "Ubique la tarjeta del mes que va a cargar.",
    "Cargue el archivo y confirme que el mes quedó marcado con sus escaneos.",
])

pdf.h2("6.2  Cargar el archivo de un mes")
pdf.p("Sobre la tarjeta del mes aparece la opción de cargar. Selecciónela, elija el "
      "archivo en su computador y espere. Los archivos grandes pueden tardar varios "
      "segundos. No cierre la ventana mientras carga.")
pdf.p("Usted no tiene que indicar a qué puerto ni a qué mes pertenece el archivo. El "
      "sistema lo deduce solo, a partir del nombre del archivo y de su contenido.")

pdf.h2("6.3  Cargar varios archivos a la vez")
pdf.p("Si tiene varios archivos puede cargarlos todos juntos con la opción de carga "
      "múltiple. Seleccione todos los archivos y el sistema enviará cada uno a su "
      "puerto y a su mes. Al terminar le mostrará un resumen indicando cuántos entraron "
      "bien y cuáles necesitan revisión.")

pdf.h2("6.4  Cómo saber que quedó guardado")
pdf.p("La tarjeta del mes cambia y muestra el total de escaneos registrados. Si abre "
      "ese mes verá el tablero con los datos. Si la tarjeta sigue diciendo que no hay "
      "datos, el archivo no entró.")

pdf.h2("6.5  Si carga dos veces el mismo mes")
pdf.p("No se duplica nada. La segunda carga reemplaza a la primera. Puede volver a "
      "cargar un mes con tranquilidad si recibió una versión corregida del archivo.")

pdf.h2("6.6  Si el sistema rechaza el archivo")
pdf.p("El sistema revisa que el archivo corresponda al puerto y al mes donde lo está "
      "soltando. Estos son los avisos que puede recibir y qué hacer con cada uno.")
pdf.tabla(
    ["Lo que dice el sistema", "Qué significa", "Qué hacer"],
    [
        ["El archivo corresponde a otro puerto",
         "El contenido pertenece a un terminal distinto al que usted eligió.",
         "Verifique que tomó el archivo correcto. Si es de otro puerto, esa carga la "
         "hace el responsable de ese puerto."],
        ["El archivo contiene datos de otro mes",
         "El período del archivo no coincide con la tarjeta donde lo soltó.",
         "Suelte el archivo sobre la tarjeta del mes que le corresponde."],
        ["No tiene permiso para cargar datos en este puerto",
         "Está intentando cargar en un puerto que no es el suyo.",
         "Cargue únicamente en su puerto asignado."],
        ["No se encontraron escaneos de ese mes en este archivo",
         "El archivo se leyó pero no trae ningún registro utilizable del período.",
         "Confirme que el archivo no está vacío y que corresponde al mes indicado."],
    ],
    widths=(48, 55, 67))

# ── 7. OBSERVADOR DE PUERTO ───────────────────────────────
pdf.h1(7, "Guía del observador de puerto")
pdf.p("Este capítulo explica cómo leer el tablero mensual. Aplica a cualquier perfil, "
      "porque el tablero es el mismo para todos.")

pdf.h2("7.1  Las cinco tarjetas de indicadores")
pdf.tabla(
    ["Indicador", "Qué le está diciendo"],
    [
        ["Total de escaneos", "Cuántas inspecciones se hicieron en todo el mes."],
        ["Días activos", "En cuántos días distintos del mes hubo actividad registrada."],
        ["Promedio diario", "Escaneos por cada día activo. Sirve para comparar meses de "
         "distinta duración."],
        ["Pico diario", "El día de mayor volumen del mes y cuántos escaneos tuvo."],
        ["Disponibilidad de servicio", "El porcentaje de disponibilidad que el "
         "administrador registró para ese mes."],
    ],
    widths=(45, 125))

pdf.h2("7.2  Panel de cumplimiento y avisos")
pdf.p("Debajo de las tarjetas aparece el estado de cumplimiento del mes junto con los "
      "avisos abiertos del puerto. El estado se explica en el capítulo de referencia.")
pdf.p("Tenga en cuenta que la disponibilidad de la tarjeta es la cifra que informa el "
      "administrador, mientras que el estado de cumplimiento lo calcula el sistema a "
      "partir de los días con actividad registrada. Son dos lecturas distintas y pueden "
      "no coincidir.")

pdf.h2("7.3  Escaneos por día")
pdf.p("Una barra por cada día del mes. Sirve para ver de un vistazo los días fuertes, "
      "los días flojos y los días sin ninguna actividad.")

pdf.h2("7.4  Actividad por hora del día")
pdf.p("Una cuadrícula que muestra en qué franjas horarias se concentra el trabajo. "
      "Cuanto más intenso el color, más escaneos en esa hora. Es útil para decidir "
      "turnos y para explicar por qué ciertos días rinden más que otros.")

pdf.h2("7.5  Resumen del período")
pdf.p("Una tabla con las cifras del mes reunidas en una sola línea, incluido el número "
      "de operadores que trabajaron.")

pdf.h2("7.6  Descargar el informe del mes")
pdf.p("Desde el tablero puede descargar dos documentos del mes que está viendo.")
pdf.puntos([
    "El informe en PDF, pensado para presentar y para archivar.",
    "El anexo en Excel, pensado para quien necesita trabajar las cifras.",
])
pdf.p("Los dos llevan el nombre del puerto, el mes y la marca del sistema. Cada "
      "descarga queda registrada con el nombre de quien la solicitó.")

# ── 8. OBSERVADOR GLOBAL ──────────────────────────────────
pdf.h1(8, "Guía del observador global")
pdf.p("El observador global ve los siete puertos. Todo lo del capítulo anterior le "
      "aplica, y además dispone de dos herramientas nacionales.")

pdf.h2("8.1  El informe nacional")
pdf.p("Desde el panel lateral del mapa puede descargar el consolidado de todo el país "
      "en PDF y en Excel. Este documento incluye el total nacional, el ranking de "
      "puertos con la participación de cada uno, la evolución del año y el detalle "
      "puerto por puerto.")

pdf.h2("8.2  Buscar un contenedor o una placa")
pdf.p("Escriba el número de contenedor o la placa en el buscador. El sistema le "
      "responde en qué puertos aparece, en qué fecha y a qué hora fue escaneado.")
pdf.p("Si el mismo contenedor aparece en más de un puerto, verá su recorrido en orden "
      "cronológico. Esta es la función más potente del sistema y la que no existía "
      "antes en ninguna parte.")
pdf.nota("La búsqueda solo devuelve resultados de los puertos que usted tiene permitido "
         "ver. Un observador de puerto solo encontrará contenedores de su terminal.")

# ── 9. ADMINISTRADOR ──────────────────────────────────────
pdf.h1(9, "Guía del administrador")
pdf.p("El administrador tiene acceso a todo y es el único que puede modificar la "
      "configuración. Estas son sus tareas.")

pdf.h2("9.1  Aprobar solicitudes de acceso")
pdf.p("Cuando alguien pide una cuenta, aparece un aviso en la parte superior con el "
      "número de solicitudes pendientes. Desde allí puede revisar cada una y decidir.")
pdf.pasos([
    "Abra la pantalla de solicitudes desde el botón del encabezado.",
    "Revise el nombre, el correo, el perfil solicitado y el puerto solicitado.",
    "Apruebe la solicitud o recházala.",
    "Si aprueba, confirme que el perfil y el puerto sean los correctos.",
])

pdf.h2("9.2  Gestionar usuarios")
pdf.p("Desde la pantalla de usuarios puede crear una cuenta directamente sin esperar "
      "una solicitud, cambiar el perfil de alguien, cambiarle el puerto asignado o "
      "eliminar una cuenta que ya no se usa.")

pdf.h2("9.3  Restablecer una contraseña")
pdf.p("Como el sistema no envía correos de recuperación, cuando alguien pierde su "
      "contraseña usted debe asignarle una nueva desde la pantalla de usuarios. "
      "Entréguesela por un medio seguro y pídale que la cambie.")

pdf.h2("9.4  Registrar la disponibilidad mensual")
pdf.p("La disponibilidad de servicio de cada puerto se informa a mano, mes a mes. "
      "Solamente el administrador puede escribir esta cifra. Ni los alimentadores ni "
      "los observadores pueden modificarla.")
pdf.pasos([
    "Abra el puerto en el mapa.",
    "Ubique la tarjeta del mes correspondiente.",
    "Escriba el porcentaje en el campo de disponibilidad de esa tarjeta.",
    "El valor se guarda solo, sin necesidad de pulsar ningún botón adicional.",
])
pdf.p("El valor admitido va de 0 a 100 y acepta decimales. Si escribe un valor fuera de "
      "ese rango el sistema no lo acepta. Puede dejar el campo vacío si todavía no "
      "tiene la cifra.")
pdf.nota("Cada cambio de disponibilidad queda registrado con el valor anterior, el "
         "valor nuevo, la fecha y el nombre de quien lo hizo.")

pdf.h2("9.5  Metas de cumplimiento")
pdf.p("Desde la pantalla de administración puede fijar la meta de disponibilidad. "
      "Existe una meta general que aplica a todos los puertos y puede definir una meta "
      "propia para un puerto concreto cuando su situación lo justifique. La meta "
      "general del sistema está en 95 por ciento.")

pdf.h2("9.6  Ventanas de mantenimiento")
pdf.p("Cuando un escáner queda fuera de servicio por mantenimiento programado o por una "
      "falla técnica, registre esos días como ventana de mantenimiento.")
pdf.p("Los días marcados así se excluyen del cálculo. No cuentan en contra de la meta y "
      "no generan avisos de caída de actividad. Esto evita castigar a un puerto por una "
      "parada que estaba prevista.")
pdf.p("Después de cambiar una meta o de registrar una ventana, use la opción de "
      "recalcular para que el período afectado se vuelva a evaluar con la nueva "
      "configuración.")

pdf.h2("9.7  Revisar la auditoría")
pdf.p("El sistema guarda un registro de todas las acciones sensibles. Cargas de "
      "archivos, cambios de disponibilidad, aprobaciones de usuarios, inicios de sesión "
      "y descargas de informes.")
pdf.p("Ese registro no se puede editar ni borrar, y el sistema puede comprobar por sí "
      "mismo que nadie lo alteró. Si alguien modificara o quitara una línea, la "
      "comprobación lo detectaría. Use la opción de verificación cuando necesite "
      "demostrar la integridad de la información.")

pdf.h2("9.8  Protecciones del sistema")
pdf.puntos([
    "No es posible quedarse sin administradores. El sistema impide eliminar o degradar "
    "al último que quede.",
    "Un administrador no puede quitarse a sí mismo el perfil de administrador.",
    "Los observadores nunca pueden modificar información, solo consultarla.",
])

# ── 10. GLOSARIO ──────────────────────────────────────────
pdf.h1(10, "Glosario")
pdf.tabla(
    ["Término", "Significado"],
    [
        ["Escaneo", "Una inspección registrada por el escáner. Es la unidad que cuenta "
         "el sistema."],
        ["Día activo", "Día del mes en el que hubo al menos un escaneo registrado."],
        ["Disponibilidad", "Porcentaje de servicio del mes. Lo informa el administrador."],
        ["Meta", "Porcentaje mínimo de disponibilidad que se espera de un puerto."],
        ["Incumplimiento", "Situación en la que un puerto queda por debajo de su meta."],
        ["Racha", "Número de meses seguidos en los que un puerto incumple la meta."],
        ["Ventana de mantenimiento", "Período en el que el escáner estuvo fuera de "
         "servicio de forma justificada y que por eso no se contabiliza."],
        ["Anomalía", "Comportamiento que se aparta de lo habitual en ese puerto, por "
         "ejemplo una caída brusca de actividad."],
        ["Contenedor", "Unidad de carga identificada por un código internacional de "
         "cuatro letras y siete números."],
        ["Placa", "Matrícula del vehículo que transporta la carga."],
        ["Operador", "Persona que realizó los escaneos según el registro del equipo."],
    ],
    widths=(42, 128))

# ── 11. ESTADOS ───────────────────────────────────────────
pdf.h1(11, "Estados de cumplimiento")
pdf.p("Cada mes de cada puerto recibe uno de estos cinco estados. El color del punto en "
      "el mapa y del borde de la tarjeta corresponde a este estado.")
pdf.tabla(
    ["Estado", "Qué significa"],
    [
        ["Cumple", "El puerto alcanzó la meta del mes."],
        ["En riesgo", "Cumple la meta pero está muy cerca del límite."],
        ["Incumple", "Quedó por debajo de la meta, o bien es un mes pasado sin ninguna "
         "carga de información."],
        ["En mantenimiento", "El mes está cubierto por una ventana de mantenimiento y "
         "por eso no se evalúa."],
        ["Sin datos", "Todavía no hay información suficiente para evaluar ese mes."],
    ],
    widths=(40, 130))
pdf.p("Cada estado viene acompañado del motivo que lo produjo, de manera que siempre se "
      "puede explicar por qué un puerto está en determinada situación.")

# ── 12. PERMISOS ──────────────────────────────────────────
pdf.h1(12, "Quién puede hacer qué")
pdf.p("Resumen de permisos por perfil. La palabra sí indica que la acción está "
      "permitida.")
pdf.tabla(
    ["Acción", "Admin.", "Obs. global", "Observador", "Alimentador"],
    [
        ["Ver su propio puerto", "Sí", "Sí", "Sí", "Sí"],
        ["Ver los siete puertos", "Sí", "Sí", "No", "No"],
        ["Cargar archivos de su puerto", "Sí", "No", "No", "Sí"],
        ["Cargar archivos de otro puerto", "Sí", "No", "No", "No"],
        ["Registrar la disponibilidad", "Sí", "No", "No", "No"],
        ["Descargar el informe de su puerto", "Sí", "Sí", "Sí", "Sí"],
        ["Descargar el informe nacional", "Sí", "Sí", "No", "No"],
        ["Buscar contenedores", "Sí", "Sí", "Solo el suyo", "Solo el suyo"],
        ["Gestionar avisos", "Sí", "No", "No", "Solo el suyo"],
        ["Aprobar usuarios", "Sí", "No", "No", "No"],
        ["Fijar metas y mantenimiento", "Sí", "No", "No", "No"],
        ["Consultar la auditoría", "Sí", "No", "No", "No"],
    ],
    widths=(62, 22, 30, 28, 28),
    aligns=["LEFT", "CENTER", "CENTER", "CENTER", "CENTER"])

# ── 13. CALENDARIO ────────────────────────────────────────
pdf.h1(13, "El mes a mes")
pdf.p("Esta es la rutina que mantiene el sistema al día. Si se cumple, todo lo demás "
      "funciona solo.")
pdf.tabla(
    ["Cuándo", "Quién", "Qué hace"],
    [
        ["Primeros días del mes", "Alimentador de cada puerto",
         "Carga el archivo del mes que acaba de terminar."],
        ["Primeros días del mes", "Administrador",
         "Registra la disponibilidad de cada puerto para el mes cerrado."],
        ["Durante el mes", "Administrador",
         "Registra las ventanas de mantenimiento apenas ocurren."],
        ["Cuando haga falta", "Administrador",
         "Aprueba las solicitudes de acceso pendientes."],
        ["Cierre de mes", "Observador global",
         "Descarga el informe nacional y lo distribuye."],
    ],
    widths=(38, 44, 88))

# ── 14. PREGUNTAS FRECUENTES ──────────────────────────────
pdf.h1(14, "Preguntas frecuentes")

pdf.h2("No veo mi puerto en el mapa")
pdf.p("Su cuenta todavía no tiene puerto asignado o no ha sido aprobada. Hable con su "
      "administrador.")

pdf.h2("El tablero del mes aparece vacío")
pdf.p("Ese mes no tiene archivo cargado. Verifique la tarjeta del mes. Si dice que no "
      "hay datos, alguien debe cargar el archivo.")

pdf.h2("La disponibilidad y el estado de cumplimiento no coinciden")
pdf.p("Son dos cifras de origen distinto. La disponibilidad de la tarjeta la escribe el "
      "administrador. El estado de cumplimiento lo calcula el sistema con los días que "
      "tuvieron actividad registrada. Si el archivo del mes cubre pocos días, el estado "
      "será bajo aunque la disponibilidad informada sea alta.")

pdf.h2("El informe se descargó pero se ve casi vacío")
pdf.p("El mes tiene poca información cargada. Un informe solo puede mostrar lo que hay "
      "en la base. Cargue el archivo completo del mes y vuelva a generarlo.")

pdf.h2("No aparecen comparaciones con meses anteriores")
pdf.p("Las comparaciones necesitan al menos un mes previo cargado. Mientras solo haya "
      "un mes en el sistema, esas casillas seguirán sin valor.")

pdf.h2("Busco un contenedor y no aparece")
pdf.p("Puede ser que el contenedor no esté en los puertos que usted tiene permitido "
      "ver, que el mes correspondiente no esté cargado, o que el reporte de ese puerto "
      "no traiga el número de contenedor.")

pdf.h2("No veo el botón de usuarios")
pdf.p("Ese botón solo aparece para el perfil de administrador.")

pdf.h2("Cargué el archivo dos veces por error")
pdf.p("No pasa nada. El sistema reemplaza, no suma. Las cifras del mes siguen siendo "
      "correctas.")

pdf.h2("Todos los puertos aparecen en incumplimiento")
pdf.p("Ocurre cuando los archivos cargados cubren muy pocos días del mes. Cargue el "
      "archivo completo del período o registre las ventanas de mantenimiento que "
      "correspondan y vuelva a recalcular.")

# ── CIERRE ────────────────────────────────────────────────
pdf.h1(15, "Para tener presente")
pdf.puntos([
    "Sin el archivo del mes no hay tablero, no hay informe y no hay búsqueda. La carga "
    "mensual es la tarea que sostiene todo lo demás.",
    "La disponibilidad la informa únicamente el administrador.",
    "Cargar dos veces el mismo mes nunca duplica la información.",
    "Todo lo que se hace en el sistema queda registrado y ese registro no se puede "
    "alterar.",
    "Cada perfil ve solo lo que le corresponde. Eso protege la información de cada "
    "terminal.",
])
pdf.ln(6)
pdf.set_font("helvetica", "", 9)
pdf.set_text_color(*B.GRIS)
pdf.multi_cell(0, 5, T("Ante cualquier duda que este manual no resuelva, comuníquese "
                       "con el administrador del sistema."),
               new_x=XPos.LMARGIN, new_y=YPos.NEXT)

pdf.output(SALIDA)
print("PDF generado:", SALIDA)
print("Paginas:", pdf.page_no())
