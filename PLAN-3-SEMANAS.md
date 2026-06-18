Plan de Trabajo de 3 Semanas — PROTACTICS (Dashboard Escáner Portuario)

Cronograma: 16-jun-2026 → 4-jul-2026 (3 semanas)
Presupuesto: USD $800

Semana 1 — Base de Datos, Carga Inteligente y Auditoría
- Diseñar el esquema de las tablas nuevas (alertas, SLA, infracciones, auditoría)
- Crear migraciones siguiendo el patrón ALTER TABLE existente (sin perder datos)
- Carga masiva inteligente: endpoint para subir hasta ~100 archivos de una vez
- Auto-enrutamiento de cada archivo al puerto/año/mes correcto leído del archivo
- Respaldo con IA: deducir el período desde el contenido cuando el nombre no trae fecha
- Arrastrar-y-soltar: subir un archivo soltándolo sobre la tarjeta del mes correcto
- Pista de auditoría: tabla inmutable (append-only) + registro de quién hizo qué y cuándo
- Enganchar la auditoría en carga, edición, aprobación de usuarios e inicio de sesión

Semana 2 — Inteligencia Operacional (Anomalías + SLA)
- Motor de detección de anomalías: mediana móvil + MAD por día de la semana
- Carta de control EWMA para caídas y picos bruscos sostenidos
- Detección de días en cero dentro de un mes activo + caída de operadores
- Endpoints de alertas + insignias en los pines del mapa y avisos en el dashboard
- Motor de SLA: meta configurable por puerto + ventanas de mantenimiento
- Registro de infracciones y seguimiento de meses consecutivos bajo la meta
- Pantalla de administración para fijar las metas de SLA por puerto
- Reemplazar el semáforo verde/amarillo/rojo por estado de SLA auditable

Semana 3 — Reportes, Analítica Nacional y Entrega
- Informes PDF con marca (por puerto y consolidado nacional)
- Anexo de datos en Excel con gráficos (reutiliza openpyxl ya instalado)
- Entrega de informes con un clic + envío por correo
- Vista "Centro de Mando": totales nacionales, ranking, variación mensual/interanual
- Mapa coroplético en tiempo real con línea de tiempo para reproducir el histórico
- Pruebas de punta a punta de todas las funciones y flujos
- Despliegue en producción (Railway + Vercel) + documentación técnica

Cronograma resumido
- Semana 1 · 16–20 jun · Base de datos, carga inteligente y auditoría
- Semana 2 · 23–27 jun · Anomalías y motor de SLA
- Semana 3 · 30 jun – 4 jul · Reportes, analítica nacional y entrega

Presupuesto
- Total: USD $800 (proyecto completo, 3 semanas)
- Hito 1 — Inicio (16-jun): $320 (40%)
- Hito 2 — Fin Semana 2 (27-jun): $240 (30%)
- Hito 3 — Entrega final (4-jul): $240 (30%)
