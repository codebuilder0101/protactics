# PROTACTICS — Propuesta de Mejoras Funcionales

**Plan detallado de implementación, cronograma y presupuesto**

| | |
|---|---|
| **Documento** | Propuesta técnica y comercial |
| **Sistema** | PROTACTICS — Dashboard Escáner Portuario (7 puertos, Colombia) |
| **Fecha** | 11 de junio de 2026 |
| **Equipo propuesto** | 5 desarrolladores (trabajo en paralelo) |
| **Tarifa base** | USD $40 / hora · USD $320 / día-desarrollador |
| **Duración estimada** | 6 semanas (kickoff 16-jun-2026 · entrega 25-jul-2026) |
| **Inversión total** | **USD ~$29.440** (+ 10% contingencia opcional → ~$32.400) |

---

## 1. Resumen ejecutivo

PROTACTICS hoy cumple bien su función como **visor de datos**: ingesta archivos Excel de tres
formatos distintos, calcula KPIs por puerto, muestra gráficos diarios, mapa de calor por hora
y un semáforo de disponibilidad. La plataforma ya cuenta con autenticación, control de acceso
por roles (administrador, observador global, observador, alimentador) y flujo de aprobación de
usuarios.

Esta propuesta lleva el producto al siguiente nivel: de **mostrar datos** a **vigilar la
operación**. Las seis funciones aquí descritas convierten a PROTACTICS en una herramienta de
inteligencia operacional, cumplimiento contractual y trazabilidad — exactamente lo que una
operación aduanera y de seguridad portuaria necesita para tomar decisiones y rendir cuentas
ante la gerencia y los entes reguladores.

Un punto importante de viabilidad: **varias de estas funciones se construyen sobre cimientos que
ya existen en el sistema**, no desde cero. Por ejemplo, el backend ya detecta el período (día,
mes, año) desde el nombre del archivo y ya bloquea una carga cuando el mes del archivo no
coincide con el mes seleccionado. Esto reduce el riesgo y el esfuerzo de las funciones más
sensibles.

---

## 2. Alcance — las 6 funciones

### Función 1 · Detección automática de señales críticas (anomalías)

**Qué hace.** Detecta y resalta automáticamente las situaciones que importan a una operación
aduanera: caídas o picos bruscos en el rendimiento de un escáner, y la ausencia de escaneos en
fechas en las que debería haber actividad. Transforma el producto de un simple visor a una
herramienta de monitoreo del estado operativo.

**Enfoque técnico (con profundidad de investigación).** No se usa un umbral fijo ingenuo. Se
aplica un modelo estadístico que respeta la estacionalidad real de un puerto (los domingos y
festivos se escanea menos):

- **Mediana móvil + MAD** (desviación absoluta mediana) por puerto y por día de la semana, para
  detectar volúmenes anómalos sin falsas alarmas en fines de semana.
- **Carta de control EWMA** (media móvil exponencialmente ponderada) para picos y caídas
  sostenidas.
- **Detección de días en cero** dentro de un mes activo (escáner caído silenciosamente = ventana
  abierta para contrabando).
- **Caída en número de operadores** activos respecto al histórico.

**Entregables.**
- Tabla `alertas` y motor de detección que corre al ingerir cada archivo y de forma programada.
- Endpoints `/alertas` (listar, reconocer/acknowledge).
- Indicadores visuales: insignias de alerta en los pines del mapa, panel de alertas y avisos
  destacados en el dashboard del puerto afectado.

**Esfuerzo:** 14 días-desarrollador.

---

### Función 2 · Motor de cumplimiento de SLA

**Qué hace.** Convierte las barras verde/amarillo/rojo en **SLA contractuales configurables por
puerto**, con historial de infracciones y cifras de cumplimiento mensual auditables.

**Por qué es necesario.** Hoy la disponibilidad se calcula como *días activos ÷ días del mes*.
Es una estimación razonable, pero **difícil de defender en una disputa contractual**. Un modelo
de umbral configurable la vuelve defendible y auditable.

