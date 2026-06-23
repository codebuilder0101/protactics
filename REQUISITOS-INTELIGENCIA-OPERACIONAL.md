# PROTACTICS — Requisitos: Inteligencia Operacional (Anomalías + SLA)

**Especificación de requisitos basada en el código actual del proyecto.**

| | |
|---|---|
| **Alcance** | Motor de anomalías, motor de SLA, ventanas de mantenimiento, alertas, estado auditable |
| **Stack real** | FastAPI + SQLAlchemy · PostgreSQL (prod) / SQLite (dev+test) · frontend `index.html` (JS vanilla) |
| **Granularidad de datos** | `escaneos_diarios` (puerto, año, mes, día, total); horas y operadores por día; disponibilidad mensual |
| **Convenciones** | Migraciones manuales estilo `_ensure_*` en `database.py` (no Alembic) · auditoría append-only con cadena hash · sin dependencias front nuevas |

**Leyenda de identificadores:** `RF` requisito funcional · `RN` regla de negocio · `RNF` requisito no funcional · `PR` requisito de prueba.

---

## 0. Contexto del código existente (lo que ya está y lo que falta)

Estado verificado en `backend/models.py`, `backend/main.py`, `backend/database.py`, `backend/auth.py`, `frontend/index.html`:

- **Ya existe el esquema stub (Semana 1)** de [models.py](backend/models.py): `Alerta`, `SLA`, `Infraccion`. **No hay motor, ni endpoints, ni UI** que los usen todavía.
- `Alerta.tipo` está restringido por `CheckConstraint` a `('sla_breach','no_upload','availability_low')` — **no admite tipos de anomalía**: hay que ampliar el CHECK.
- `SLA.metrica` está restringido a `('availability','upload_deadline','min_daily_scans')`; `puerto_id NULL` = valor por defecto global; `UniqueConstraint(puerto_id, metrica)`.
- `Infraccion` ya enlaza `sla_id`, `puerto`, `year`, `mes`, `dia`, `valor_observado`, `valor_esperado`, `alerta_id`.
- **No existe tabla de ventanas de mantenimiento** → hay que crearla.
- `compute_availability()` en [main.py](backend/main.py) ya calcula disponibilidad = días activos / días efectivos del mes × 100.
- El **semáforo actual** vive en `getDispColor()` de [index.html](frontend/index.html) y depende solo de la disponibilidad (≥95 verde, ≥90 amarillo, <90 rojo). Es el que se debe reemplazar por estado de SLA auditable.
- **Migraciones:** patrón `_ensure_user_columns` / `_ensure_daily_schema` en [database.py](backend/database.py) con `ALTER TABLE`. **No hay Alembic.** Cambiar un `CheckConstraint` en una tabla existente requiere recrearla (Postgres: `ALTER TABLE ... DROP/ADD CONSTRAINT`; SQLite: recrear tabla). En tests el esquema se hace `drop_all/create_all` por prueba, así que el CHECK nuevo entra limpio en test pero **requiere migración explícita en producción**.
- **Roles:** `admin`, `observador_global`, `observador`, `alimentador` (alcance por puerto). Helpers `can_view_port`, `can_upload_port`, `allowed_port_ids`, `require_admin`.
- **Auditoría:** `record_audit(...)` en cada mutación; cadena hash inmutable.

---

## 1. Requisitos transversales (aplican a todo el módulo)

### Datos y migración
- **RN-1.1** Toda tabla/columna nueva se crea siguiendo el patrón `_ensure_*` de `database.py` con `ALTER TABLE`, sin perder datos existentes. Idempotente.
- **RN-1.2** La ampliación del `CheckConstraint` de `alertas.tipo` (para tipos de anomalía) y cualquier CHECK nuevo debe migrarse en Postgres con `ALTER TABLE alertas DROP CONSTRAINT ck_alertas_tipo; ADD CONSTRAINT ...`, protegido por dialecto (`engine.dialect.name == 'postgresql'`).
- **RN-1.3** Todos los cálculos respetan la granularidad existente: día = `(puerto_id, year, mes, dia)`; mes = `(puerto_id, year, mes)`.

