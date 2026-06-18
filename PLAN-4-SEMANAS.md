PROTACTICS Plan de Trabajo

Cronograma: 16 jun 2026 ~ 7 jul 2026 (4 semanas)
Presupuesto: USD $1.040

Semana 1. Base de Datos, Carga Inteligente y Auditoría - $320 (31%)
- Diseñar el esquema de las tablas nuevas (alertas, SLA, infracciones, auditoría)
- Crear migraciones siguiendo el patrón ALTER TABLE existente (sin perder datos)
- Carga masiva inteligente: endpoint para subir hasta ~100 archivos de una vez
- Auto-enrutamiento de cada archivo al puerto/año/mes correcto leído del archivo
- Respaldo con IA: deducir el período desde el contenido cuando el nombre no trae fecha
- Arrastrar-y-soltar: subir un archivo soltándolo sobre la tarjeta del mes correcto
- Pista de auditoría: tabla inmutable (append-only) + registro de quién hizo qué y cuándo
- Enganchar la auditoría en carga, edición, aprobación de usuarios e inicio de sesión

Semana 2. Inteligencia Operacional (Anomalías + SLA) - $240 (23%)
- Motor de detección de anomalías: mediana móvil + MAD por día de la semana
- Carta de control EWMA para caídas y picos bruscos sostenidos
- Detección de días en cero dentro de un mes activo + caída de operadores
- Excepciones para evitar falsos positivos: el mantenimiento programado y las caídas
  técnicas del escáner NO generan alertas
- Marcar períodos de mantenimiento / inactividad técnica para excluirlos tanto de las
  anomalías como del cálculo de SLA
- Endpoints de alertas + insignias en los pines del mapa y avisos en el dashboard
- Motor de SLA: meta configurable por puerto + ventanas de mantenimiento
- Registro de infracciones y seguimiento de meses consecutivos bajo la meta
- Pantalla de administración para fijar las metas de SLA por puerto
- Reemplazar el semáforo verde/amarillo/rojo por estado de SLA auditable

Semana 3. Reportes y Analítica Nacional - $240 (23%)
- Informes PDF con marca (por puerto y consolidado nacional)
- Anexo de datos en Excel con gráficos (reutiliza openpyxl ya instalado)
- Entrega de informes con un clic + envío por correo
- Vista "Centro de Mando": totales nacionales, ranking, variación mensual/interanual
- Mapa coroplético en tiempo real con línea de tiempo para reproducir el histórico

Semana 4. Búsqueda de Imágenes por Contenedor, Pruebas y Puesta en Producción - $240 (23%)
- Asociar imágenes al número de contenedor (modelo de datos + vínculo por contenedor)
- Almacenamiento de imágenes referenciadas, sin precarga en el dashboard
- Búsqueda de imágenes SOLO a solicitud del observador (bajo demanda)
- Carga diferida (lazy loading) para no afectar el rendimiento del sistema
- Visor de imágenes por contenedor con control de acceso por rol
- Pruebas de punta a punta de todas las funciones y flujos
- Despliegue en producción
- Documentación técnica + repositorio organizado

Si un solo desarrollador se encarga del desarrollo, este tardará más de dos meses,
incluyendo el funcionamiento completo del sistema y la corrección de errores. Nuestro
equipo completará esta tarea en cuatro semanas.
