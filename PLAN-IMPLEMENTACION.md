# PROTACTICS — Plan Detallado de Implementación

**Qué se va a hacer, tarea por tarea · Presupuesto · Fecha límite**

| | |
|---|---|
| **Tipo** | Plan de ejecución técnico (interno + cliente) |
| **Equipo** | 5 desarrolladores en paralelo |
| **Tarifa** | USD $320 / día-desarrollador ($40/h) |
| **Inicio** | Lunes 16-jun-2026 |
| **Fecha límite (entrega)** | Viernes 25-jul-2026 (6 semanas) |
| **Presupuesto total** | USD $29.440 (base) · $32.384 con contingencia 10% |

> Cada función está descrita como una **lista de tareas concretas** sobre los archivos reales del
> proyecto (`backend/models.py`, `backend/main.py`, `frontend/index.html`, `backend/parsers/…`),
> con su esfuerzo en días-desarrollador.

---

## Semana 0 → Semana 1 · Fundaciones compartidas (todo el equipo)

Antes de tocar funciones, lo que voy a hacer en los primeros días:

1. **Recolectar archivos de muestra reales** de cada puerto y formato (standard / rapiscan / tcbuen).
2. **Diseño del esquema de base de datos** para las 5 tablas nuevas (alertas, SLA config,
   infracciones, auditoría) — definir columnas y relaciones en una sola revisión.
3. **Acordar las interfaces entre funciones** (los informes consumen datos de SLA y de alertas; el
   mapa consume la analítica nacional) para que el desarrollo en paralelo no choque.
4. **Preparar entorno**: rama de trabajo, migraciones siguiendo el patrón existente
   (`_ensure_user_columns` / `_ensure_daily_schema` en `database.py` usan `ALTER TABLE` para no
   perder datos — replico ese patrón para cada tabla nueva).

**Esfuerzo:** 4 días-dev · **Costo:** $1.280

---

## Función 1 · Detección de anomalías y alertas — Dev A

**Esfuerzo: 14 días-dev · $4.480**

| # | Tarea concreta | Archivo / componente |
|---|---|---|
| 1.1 | Crear modelo `Alerta` (puerto_id, year, mes, dia, tipo, severidad, métrica, valor, esperado, mensaje, estado `nueva/reconocida`, creada_en) | `backend/models.py` |
| 1.2 | Migración con `ALTER TABLE` siguiendo el patrón de `database.py` | `backend/database.py` |
| 1.3 | Nuevo módulo `anomalies.py`: mediana móvil + MAD por día de la semana | `backend/anomalies.py` |
| 1.4 | Carta de control EWMA para caídas/picos sostenidos | `backend/anomalies.py` |
| 1.5 | Detección de días en cero dentro de un mes activo | `backend/anomalies.py` |
| 1.6 | Detección de caída en número de operadores vs. histórico | `backend/anomalies.py` |
| 1.7 | Ejecutar la detección automáticamente al guardar datos | hook en `save_parsed_data()` de `main.py` |
| 1.8 | Endpoints `GET /alertas` (filtros) y `POST /alertas/{id}/ack` | `backend/main.py` |
| 1.9 | Insignias de alerta en los pines del mapa | `buildMap()` en `frontend/index.html` |
| 1.10 | Panel de alertas + avisos en el dashboard del puerto | `renderDashboard()` en `frontend/index.html` |
| 1.11 | Calibración de umbrales con datos reales + pruebas | — |

---

## Función 2 · Motor de cumplimiento de SLA — Dev B

**Esfuerzo: 13 días-dev · $4.160**

| # | Tarea concreta | Archivo / componente |
|---|---|---|
| 2.1 | Modelo `SLAConfig` (puerto_id, meta_pct, ventanas de mantenimiento, exclusiones) | `backend/models.py` |
| 2.2 | Modelo `SLAInfraccion` (puerto_id, year, mes, valor, meta, severidad, creada_en) | `backend/models.py` |
| 2.3 | Migraciones de ambas tablas | `backend/database.py` |
| 2.4 | Módulo `sla.py`: cálculo de disponibilidad real (planificado vs. no planificado, exclusiones) | `backend/sla.py` |
| 2.5 | Seguimiento de **meses consecutivos por debajo de la meta** + cumplimiento acumulado | `backend/sla.py` |
| 2.6 | Reemplazar/encapsular `compute_availability()` con el motor de SLA | `backend/main.py` |
| 2.7 | Endpoints `GET/PUT /sla/config/{puerto_id}`, `GET /sla/cumplimiento`, `GET /sla/infracciones` | `backend/main.py` |
| 2.8 | UI de administración para fijar metas por puerto | nueva sección en `frontend/admin.html` |
| 2.9 | Sustituir el semáforo (verde/amarillo/rojo) por estado de SLA + historial de infracciones | `frontend/index.html` |
| 2.10 | Pruebas con períodos históricos | — |