### Seguridad y permisos
- **RF-1.4** Lectura de alertas/infracciones/estado SLA de un puerto: permitida si `can_view_port(user, puerto_id)` (admin y global ven todo; observador/alimentador solo su puerto).
- **RF-1.5** Configurar metas de SLA y ventanas de mantenimiento: **solo `admin`** (`require_admin`).
- **RF-1.6** Reconocer/resolver alertas: `admin` y `alimentador` del puerto (configurable; por defecto admin + feeder del puerto). Observadores no mutan.
- **RF-1.7** Endpoints que filtran por puerto deben respetar `allowed_port_ids(user)` igual que `/puertos`.

### Auditoría
- **RN-1.8** Toda mutación (crear/editar meta SLA, crear/cerrar ventana de mantenimiento, ack/resolver alerta, recálculo manual) registra `record_audit(...)` con antes/después. Las alertas generadas automáticamente por el motor se auditan con actor sistema (`actor_email="system"` o `actor=None`).

### No funcionales
- **RNF-1.9** El recálculo de anomalías y SLA de un puerto-mes debe completarse en < 500 ms con un año de datos en SQLite local (es un volumen pequeño: ≤ 31 filas/mes/puerto).
- **RNF-1.10** Sin dependencias nuevas de frontend (se mantiene JS vanilla). En backend se permite **solo la librería estándar y numpy/estadística manual**; preferible implementar mediana/MAD/EWMA a mano para no añadir numpy si no está. *(Decisión a confirmar: ver §11.)*
- **RNF-1.11** Internacionalización: mensajes de alerta y estados en español (consistente con el resto de la app).
- **RNF-1.12** Determinismo: dado el mismo conjunto de datos y configuración, el motor produce exactamente las mismas alertas e infracciones (idempotencia — volver a correrlo no duplica).

---

## 2. Ventanas de mantenimiento / inactividad técnica

*Base de todo: las excepciones deben existir antes de calcular anomalías y SLA, porque ambos las consumen.*

### Modelo de datos
- **RF-2.1** Nueva tabla `VentanaMantenimiento` (`mantenimiento`):
  - `id`, `puerto_id` (FK, no nulo)
  - `tipo`: `('programado','falla_tecnica')` — mantenimiento planificado vs. caída técnica del escáner
  - `fecha_inicio` (Date), `fecha_fin` (Date, nullable = abierta/en curso)
  - `motivo` (Text), `creada_por` (FK users), `creada_en`, `cerrada_en` (nullable)
  - Índice `(puerto_id, fecha_inicio, fecha_fin)`.
- **RN-2.2** Una ventana cubre días completos `[fecha_inicio, fecha_fin]` inclusive. `fecha_fin NULL` = sigue activa (cubre hasta hoy).
- **RN-2.3** Validación: `fecha_fin >= fecha_inicio`. Se permiten solapamientos (se unifican al evaluar).

### API
- **RF-2.4** `GET /mantenimiento/{puerto_id}` → lista de ventanas (respeta `can_view_port`).
- **RF-2.5** `POST /mantenimiento/{puerto_id}` (admin) → crea ventana. Body: `tipo`, `fecha_inicio`, `fecha_fin?`, `motivo`. Audita.
- **RF-2.6** `PATCH /mantenimiento/{id}` (admin) → editar/cerrar (fijar `fecha_fin`). Audita antes/después.
- **RF-2.7** `DELETE /mantenimiento/{id}` (admin) → eliminar (raro; auditar). Alternativa: marcar anulada.

### Reglas de negocio (consumo)
- **RN-2.8** Un día `(puerto, year, mes, dia)` está **excluido** si cae dentro de alguna ventana de ese puerto.
- **RN-2.9** **Anomalías:** los días excluidos no generan alertas y **no entran** en el cálculo de mediana/MAD/EWMA ni en la detección de días-en-cero. (Un cero en mantenimiento programado es esperado, no anómalo.)
- **RN-2.10** **SLA:** los días excluidos se descuentan del denominador del cálculo de disponibilidad y de cualquier meta diaria. Es decir, SLA mensual se evalúa solo sobre días "elegibles" (no en mantenimiento).
- **RN-2.11** Helper único compartido `dias_excluidos(puerto_id, year, mes) -> set[int]` usado por ambos motores, para garantizar consistencia.

