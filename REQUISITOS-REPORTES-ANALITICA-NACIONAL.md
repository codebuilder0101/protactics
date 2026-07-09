# PROTACTICS — Requisitos: Informes PDF de Gestión (por puerto y nacional)

**Especificación de requisitos basada en el código actual del proyecto.**

> **Alcance de este milestone: SOLO generación de informes PDF con marca.**
> Se acordó con el cliente limitar la entrega a los informes PDF. **Quedan FUERA de este milestone** (documentados como fase posterior, §7): anexo Excel, envío por correo, vista "Centro de Mando" y mapa coroplético con línea de tiempo.

| | |
|---|---|
| **Alcance** | Informe PDF con marca, por puerto y consolidado nacional, con datos y gráficos. Descarga directa desde la UI |
| **Stack real** | FastAPI + SQLAlchemy · PostgreSQL (prod) / SQLite (dev+test) · frontend `index.html` (JS vanilla) |
| **Granularidad de datos** | `escaneos_diarios` (puerto, año, mes, día, total); `escaneos_horarios` (por hora); `operadores` (por día/nombre); `escaneo_filas`/`indice_identificadores` (trazabilidad); `alertas` (Inteligencia Operacional) |
| **Dependencias nuevas** | Backend: **1 librería PDF pure-Python** (a decidir, §7 D-1). El gráfico del PDF se dibuja con primitivos de la propia librería (sin matplotlib). Frontend: **ninguna** (solo botones de descarga; los gráficos se renderizan en el servidor dentro del PDF) |
| **Convenciones** | Migraciones `_ensure_*` en `database.py` (no Alembic) · auditoría append-only con cadena hash · lógica de datos pura y testeable separada de la composición del PDF · mensajes en español |

**Leyenda de identificadores:** `RF` requisito funcional · `RN` regla de negocio · `RNF` requisito no funcional · `PR` requisito de prueba.

---

## 0. Contexto del código existente (lo que ya está y lo que falta)

Estado verificado en `backend/main.py`, `backend/models.py`, `backend/auth.py`, `frontend/index.html`:

**Lo que YA existe y se reutiliza:**
- `GET /data/{puerto_id}/{year}/{mes}` → detalle mensual de un puerto (serie diaria, promedio, total del mes).
- `GET /meses/{puerto_id}` → meses disponibles de un puerto.
- `escaneos_horarios` (escaneos por hora), `operadores` (por operador/día), `escaneo_filas`/`indice_identificadores` (contenedores/placas de trazabilidad).
- `GET /alertas` → alertas de Inteligencia Operacional (para el resumen de alertas del informe).
- Roles y helpers: `admin`, `observador_global`, `observador`, `alimentador`; `can_view_port`, `allowed_port_ids` (None = todos), `require_admin` ([auth.py](backend/auth.py)).
- `record_audit(...)` en cada mutación; cadena hash inmutable; `GET /api/audit/verify`.
- `MONTHS` (nombres de mes en español) en [main.py](backend/main.py).

**Lo que FALTA (objeto de este milestone):**
- **No hay generación de PDF**: no existe librería PDF instalada ni endpoints de informe.
- **No hay agregación nacional** (totales país, ranking, variación) — necesaria solo para el informe nacional consolidado.
- **No hay botones de descarga de informe** en la UI.

---

## 1. Requisitos transversales