**Enfoque técnico.**
- Configuración de SLA por puerto (meta %, ventanas de mantenimiento, exclusiones de tiempo de
  inactividad planificado vs. no planificado).
- Registro de infracciones (breach log) con fecha, severidad y causa.
- Seguimiento de **meses consecutivos por debajo de la meta** — el indicador que dispara
  consecuencias contractuales.
- Cumplimiento acumulado (rolling) para informes ejecutivos.

**Entregables.**
- Tablas de configuración de SLA y de infracciones.
- Pantalla de administración para fijar metas por puerto.
- Sustitución del semáforo actual por un estado de SLA con historial de infracciones.

**Esfuerzo:** 13 días-desarrollador.

---

### Función 3 · Exportación de informes PDF / Excel con marca

**Qué hace.** Con un solo clic genera el **Informe Operativo Mensual** — por puerto o consolidado
nacional — en PDF con la imagen institucional, más un anexo de datos en Excel con gráficos.
Pensado para enviarse a la gerencia y a los entes reguladores, y para ser entendido incluso por
usuarios sin perfil técnico.

**Enfoque técnico.**
- Generación de PDF del lado del servidor con marca, resumen de KPIs, estado de SLA (Función 2) y
  alertas del período (Función 1).
- Anexo en Excel reutilizando **`openpyxl`, que ya es una dependencia del sistema** (menor
  esfuerzo).
- Gráficos renderizados del lado del servidor como imágenes embebidas.
- Versión consolidada nacional además de la individual por puerto.

**Experiencia.** Contamos con experiencia desarrollando portales de gestión gubernamental con
altos requisitos de seguridad, donde el informe formal es la función más solicitada.

**Entregables.** Endpoints de generación, botones de exportación en el frontend, plantilla PDF
con marca y plantilla Excel.

**Esfuerzo:** 11 días-desarrollador.

---

### Función 4 · Vista comparativa entre puertos — analítica nacional

**Qué hace.** Una pantalla de **centro de mando** que supera el aislamiento actual (cada puerto
muestra solo sus propios datos). De un vistazo: clasificaciones, totales nacionales, mapa de
calor por departamento, disponibilidad máxima/mínima y variación mensual e interanual.

**Enfoque técnico.**
- Endpoints de agregación nacional (totales, rankings, deltas mensual/interanual — MoM / YoY).
- Conversión del mapa SVG estático actual en un **mapa coroplético en tiempo real** que cambia de
  color según disponibilidad/uso, con una **línea de tiempo** para reproducir el histórico.
- Mapa de calor por departamento y panel de variaciones.

**Valor.** Permite a los administradores y al personal de red comprender el estado general de la
red de un vistazo — algo hoy imposible.

**Entregables.** Vista "Centro de Mando", endpoints de analítica nacional, mapa coroplético
interactivo con control de tiempo.

**Esfuerzo:** 15 días-desarrollador.

---

### Función 5 · Carga masiva inteligente y arrastrar-y-soltar (anti-error humano)

**Qué hace.** Resuelve un problema operativo real y grave: hoy, si un operador hace clic por error
en el botón de carga de **julio** para subir datos de **junio**, el sistema puede archivarlos en
el mes equivocado. Los operadores son humanos y cometen errores.

Esta función elimina ese riesgo por completo:

- **Carga masiva con un clic:** se pueden seleccionar hasta ~100 archivos y el sistema los enruta
  automáticamente al **puerto, año y mes correctos** leídos del propio archivo. El administrador
  ya no asigna el mes manualmente.
- **Capa de validación con IA / lectura de contenido:** cuando el nombre del archivo no trae
  fecha, el sistema la deduce del contenido del archivo y reporta nivel de confianza y posibles
  conflictos antes de confirmar. Estamos en la era de la IA: este tipo de error humano puede
  eliminarse incorporando inteligencia al sistema.