---

## Función 3 · Informes PDF / Excel con marca — Dev C

**Esfuerzo: 11 días-dev · $3.520**

| # | Tarea concreta | Archivo / componente |
|---|---|---|
| 3.1 | Añadir dependencias de reportes (WeasyPrint/ReportLab + matplotlib). `openpyxl` **ya está** | `backend/requirements.txt` |
| 3.2 | Módulo `reports.py`: PDF mensual por puerto (KPIs + estado SLA + alertas + gráficos) | `backend/reports.py` |
| 3.3 | Renderizado de gráficos del lado del servidor como imágenes embebidas | `backend/reports.py` |
| 3.4 | PDF consolidado nacional | `backend/reports.py` |
| 3.5 | Anexo Excel reutilizando `openpyxl` | `backend/reports.py` |
| 3.6 | Plantilla con marca institucional (logo, colores) | recurso + `reports.py` |
| 3.7 | Endpoints `GET /reportes/pdf/...`, `/reportes/excel/...`, `/reportes/nacional/...` | `backend/main.py` |
| 3.8 | Botones de exportación en dashboard y vista nacional | `frontend/index.html` |
| 3.9 | Validación de salidas con datos reales | — |

---

## Función 4 · Analítica nacional y mapa coroplético — Dev D

**Esfuerzo: 15 días-dev · $4.800**

| # | Tarea concreta | Archivo / componente |
|---|---|---|
| 4.1 | Endpoint `GET /nacional/resumen` (totales, rankings) | `backend/main.py` |
| 4.2 | Endpoint `GET /nacional/mapa` (disponibilidad/volumen por puerto) | `backend/main.py` |
| 4.3 | Deltas mensual e interanual (MoM / YoY) | `backend/main.py` |
| 4.4 | Nueva vista "Centro de Mando" | nueva sección `view-` en `frontend/index.html` |
| 4.5 | Convertir el SVG estático en **mapa coroplético** que colorea por disponibilidad/uso | `buildMap()` en `frontend/index.html` |
| 4.6 | **Línea de tiempo** para reproducir el histórico | `frontend/index.html` |
| 4.7 | Mapa de calor por departamento + tabla de ranking + panel de variaciones | `frontend/index.html` |
| 4.8 | Restringir la vista a roles `admin` / `observador_global` | `auth.py` + frontend |
| 4.9 | Pruebas | — |

---

## Función 5 · Carga masiva inteligente + arrastrar-y-soltar — Dev E

**Esfuerzo: 12 días-dev · $3.840**

> Extiende código probado: `period_from_filename()` (en `parsers/dates.py`) ya lee la fecha del
> nombre, y `upload_file()` ya bloquea el mes equivocado. Aquí se generaliza a lotes y a la
> lectura desde el contenido.

| # | Tarea concreta | Archivo / componente |
|---|---|---|
| 5.1 | Endpoint `POST /upload/bulk` que acepta hasta ~100 archivos | `backend/main.py` |
| 5.2 | Para cada archivo: `detect_format` + `period_from_filename` para enrutar a año/mes correctos | reutiliza `parsers/__init__.py` |
| 5.3 | **Respaldo con IA / contenido**: si el nombre no trae fecha, deducir el período desde las filas (`to_ymdh`) | `parsers/dates.py` |
| 5.4 | Detección de conflictos + nivel de confianza (nombre vs. contenido) antes de confirmar | `backend/main.py` |
| 5.5 | Inferencia/confirmación del puerto del lote (por nombre o selección) | `backend/main.py` |
| 5.6 | Reporte por archivo: cargado / omitido / conflicto | respuesta JSON + UI |
| 5.7 | UI de carga masiva con resultados por archivo | `frontend/index.html` |
| 5.8 | **Arrastrar-y-soltar** un archivo sobre la tarjeta del mes → carga automática si corresponde | `openMonths()` en `frontend/index.html` |
| 5.9 | Pruebas con un lote de ~100 archivos | — |

---

## Función 6 · Pista de auditoría / cadena de custodia — Dev E (tras F5)