### Datos y agregación
- **RN-1.1** Toda cifra se deriva de la granularidad existente: total mes = `SUM(escaneos_diarios.total)` por `(puerto, year, mes)`; total nacional = suma sobre los puertos **visibles para el usuario**. Cálculo on-demand al pedir el PDF (volumen pequeño: 7 puertos × meses); no se persisten agregados.
- **RN-1.2** **La DISPONIBILIDAD queda EXCLUIDA de los informes** (decisión del cliente). No se muestra el índice de disponibilidad, ni el estado de cumplimiento de SLA derivado de ella. El contenido se basa en **volumen de escaneos** y en el catálogo RN-1.2b.
- **RN-1.2b** **Catálogo de contenido del informe** (para "lo más completo posible con gráficos y data", sin disponibilidad). Fuentes reales ya en la BD:
  - **Volumen**: `escaneos_diarios` → total del mes, promedio diario, serie diaria, día pico / día valle.
  - **Distribución horaria**: `escaneos_horarios` → escaneos por hora (0–23), hora pico.
  - **Operadores**: `operadores` → nº de operadores distintos, escaneos por operador (productividad).
  - **Trazabilidad**: `escaneo_filas`/`indice_identificadores` → nº de contenedores escaneados, contenedores ISO 6346 válidos, placas/vehículos (solo puertos con reporte de detalle).
  - **Alertas de volumen** (Inteligencia Operacional, EXCLUYENDO las de disponibilidad/SLA): `anomaly_low`, `anomaly_high`, `ewma_drop`, `ewma_spike`, `zero_day`, `operator_drop`. Se omiten `sla_breach`, `no_upload` y `availability_low`.
  - **Comparativa / tendencia** (solo informe nacional): ranking de puertos, variación MoM/YoY, serie mensual del año.
- **RN-1.3** Variación mensual (MoM): `(m[mes] − m[mes−1]) / m[mes−1] × 100`. Interanual (YoY): `(m[mes,año] − m[mes,año−1]) / m[mes,año−1] × 100`. Denominador 0 o sin dato base → variación `null` ("n/d"); **nunca** división por cero.
- **RN-1.4** Ranking de puertos (informe nacional): por escaneos del período, descendente; empates por `puerto_id` ascendente (determinista). `cuota_pct` = valor / total nacional × 100.
- **RN-1.5** Las alertas del informe provienen de `GET /alertas`, **filtradas a los tipos de volumen** de RN-1.2b.

### Seguridad y permisos
- **RF-1.6** Informe **de un puerto** (`.../pdf/puerto/{puerto_id}/...`): permitido si `can_view_port(user, puerto_id)`.
- **RF-1.7** Informe **nacional** (`.../pdf/nacional/...`): permitido solo si `allowed_port_ids(user) is None` (`admin` u `observador_global`). Un usuario con alcance (`observador`/`alimentador`) recibe **403**.
- **RN-1.8** El informe nacional incluye **exactamente** los puertos de `allowed_port_ids(user)` (para admin/global = todos). Ningún informe filtra distinto a `/puertos`: sin fuga de datos entre puertos.

### Auditoría
- **RN-1.9** Cada generación de informe registra `record_audit(accion="reporte_pdf", ...)` con período, alcance (`puerto_id` o `nacional`) y usuario. Es una lectura, pero se audita por trazabilidad de difusión.

### No funcionales
- **RNF-1.10** El informe de puerto o nacional se genera en **< 2 s** con un año de datos en SQLite local.
- **RNF-1.11** Librería PDF **pure-Python** o con wheels sin dependencias de SO (para no romper el Docker/Railway). Descarta WeasyPrint/cairo salvo decisión explícita (§7 D-1). Gráficos dibujados como primitivos (barras/línea), sin matplotlib.
- **RNF-1.12** Frontend sin librerías nuevas: solo botones de descarga; el PDF (incluidos sus gráficos) se compone en el servidor.
- **RNF-1.13** Todo el texto del informe en **español** (meses vía `MONTHS`).
- **RNF-1.14** **Zona horaria**: toda fecha/hora visible (sello de generación) en **América/Bogotá (UTC−5)** — "Bogotá, Lima, Quito". El almacenamiento sigue en UTC; se convierte solo en la capa de presentación.
- **RNF-1.15** **Determinismo/reproducibilidad**: mismo dato + mismo período → contenido idéntico salvo el sello de generación (fecha/hora y usuario), en un pie claramente marcado.
- **RNF-1.16** **Marca (branding)** centralizada en `reportes/branding.py` + `frontend/assets`, no incrustada en cada plantilla. **Valores confirmados por el cliente:**
  - **Título de todos los informes**: "Informe de Gestión — Sistema de Inspección No Intrusiva".
  - **Logo**: Protactics (el proporcionado), en `frontend/assets/` en PNG con fondo transparente y versión apta para PDF.
  - **Paleta**: azul corporativo del logo (navy) **mezclado con blanco**. Primario ≈ `#232C7C` (⚠ **muestrear el hex exacto del logo** en implementación), fondo **blanco** `#FFFFFF`. Series de gráficos: rampa monocroma de azules a partir del primario (p. ej. `#232C7C → #3A46A6 → #6470C7 → #9AA3DB → #C9CEEC`), definida con el método de la skill **dataviz** en implementación.
  - **Pie obligatorio de todos los informes**: "Información confidencial – Prohibida su reproducción", junto al sello de generación (RNF-1.15) en hora de Bogotá.