### Pruebas
- **PR-2.12** Unit: `dias_excluidos` con ventana cerrada, ventana abierta (`fecha_fin NULL`), ventana que cruza fin de mes, ventana fuera del mes (set vacío), solapamiento de dos ventanas.
- **PR-2.13** Integración: admin crea ventana → `GET` la devuelve; observador del puerto la ve; observador de otro puerto recibe 403; no-admin recibe 403 al crear.
- **PR-2.14** Integración: crear ventana audita (aparece en `/api/audit`).

---

## 3. Motor de detección de anomalías

*Nuevo módulo `backend/anomalies.py`. Trabaja sobre `escaneos_diarios` (y `operadores`) de un `(puerto, year, mes)`, excluyendo días de mantenimiento (§2).*

### 3.1 Mediana móvil + MAD por día de la semana
- **RF-3.1** Para cada día con dato, calcular un valor de referencia robusto usando **la mediana** de los totales históricos del **mismo día de la semana** (lunes…domingo) en una ventana móvil configurable (por defecto las últimas N=8 ocurrencias de ese día de semana, excluyendo días de mantenimiento).
- **RF-3.2** Calcular **MAD** (desviación absoluta mediana) sobre esa misma muestra. Marcar anomalía si `|valor − mediana| > k · MAD` con `k` configurable (por defecto `k=3.5`), usando el factor de consistencia 1.4826 para escalar MAD a desviación estándar.
- **RN-3.3** Si la muestra histórica del día de semana tiene < `min_muestra` puntos (por defecto 4), **no** se evalúa (evita falsos positivos por falta de historia). Se reporta como "datos insuficientes", no como anomalía.
- **RN-3.4** `MAD == 0` (todos los valores iguales): usar un umbral mínimo absoluto configurable para no disparar por ruido de ±1.
- **RF-3.5** Cada anomalía produce/actualiza una `Alerta` tipo `anomaly_low` o `anomaly_high` (según el signo), severidad derivada de cuántos MAD se desvía (`warning` ≥ k, `critical` ≥ 1.5·k), con `payload` = {metodo, valor, mediana, mad, desv}.

### 3.2 Carta de control EWMA (caídas y picos bruscos sostenidos)
- **RF-3.6** Calcular EWMA sobre la serie diaria del puerto (orden cronológico, días excluidos omitidos): `z_t = λ·x_t + (1−λ)·z_{t−1}`, `λ` configurable (por defecto 0.3).
- **RF-3.7** Límites de control `± L·σ_ewma` con `σ_ewma = σ·sqrt(λ/(2−λ))`, `L` configurable (por defecto 3). `σ` estimado por MAD robusto de la serie base.
- **RF-3.8** Disparar alerta solo en desviaciones **sostenidas**: el EWMA debe cruzar el límite durante ≥ `m` días consecutivos elegibles (por defecto 2) — distingue una caída sostenida de un bache de un solo día.
- **RF-3.9** Genera `Alerta` `ewma_drop` / `ewma_spike`, severidad por magnitud y duración.

### 3.3 Días en cero dentro de un mes activo
- **RF-3.10** Dentro de un mes con actividad (≥1 día con escaneos), todo día **elegible** (no mantenimiento) con `total == 0` **o sin registro** entre el primer y el último día activo del mes se marca como `dia_cero`.
- **RN-3.11** No se marcan los días futuros del mes en curso (posteriores a "hoy" UTC) ni los días anteriores al primer dato del puerto.
- **RF-3.12** Genera `Alerta` `zero_day` (una por día, o una agrupada por racha — ver RN-3.13).
- **RN-3.13** Días-cero consecutivos se agrupan en **una** alerta con rango `payload={desde, hasta, dias}` para no inundar.

### 3.4 Caída de operadores
- **RF-3.14** Comparar el nº de operadores distintos activos del mes (`COUNT(DISTINCT nombre)` en `operadores`) contra la mediana de los meses previos del puerto. Si cae por debajo de `(1 − caida_pct)` (por defecto 40%), generar `Alerta` `operator_drop`.
- **RN-3.15** Requiere ≥ `min_meses` (por defecto 3) de historia; si no, no evalúa.