- **Arrastrar y soltar (drag-and-drop):** para una carga individual, basta arrastrar el archivo
  desde el explorador y soltarlo sobre la tarjeta del mes correspondiente (p. ej. junio). Si
  corresponde a ese mes, se sube automáticamente — sin buscar el archivo desesperadamente.
- **Reporte por archivo:** resultado claro de cada uno (cargado / omitido / conflicto).

**Ventaja de viabilidad.** El backend **ya detecta el período desde el nombre del archivo**
(`period_from_filename`, formato DD-MM-AAAA) y **ya bloquea** una carga cuyo mes no coincide con
el seleccionado. Esta función **extiende código probado**, no parte de cero — menor riesgo.

**Entregables.** Endpoint de carga masiva con auto-enrutamiento, capa de validación/IA con reporte
de confianza y conflictos, interfaz de arrastrar-y-soltar, reporte por archivo.

**Esfuerzo:** 12 días-desarrollador.

---

### Función 6 · Pista de auditoría y cadena de custodia

**Qué hace.** Registros **inmutables** de quién subió, modificó o aprobó qué, y cuándo.

**Por qué es necesario.** En entornos aduaneros y de seguridad, la trazabilidad es un **requisito
de cumplimiento obligatorio**. Hoy el sistema gestiona usuarios, roles y archivos cargados, pero
es imposible saber quién subió o cambió algo y en qué momento.

**Enfoque técnico.**
- Tabla de auditoría **append-only** (solo se agrega, nunca se modifica ni borra).
- Enganches (hooks) en: carga de archivos, edición de disponibilidad, aprobación/rechazo de
  usuarios, gestión de usuarios e inicio de sesión.
- Página de auditoría para el administrador con filtros y exportación.

**Entregables.** Tabla de auditoría inmutable, integración con los eventos clave, pantalla de
auditoría con filtros y exportación.

**Esfuerzo:** 9 días-desarrollador.

---

## 3. Estimación de esfuerzo y presupuesto

### 3.1 Esfuerzo por función

| # | Función | Días-dev | Costo (USD) |
|---|---------|:---:|---:|
| 1 | Detección de anomalías y alertas | 14 | $4.480 |
| 2 | Motor de cumplimiento de SLA | 13 | $4.160 |
| 3 | Informes PDF / Excel con marca | 11 | $3.520 |
| 4 | Analítica nacional y mapa coroplético | 15 | $4.800 |
| 5 | Carga masiva inteligente + drag-and-drop | 12 | $3.840 |
| 6 | Pista de auditoría / cadena de custodia | 9 | $2.880 |
| | **Subtotal funciones** | **74** | **$23.680** |

### 3.2 Trabajo transversal (compartido por el equipo)

| Concepto | Días-dev | Costo (USD) |
|----------|:---:|---:|
| Diseño técnico y esquema de base de datos | 4 | $1.280 |
| Integración entre funciones | 4 | $1.280 |
| QA / pruebas / pruebas de aceptación (UAT) | 6 | $1.920 |
| Despliegue, documentación y capacitación | 4 | $1.280 |
| **Subtotal transversal** | **18** | **$5.760** |

### 3.3 Total

| | Días-dev | Costo (USD) |
|---|:---:|---:|
| Funciones | 74 | $23.680 |
| Transversal | 18 | $5.760 |
| **Total base** | **92** | **$29.440** |
| Contingencia (10%, opcional) | — | $2.944 |
| **Total con contingencia** | | **$32.384** |

> Tarifa aplicada: USD $320 por día-desarrollador (USD $40/hora). El esfuerzo está expresado en
> días-desarrollador; el equipo de 5 personas trabaja en paralelo para comprimir el calendario
> (ver cronograma).

---

## 4. Cronograma — 6 semanas, 5 desarrolladores en paralelo

Con un equipo de 5 desarrolladores se asigna aproximadamente una función por persona, permitiendo
ejecución en paralelo. Inicio propuesto: **lunes 16 de junio de 2026**. Entrega final: **viernes
25 de julio de 2026**.