---

## 2. Agregación de datos para informes (backend `reportes/datos.py`)

*Módulo de **lógica pura/consultas** que reúne los datos de cada informe, separado de la composición del PDF (§3). Testeable con `Session` + `puerto_ids` ya filtrado por el llamador (RN-1.8).*

### Datos de un puerto-mes
- **RF-2.1** `datos_puerto(db, puerto_id, year, mes) -> dict`: total, promedio diario, serie diaria (día→total), día pico/valle, distribución horaria (hora→total), operadores (nombre→total) y nº distinto, trazabilidad (contenedores, contenedores_validos, placas) si el puerto tiene detalle, variación MoM/YoY del puerto (RN-1.3), y alertas de volumen abiertas del puerto-mes (RN-1.5). **Sin disponibilidad.**

### Consolidado nacional
- **RF-2.2** `datos_nacional(db, year, mes, puerto_ids) -> dict`: total nacional, promedio diario nacional, desglose por puerto, ranking (RN-1.4), variación nacional MoM/YoY, serie mensual del año (mes→total nacional) para el gráfico de tendencia, agregados del catálogo (operadores distintos, contenedores) y nº de puertos con dato / sin carga. **Sin disponibilidad.**
- **RN-2.3** Un mes/puerto sin `escaneos_diarios` cuenta como `valor=0` con bandera `sin_carga=true`; en variación, base sin dato → `delta_pct=null` (no 0).
- **RN-2.4** Período por defecto cuando no se especifica: **último mes con datos** (no "hoy"), tanto para puerto como para nacional.

### Pruebas
- **PR-2.5** Unit `datos_nacional`: ranking ordenado y `cuota_pct` correctos; empate desempata por `puerto_id`; total nacional respeta `puerto_ids` parcial.
- **PR-2.6** Unit variación: base 0/ausente → `null`; caso normal → porcentaje correcto; YoY sin año previo → `null`.
- **PR-2.7** Unit `datos_puerto`: serie diaria, hora pico y día pico correctos sobre datos sembrados; puerto sin detalle → trazabilidad en 0/omitida sin error.

---

## 3. Generación del informe PDF

*Paquete `backend/reportes/` con `pdf.py` (composición), `branding.py` (marca, RNF-1.16) y datos vía §2. Librería PDF según §7 D-1.*

### 3.1 Informe de PUERTO
- **RF-3.1** `GET /reportes/pdf/puerto/{puerto_id}/{year}/{mes}` (respeta `can_view_port`, RF-1.6) → PDF con:
  - Encabezado de marca: logo Protactics, título "Informe de Gestión — Sistema de Inspección No Intrusiva", subtítulo "{puerto} · {mes} {año}".
  - KPIs del mes (**sin disponibilidad**): total de escaneos, promedio diario, día pico/valle, operadores distintos, contenedores escaneados (y válidos ISO 6346) y placas si hay detalle, nº de alertas de volumen por severidad.
  - Gráfico **serie diaria** del mes (barras/línea).
  - Gráfico **distribución horaria** (0–23) con la hora pico marcada.
  - **Productividad por operador**: tabla/gráfico de escaneos por operador.
  - Variación MoM y YoY del puerto.
  - Resumen de **alertas de volumen** (tipo, severidad, fecha) del puerto-mes, si las hay.
  - Pie (RNF-1.15/1.16): "Información confidencial – Prohibida su reproducción" + sello de generación (fecha/hora Bogotá, usuario) + "documento generado automáticamente".