### 3.5 Ejecución y persistencia
- **RF-3.16** El motor se ejecuta automáticamente al final de `save_parsed_data()` / `process_upload()` para el `(puerto, year, mes)` cargado (hook), y bajo demanda vía endpoint (§5).
- **RN-3.17** **Idempotencia:** antes de insertar, el motor reconcilia: si una alerta del mismo `(puerto, tipo, periodo, clave)` ya existe y sigue vigente, se actualiza; si la condición ya no se cumple, la alerta abierta se **auto-resuelve** (`estado=resolved`, `resuelta_por=system`). No se duplican alertas al recargar el mismo archivo.
- **RN-3.18** Parámetros (`N`, `k`, `λ`, `L`, `m`, `caida_pct`, umbrales mínimos) viven en un dict de configuración central (`anomalies.py`) con posibilidad de override por variable de entorno; valores por defecto documentados. *(SLA por puerto se configura en BD; los de anomalías son globales en esta fase.)*

### Pruebas (motor de anomalías)
- **PR-3.19** Unit mediana/MAD: serie estable + un día caído a 0 → detecta `anomaly_low`; serie estable sin outliers → 0 alertas; muestra < `min_muestra` → "datos insuficientes", 0 alertas; `MAD==0` con ruido ±1 → 0 alertas.
- **PR-3.20** Unit EWMA: caída sostenida 3 días → `ewma_drop`; caída de 1 solo día seguida de recuperación → no dispara (filtro de sostenido); pico sostenido → `ewma_spike`.
- **PR-3.21** Unit días-cero: mes con hueco de 3 días entre actividad → 1 alerta agrupada `zero_day` (desde/hasta/dias=3); hueco que coincide con ventana de mantenimiento → 0 alertas (RN-2.9); días futuros del mes en curso → no marcados.
- **PR-3.22** Unit operadores: caída de 5→2 operadores con 3 meses de historia → `operator_drop`; con < 3 meses → no evalúa.
- **PR-3.23** Idempotencia: correr el motor dos veces sobre los mismos datos → mismo nº de alertas (no duplica). Corregir el dato (recarga) que eliminó la causa → alerta abierta pasa a `resolved`.
- **PR-3.24** Exclusión por mantenimiento: día anómalo dentro de ventana → ninguna alerta; el mismo día fuera de ventana → alerta. (prueba parametrizada)
- **PR-3.25** Determinismo: dos ejecuciones independientes producen idéntico conjunto (orden y contenido) de alertas.

---

## 4. Motor de SLA, infracciones y meses consecutivos

### 4.1 Configuración de metas (`SLA`)
- **RF-4.1** Reutilizar la tabla `SLA` existente. Métrica principal de esta fase: `availability` (umbral por defecto p. ej. 95.0, periodo `mensual`). `puerto_id NULL` = meta global por defecto; una fila con `puerto_id` la sobreescribe.
- **RF-4.2** Resolución de meta efectiva para un puerto: `SLA` con `puerto_id` y `activo=True` → si no existe, la fila global (`puerto_id NULL`) → si no existe, constante por defecto del código.
- **RF-4.3** `GET /sla` (admin) lista metas; `GET /sla/{puerto_id}` devuelve la meta efectiva (cualquiera con `can_view_port`).
- **RF-4.4** `PUT /sla/{puerto_id}` (admin) crea/actualiza la meta del puerto (`metrica`, `umbral`, `periodo`, `activo`). Valida `0 ≤ umbral ≤ 100` para `availability`. Audita antes/después.
- **RF-4.5** `PUT /sla` con `puerto_id=null` (admin) fija la meta global por defecto.

### 4.2 Evaluación y registro de infracciones
- **RF-4.6** Para cada `(puerto, year, mes)` con datos, calcular disponibilidad **sobre días elegibles** (excluye mantenimiento, RN-2.10) y compararla con la meta efectiva.
- **RF-4.7** Si `valor_observado < umbral`, registrar una `Infraccion` (`sla_id`, `year`, `mes`, `valor_observado`, `valor_esperado=umbral`) y abrir/actualizar una `Alerta` tipo `sla_breach` enlazada (`infraccion.alerta_id`).
- **RN-4.8** **Idempotencia:** una sola infracción por `(puerto, sla_id, year, mes)`. Recalcular actualiza la existente; si el mes pasa a cumplir, la infracción se elimina/marca resuelta y su alerta se auto-resuelve.
- **RF-4.9** El cálculo se dispara en el hook de carga (§3.16) y bajo demanda (§5).