**Esfuerzo: 9 días-dev · $2.880**

| # | Tarea concreta | Archivo / componente |
|---|---|---|
| 6.1 | Modelo `AuditLog` **append-only** (actor_user_id, acción, entidad, entidad_id, detalle, ip, creado_en) | `backend/models.py` |
| 6.2 | Migración de la tabla | `backend/database.py` |
| 6.3 | Helper `registrar_auditoria()` reutilizable | `backend/audit.py` |
| 6.4 | Enganchar en carga de archivos, `PUT /disponibilidad`, aprobar/rechazar, CRUD de usuarios y login | `main.py` + `auth.py` |
| 6.5 | Endpoint `GET /auditoria` (solo admin, con filtros) + exportación CSV | `backend/main.py` |
| 6.6 | Nueva página de auditoría para el administrador | nuevo `frontend/auditoria.html` (modelo: `approvals.html`) |
| 6.7 | Pruebas de inmutabilidad | — |

---

## Semanas 4–6 · Cierre (todo el equipo)

| Concepto | Qué voy a hacer | Días-dev | Costo |
|---|---|:---:|---:|
| Integración | Conectar informes ↔ SLA/alertas; mapa ↔ analítica nacional | 4 | $1.280 |
| QA / UAT | Pruebas integrales + pruebas de aceptación con el cliente | 6 | $1.920 |
| Despliegue / docs / capacitación | Desplegar (Railway + Vercel, ya configurado), documentar, capacitar al cliente | 4 | $1.280 |

---

## Cronograma — 6 semanas

| Semana | Fechas | Qué se hace |
|:---:|---|---|
| 1 | 16–20 jun | Fundaciones: muestras, esquema BD, interfaces, entorno. Inicio de desarrollo. |
| 2 | 23–27 jun | Desarrollo en paralelo de F1–F6. |
| 3 | 30 jun – 4 jul | Desarrollo en paralelo. Demos internas. |
| 4 | 7–11 jul | Cierre de desarrollo + integración entre funciones. **Hito: funciones núcleo (F1–F3).** |
| 5 | 14–18 jul | Integración final + QA + UAT con el cliente. |
| 6 | 21–25 jul | Endurecimiento, despliegue, documentación, capacitación. **Entrega final.** |

```
Sem:           1     2     3     4     5     6
F1 Anomalías     ████████████████░░
F2 SLA           ████████████████░░
F3 Reportes        ██████████████████░
F4 Nacional      ██████████████████░░
F5 Ingesta       ████████████░░
F6 Auditoría           ████████████░░
Integración                     ██████░
QA / UAT                          ████████
Despliegue                             ██████
```

---

## Resumen de presupuesto

| Bloque | Días-dev | Costo (USD) |
|---|:---:|---:|
| F1 Anomalías | 14 | $4.480 |
| F2 SLA | 13 | $4.160 |
| F3 Reportes | 11 | $3.520 |
| F4 Nacional | 15 | $4.800 |
| F5 Ingesta inteligente | 12 | $3.840 |
| F6 Auditoría | 9 | $2.880 |
| Fundaciones (Semana 1) | 4 | $1.280 |
| Integración | 4 | $1.280 |
| QA / UAT | 6 | $1.920 |
| Despliegue / docs / capacitación | 4 | $1.280 |
| **TOTAL BASE** | **92** | **$29.440** |
| Contingencia 10% (opcional) | — | $2.944 |
| **TOTAL CON CONTINGENCIA** | | **$32.384** |

---

## Hitos de pago

| Hito | Cuándo | % | Monto |
|---|---|:---:|---:|
| 1 — Firma / kickoff | 16-jun | 30% | $8.832 |
| 2 — Funciones núcleo (F1, F2, F3) | 11-jul | 40% | $11.776 |
| 3 — Entrega final + UAT aprobada | 25-jul | 30% | $8.832 |

---

## Supuestos

- Equipo de **5 desarrolladores en paralelo** a **$320/día**. Con menos personas, el calendario se
  alarga proporcionalmente; el costo en días-dev no cambia.
- El cliente entrega archivos de muestra reales, imagen institucional y metas de SLA por puerto en
  la Semana 1.
- **No incluye** costos de infraestructura en la nube (hosting, base de datos gestionada, correo
  saliente para informes), que se facturan por separado.
- La contingencia del 10% solo se factura si se utiliza.

---

*PROTACTICS · Plan Detallado de Implementación · Junio 2026*