### 3.2 Informe NACIONAL consolidado
- **RF-3.2** `GET /reportes/pdf/nacional/{year}/{mes}` (alcance nacional, RF-1.7) → PDF con:
  - Portada de marca (logo + título) + período.
  - Totalizadores nacionales (**sin disponibilidad**): escaneos, promedio diario, puertos activos, operadores distintos, contenedores escaneados.
  - **Ranking** de puertos (tabla: posición, escaneos, cuota %) + gráfico de barras comparativo por puerto.
  - Variación nacional MoM/YoY.
  - Gráfico de **serie mensual** del año (evolución del total nacional).
  - Tabla por puerto: escaneos, promedio diario, operadores, contenedores/placas, alertas de volumen. **Sin disponibilidad ni estado de SLA.**
  - Pie (RNF-1.15/1.16): confidencialidad + sello de generación en hora de Bogotá.

### 3.3 Reglas comunes
- **RN-3.3** Período sin datos → PDF válido con la leyenda "Sin cargas para el período", **no** un error 500.
- **RN-3.4** Se sirve con `Content-Type: application/pdf` y `Content-Disposition: attachment; filename="..."`, nombre determinista: `PROTACTICS_{puerto|nacional}_{year}-{mes:02d}.pdf`.
- **RN-3.5** El branding sale de `branding.py`; cambiar la marca no exige tocar la composición.
- **RN-3.6** `year`/`mes` opcionales → último mes con datos (RN-2.4).

### Pruebas
- **PR-3.7** `GET /reportes/pdf/puerto/...` con permiso → 200, `Content-Type` PDF, cuerpo empieza por `%PDF-` y > N bytes; sin permiso → 403; sin sesión → 401.
- **PR-3.8** `GET /reportes/pdf/nacional/...` por observador de puerto → 403; por admin → 200 PDF válido.
- **PR-3.9** Período sin datos → 200 con PDF "sin cargas" (RN-3.3), no 500.
- **PR-3.10** Generar el informe registra `record_audit(accion="reporte_pdf", ...)` con período y alcance (RN-1.9) y no rompe `/api/audit/verify`.
- **PR-3.11** Determinismo (RNF-1.15): dos generaciones del mismo período son idénticas salvo el pie (comparar tras enmascarar el sello).

---

## 4. Entrega — descarga con un clic (frontend)

- **RF-4.1** En el dashboard de puerto ([index.html](frontend/index.html), `renderDashboard`), botón **"Descargar informe PDF"** que abre `GET /reportes/pdf/puerto/{puerto_id}/{year}/{mes}` del período mostrado.
- **RF-4.2** Botón **"Informe nacional (PDF)"** visible **solo** para `admin`/`observador_global` (se oculta a roles con alcance), que abre `GET /reportes/pdf/nacional/{year}/{mes}` del período seleccionado (por defecto el último con datos).
- **RNF-4.3** Sin vistas nuevas ni librerías nuevas: son enlaces/botones de descarga que reutilizan la sesión (cookie) existente.

### Pruebas
- **PR-4.4** *(manual/e2e)* El botón de puerto descarga el PDF del mes mostrado; el botón nacional no aparece para un observador de puerto y sí para admin/global.

---

## 5. Estrategia y cobertura de pruebas (resumen)

- **PR-5.1** La agregación (`reportes/datos.py`) se prueba con **unit tests** sobre datos sembrados; es el grueso de la cobertura numérica (ranking, variación, serie, hora/día pico).
- **PR-5.2** Patrón existente en `backend/tests/`: `pytest` + `TestClient`, SQLite, fixtures `client/admin/feeder` de `conftest.py`, builders `standard_xlsx/tcbuen_xlsx/rapiscan_xlsx` para sembrar varios meses/años (MoM/YoY).
- **PR-5.3** Nuevos archivos: `test_reportes_datos.py`, `test_reportes_pdf.py`.
- **PR-5.4** PDF: no se valida pixel a pixel; se valida **estructura** (empieza por `%PDF-`, tamaño), **permisos** (401/403/200), **período vacío** (RN-3.3), **auditoría** (RN-1.9) y **determinismo** (PR-3.11).
- **PR-5.5** Meta de cobertura: ≥ 90% en `reportes/datos.py`; endpoints y composición: camino feliz + permisos + período vacío.

---

## 6. Criterios de aceptación (Definition of Done)