### 4.3 Meses consecutivos bajo la meta
- **RF-4.10** Endpoint/cálculo que, para un puerto, cuente la **racha de meses consecutivos** (hasta el último mes con datos) con infracción de `availability`. Expuesto en el estado del puerto (§6) y en `GET /sla/{puerto_id}/estado`.
- **RN-4.11** La racha se rompe con un mes que cumple, o con un mes **sin datos** que no esté completamente en mantenimiento (configurable: por defecto un mes sin datos rompe la racha y genera alerta `no_upload`).
- **RF-4.12** Severidad escalada por racha: 1 mes `warning`, ≥ `racha_critica` (por defecto 3) `critical`.

### Pruebas (SLA)
- **PR-4.13** Unit resolución de meta: puerto con meta propia → usa la propia; sin meta propia → global; sin global → constante por defecto.
- **PR-4.14** Unit evaluación: disponibilidad 92% vs meta 95% → infracción con `valor_observado=92, valor_esperado=95`; 96% vs 95% → sin infracción.
- **PR-4.15** Exclusión: mes con días en mantenimiento que, descontados, suben la disponibilidad por encima de la meta → sin infracción (RN-2.10).
- **PR-4.16** Idempotencia: recalcular no duplica infracción; corregir datos para cumplir → infracción y alerta se resuelven.
- **PR-4.17** Racha: 3 meses consecutivos bajo meta → racha=3, severidad `critical`; un mes intermedio que cumple → racha se reinicia.
- **PR-4.18** Permisos: `PUT /sla/{puerto}` por no-admin → 403; por admin → 200 + auditoría.
- **PR-4.19** Validación: umbral fuera de `[0,100]` → 400/422.

---

## 5. Endpoints de alertas

- **RF-5.1** `GET /alertas` — lista alertas con filtros `puerto_id?`, `estado?` (`open|acknowledged|resolved`), `tipo?`, `severidad?`, `limit/offset`. Respeta `allowed_port_ids`.
- **RF-5.2** `GET /alertas/resumen` — conteo de alertas abiertas por puerto y severidad (para insignias del mapa y badge global). Forma sugerida: `{ puerto_id: {critical, warning, info} }`.
- **RF-5.3** `POST /alertas/{id}/ack` — pasa `open → acknowledged` (admin o feeder del puerto). Audita.
- **RF-5.4** `POST /alertas/{id}/resolve` — pasa a `resolved`, fija `resuelta_en`, `resuelta_por`. Audita.
- **RF-5.5** `POST /alertas/recalcular/{puerto_id}/{year}/{mes}` (admin) — fuerza re-ejecución de anomalías + SLA para ese período (útil tras cambiar metas o ventanas). Audita.
- **RN-5.6** Ampliar `CheckConstraint` de `alertas.tipo` a: `sla_breach`, `no_upload`, `availability_low`, `anomaly_low`, `anomaly_high`, `ewma_drop`, `ewma_spike`, `zero_day`, `operator_drop` (RN-1.2 para la migración).
- **RN-5.7** `GET /alertas` ordena por `severidad` (critical→info) y luego `creada_en` desc.

### Pruebas (alertas API)
- **PR-5.8** `GET /alertas` filtra por estado y puerto; observador de otro puerto no ve alertas ajenas.
- **PR-5.9** `ack` y `resolve` cambian estado y auditan; doble `resolve` es idempotente o 409 (definir; por defecto idempotente).
- **PR-5.10** `recalcular` por admin regenera alertas; por no-admin → 403.
- **PR-5.11** Insertar alerta con tipo de anomalía nuevo no viola el CHECK (regresión de la migración RN-5.6).

---

## 6. Frontend — insignias en pines, avisos en dashboard, estado auditable

### 6.1 Insignias en los pines del mapa
- **RF-6.1** En `buildMap()` de [index.html](frontend/index.html), cada pin muestra una insignia con el conteo de alertas abiertas (color por severidad máxima: rojo `critical`, ámbar `warning`). Datos de `GET /alertas/resumen`.
- **RF-6.2** El tooltip del pin incluye la alerta más severa abierta.

### 6.2 Avisos en el dashboard del puerto
- **RF-6.3** En `renderDashboard()`, panel de alertas del puerto-mes: lista tipo, severidad, mensaje, fecha; botones **Reconocer/Resolver** visibles solo si el usuario puede mutar (RF-1.6).
- **RF-6.4** Aviso de racha de SLA ("3 meses consecutivos bajo la meta de 95%").