### 4.1 Asignación del equipo

| Desarrollador | Responsabilidad principal |
|---|---|
| Dev A — Backend / Datos | Función 1 (Anomalías) |
| Dev B — Backend / Negocio | Función 2 (SLA) |
| Dev C — Full-stack / Reportes | Función 3 (Informes) |
| Dev D — Frontend / Datos | Función 4 (Analítica nacional) |
| Dev E — Full-stack | Función 5 (Carga inteligente) + Función 6 (Auditoría) |

### 4.2 Calendario por semanas

| Semana | Fechas | Foco |
|:---:|---|---|
| 1 | 16–20 jun | Diseño técnico, esquema de BD, preparación del entorno. Inicio de desarrollo. |
| 2 | 23–27 jun | Desarrollo en paralelo de las 6 funciones. |
| 3 | 30 jun – 4 jul | Desarrollo en paralelo. Primeras demos internas. |
| 4 | 7–11 jul | Cierre de desarrollo + integración (los informes consumen datos de SLA y alertas; el mapa consume la analítica nacional). |
| 5 | 14–18 jul | Integración final, QA y pruebas de aceptación (UAT) con el cliente. |
| 6 | 21–25 jul | Endurecimiento (hardening), despliegue, documentación, capacitación y entrega. |

```
Sem:        1     2     3     4     5     6
F1 Anomalías  ████████████████░░
F2 SLA        ████████████████░░
F3 Reportes     ██████████████████░
F4 Nacional   ██████████████████░░
F5 Ingesta    ████████████░░
F6 Auditoría        ████████████░░
Integración                  ██████░
QA / UAT                       ████████
Despliegue                          ██████
```

---

## 5. Hitos de pago propuestos

| Hito | Momento | % | Monto (USD) |
|---|---|:---:|---:|
| Hito 1 — Firma / kickoff | Inicio (16-jun) | 30% | $8.832 |
| Hito 2 — Funciones núcleo (1, 2, 3) entregadas | Fin Semana 4 (11-jul) | 40% | $11.776 |
| Hito 3 — Entrega final + UAT aprobada | Fin Semana 6 (25-jul) | 30% | $8.832 |
| | | **100%** | **$29.440** |

---

## 6. Supuestos y condiciones

- El presupuesto se basa en la tarifa de **USD $320/día-desarrollador** y un equipo de **5
  desarrolladores** trabajando en paralelo. Un equipo menor extiende el calendario
  proporcionalmente, no el costo total en días-dev.
- El cliente proveerá **archivos de muestra reales** de cada formato y puerto al inicio, e
  indicará los **destinatarios y la imagen institucional** de los informes (Función 3).
- Las metas de SLA por puerto (Función 2) y los criterios de mantenimiento/exclusión serán
  definidos por el cliente durante la Semana 1.
- Para la ingesta inteligente con IA (Función 5), la lectura de fecha desde el contenido se basa
  en los formatos ya soportados; formatos nuevos no contemplados pueden requerir ajuste.
- No incluye costos de infraestructura en la nube (hosting, base de datos gestionada, correo
  saliente para informes), que se facturan por separado según el proveedor elegido.
- La contingencia del 10% cubre imprevistos de integración y se factura solo si se utiliza.

---

## 7. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Formatos de Excel no documentados | Recolección temprana de muestras reales en Semana 1. |
| Falsas alarmas en detección de anomalías | Modelo estadístico con estacionalidad (MAD/EWMA) y umbrales calibrables. |
| Disputa sobre la definición de disponibilidad | El motor de SLA hace la definición explícita, configurable y auditable. |
| Error humano en cargas | La Función 5 elimina la asignación manual de mes (extiende validación ya existente). |
| Dependencia entre funciones (informes ↔ SLA/alertas) | Integración planificada en Semana 4 con interfaces acordadas desde la Semana 1. |

---

*PROTACTICS · Propuesta de Mejoras Funcionales · Junio 2026*