1. Un usuario con permiso descarga el **PDF de un puerto** para un mes: sale con marca (logo, título, azul + blanco, pie de confidencialidad), KPIs sin disponibilidad, y gráficos de serie diaria, distribución horaria y operadores.
2. Un `admin`/`observador_global` descarga el **PDF nacional**: totales, ranking con gráfico, variación MoM/YoY y serie mensual del año; un usuario con alcance recibe 403.
3. El sello de generación aparece en **hora de Bogotá**; el pie de confidencialidad está en ambos informes.
4. Un período sin datos produce un PDF de "sin cargas", no un error.
5. Cada generación queda auditada (`reporte_pdf`) y `/api/audit/verify` sigue OK.
6. Ningún informe filtra datos fuera del `allowed_port_ids` del usuario.
7. Suite verde: unit de agregación, estructura de PDF, permisos, período vacío y determinismo.

---

## 7. Riesgos y decisiones abiertas

- **D-1 (librería PDF):** ✅ **RESUELTO — `fpdf2==2.8.2`** (pure-Python, sin dependencias de SO; RNF-1.11). Los gráficos (barras/línea) se dibujan con primitivos de la propia librería, sin matplotlib. El texto se sanea a latin-1 porque las fuentes core no son Unicode.
- **D-4 (disponibilidad):** ✅ **RESUELTO — EXCLUIDA** de los informes (RN-1.2). El contenido se enriquece con el catálogo RN-1.2b.
- **D-6 (período por defecto):** ✅ último mes con datos (RN-2.4), para no mostrar vacíos.
- **D-7 (caché de agregados):** on-demand en esta fase (volumen pequeño, RNF-1.10). Materializar solo si aparece un cuello de botella.
- **D-8 (marca real):** ✅ **RESUELTO** — título, logo Protactics, azul navy + blanco, pie de confidencialidad, hora de Bogotá (RNF-1.16). *Pendiente menor:* muestrear el hex exacto del azul del logo en implementación.

### Fuera de alcance de este milestone (fase posterior)
- **Anexo Excel** con gráficos (`openpyxl` ya instalado).
- **Envío por correo** de los informes (SMTP).
- **Vista "Centro de Mando"** (totales nacionales, ranking, variación en pantalla).
- **Mapa coroplético** con línea de tiempo.
> La agregación de §2 (`datos_nacional`) queda lista para reutilizarse en el Centro de Mando y el mapa cuando se retomen.

---

## 8. Mapa de archivos a tocar (referencia de implementación)

| Componente | Archivo | Acción |
|---|---|---|
| Agregación de datos del informe (puerto + nacional) | `backend/reportes/datos.py` | **nuevo** (consultas/lógica pura) |
| Composición del PDF | `backend/reportes/pdf.py` | **nuevo** |
| Marca centralizada (logo/título/paleta/pie) | `backend/reportes/branding.py` + `frontend/assets/` | **nuevo** |
| Endpoints de informe | [main.py](backend/main.py) | `GET /reportes/pdf/puerto/...`, `GET /reportes/pdf/nacional/...` |
| Dependencia PDF | [requirements.txt](backend/requirements.txt) | +1 librería (D-1) |
| Botones de descarga (puerto + nacional) | [index.html](frontend/index.html) | 2 botones en `renderDashboard` / cabecera |
| Pruebas | `backend/tests/test_reportes_{datos,pdf}.py` | **nuevas** |

---

## 9. Orden de implementación recomendado

1. **Decidir D-1** (librería PDF) y añadirla a `requirements.txt`.
2. **`reportes/datos.py`** (§2) — puro y testeable primero (unit tests de agregación).
3. **`reportes/branding.py`** — logo, título, paleta, pie (muestrear el azul exacto).
4. **`reportes/pdf.py` + `GET /reportes/pdf/puerto/...`** (§3.1) — el informe de puerto de punta a punta.
5. **`GET /reportes/pdf/nacional/...`** (§3.2) — reutiliza la agregación nacional.
6. **Botones de descarga en la UI** (§4).

> Cada paso deja la suite de pruebas verde antes de avanzar. La única dependencia nueva (PDF) entra en el paso 1; el resto del milestone no añade dependencias.