### 6.3 Reemplazo del semáforo por estado de SLA auditable
- **RF-6.5** Sustituir `getDispColor()` (umbrales fijos 95/90 hardcodeados) por un **estado de SLA derivado del backend**: el color/etiqueta viene de comparar disponibilidad del mes contra la **meta configurada del puerto** y la existencia de infracciones, no de constantes del front.
- **RF-6.6** Estados auditables (con tooltip explicativo): `CUMPLE` (verde), `EN RIESGO` (ámbar, dentro de margen configurable de la meta), `INCUMPLE` (rojo, infracción registrada), `EN MANTENIMIENTO` (gris/azul, mes mayormente excluido), `SIN DATOS` (neutro).
- **RF-6.7** El estado mostrado debe poder rastrearse: cada estado enlaza/expone la infracción o la meta que lo justifica (auditable = el usuario puede ver *por qué* está en rojo: meta X, observado Y, en período Z).
- **RNF-6.8** Reflejar el mismo estado en la columna **"Estado"** de la tabla (la `<th>Estado</th>` ya existente) y en la barra lateral, eliminando los umbrales mágicos del front.

### 6.4 Pantalla de administración de metas de SLA
- **RF-6.9** En `admin.html`, sección "Metas de SLA por puerto": tabla con cada puerto, su meta efectiva (propia/heredada de global), input para fijar `umbral` y `activo`, y la meta global por defecto editable. Guarda vía `PUT /sla/...`.
- **RF-6.10** Solo visible/operable para `admin` (la ruta `/admin` ya exige admin en backend).
- **RF-6.11** Gestión de ventanas de mantenimiento por puerto desde admin (crear/cerrar) — formulario que consume §2 API.

### Pruebas (frontend)
- **PR-6.12** *(manual / e2e con `/verify`)* Insignia aparece en el pin de un puerto con alerta abierta y desaparece al resolverla.
- **PR-6.13** *(manual)* Cambiar la meta de SLA de un puerto recalcula y cambia el color de estado de un mes que antes cumplía.
- **PR-6.14** *(manual)* Un mes marcado mayormente en mantenimiento muestra estado `EN MANTENIMIENTO`, no `INCUMPLE`.
- **PR-6.15** *(manual)* Usuario observador no ve botones Reconocer/Resolver.
- **RN-6.16** No se introducen librerías JS nuevas; el estado se calcula con datos servidos por el backend (sin reimplementar umbrales en el front).

---

## 7. Estrategia y cobertura de pruebas (resumen)

- **PR-7.1** Toda la lógica numérica (mediana, MAD, EWMA, exclusión de días, resolución de meta, racha) en **funciones puras** testeables sin BD → unit tests rápidos. Es el grueso de la cobertura.
- **PR-7.2** Las pruebas siguen el patrón existente en `backend/tests/`: `pytest` + `TestClient`, SQLite, fixtures `client/admin/feeder` de `conftest.py`, constructores `standard_xlsx/tcbuen_xlsx/rapiscan_xlsx`.
- **PR-7.3** Nuevos archivos sugeridos: `test_mantenimiento.py`, `test_anomalies.py`, `test_sla.py`, `test_alertas_api.py`. Reutilizan los builders de Excel para sembrar datos diarios realistas (varios días/meses).
- **PR-7.4** Fixture nuevo: helper que carga N meses de datos sintéticos de un puerto (serie con tendencia + outliers controlados) para alimentar anomalías/SLA de forma determinista.
- **PR-7.5** Pruebas de permisos para **cada** endpoint nuevo: 401 sin sesión, 403 por rol insuficiente, 200 por rol correcto (espejo de `test_audit_api.py`).
- **PR-7.6** Pruebas de auditoría: cada mutación nueva deja rastro verificable en `/api/audit` y no rompe `/api/audit/verify`.
- **PR-7.7** Pruebas de idempotencia/determinismo (PR-3.23, PR-3.25, PR-4.16) como red de seguridad contra duplicación de alertas en recargas.
- **PR-7.8** Regresión de migración (PR-5.11): el CHECK ampliado de `alertas.tipo` acepta todos los tipos nuevos.
- **PR-7.9** Meta de cobertura: ≥ 90% de líneas en `anomalies.py`, `sla.py`, `mantenimiento` (módulos de lógica pura). Endpoints: al menos un caminito feliz + permisos por cada uno.

---

## 8. Criterios de aceptación (Definition of Done)

1. Cargar un archivo con una caída anómala genera una alerta visible en el pin y el dashboard; corregir el dato la resuelve sola.
2. Un día/periodo marcado como mantenimiento **no** genera anomalías **ni** cuenta contra el SLA (verificable en una prueba).
3. El admin puede fijar la meta de SLA por puerto y una meta global; el estado de color cambia en consecuencia, sin tocar constantes del front.
4. El estado verde/ámbar/rojo es **auditable**: el usuario puede ver meta, valor observado y período que lo justifican.
5. La racha de meses consecutivos bajo la meta se calcula y se muestra, escalando severidad.
6. Todas las mutaciones quedan en la auditoría y `/api/audit/verify` sigue OK.
7. Suite de pruebas verde, incluyendo unit (numérico), integración (endpoints), permisos, idempotencia y regresión de migración.

---

## 9. Riesgos y decisiones abiertas

- **D-1 (numpy):** ¿se permite añadir `numpy` al backend o se implementa la estadística a mano? Recomendación: a mano (volumen pequeño, sin dependencia nueva — RNF-1.10).
- **D-2 (parámetros de anomalías):** globales por código vs. configurables por puerto en BD. Recomendación: globales en esta fase; tabla de parámetros por puerto en una fase posterior si hay falsos positivos.
- **D-3 (mes sin datos):** ¿rompe la racha de SLA y genera `no_upload`, o se ignora? Recomendación: genera `no_upload` salvo que el mes esté completamente en mantenimiento (RN-4.11).
- **D-4 (quién resuelve alertas):** ¿solo admin, o también feeder del puerto? Recomendación: admin + feeder del puerto (RF-1.6).
- **D-5 (migración del CHECK en producción):** requiere ventana de despliegue con `ALTER TABLE` en Postgres; en SQLite/test es transparente. Confirmar permisos de BD en Railway.
- **D-6 (recálculo histórico):** al cambiar una meta o una ventana, ¿se recalculan automáticamente los meses pasados o solo bajo `POST /alertas/recalcular`? Recomendación: manual vía endpoint para no recalcular todo el histórico en cada edición.

---

## 10. Mapa de archivos a tocar (referencia de implementación)

| Componente | Archivo | Acción |
|---|---|---|
| Tablas `VentanaMantenimiento`, ampliación CHECK `alertas.tipo` | [models.py](backend/models.py) | nuevo modelo + CHECK |
| Migraciones `_ensure_*` (tabla mantenimiento, CHECK, columnas) | [database.py](backend/database.py) | nuevas funciones idempotentes |
| Motor de anomalías | `backend/anomalies.py` | **nuevo** |
| Motor de SLA + infracciones + racha | `backend/sla.py` | **nuevo** |
| Helper `dias_excluidos` compartido | `backend/mantenimiento.py` | **nuevo** |
| Hook al guardar + endpoints alertas/SLA/mantenimiento | [main.py](backend/main.py) | nuevos endpoints + hook en `process_upload` |
| Permisos de mutación de alertas | [auth.py](backend/auth.py) | helper `can_manage_alerts` |
| Insignias pin + panel alertas + estado SLA auditable | [index.html](frontend/index.html) | reemplazar `getDispColor`, `buildMap`, `renderDashboard` |
| Pantalla de metas SLA + ventanas mantenimiento | [admin.html](frontend/admin.html) | nueva sección admin |
| Pruebas | `backend/tests/test_{mantenimiento,anomalies,sla,alertas_api}.py` | **nuevas** |

---

## 11. Orden de implementación recomendado (dependencias)

1. **Ventanas de mantenimiento** (§2) — base de las exclusiones; sin esto los otros dos motores no son correctos.
2. **Motor de SLA + metas + infracciones + racha** (§4) — reutiliza tablas existentes, desbloquea el estado auditable.
3. **Estado de SLA auditable en el front** (§6.3) — reemplazo del semáforo, valor visible inmediato.
4. **Motor de anomalías** (§3) — el más complejo y el que más calibración necesita.
5. **Endpoints de alertas + insignias + panel** (§5, §6.1–6.2) — capa de presentación sobre lo anterior.
6. **Pantalla admin de metas y mantenimiento** (§6.4).

> Cada paso entrega valor verificable y deja la suite de pruebas verde antes de avanzar.
