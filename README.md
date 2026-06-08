# PROTACTICS — Dashboard Escáner Portuario

# Server Start Command
powershell -ExecutionPolicy Bypass -File run.ps1


Sistema de monitoreo operacional para 7 escáneres portuarios en Colombia.

---

## Estructura del Proyecto

```
protactics/
├── frontend/
│   └── index.html          ← Dashboard completo (funciona solo sin backend)
├── backend/
│   ├── main.py             ← API FastAPI
│   ├── models.py           ← Modelos SQLAlchemy
│   ├── database.py         ← Conexión BD + seed de puertos
│   ├── parsers/
│   │   ├── __init__.py     ← Auto-detector de formato
│   │   ├── standard.py     ← Formato A (Miniatura)
│   │   ├── rapiscan.py     ← Formato B (Cargo Inspection Report)
│   │   └── tcbuen.py       ← Formato C (Estado numérico 100)
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Opción 1 — Solo Frontend (sin backend, sin instalación)

Abrir `frontend/index.html` en cualquier navegador. Funciona completamente offline.
Los datos se pierden al cerrar el navegador.

---

## Opción 2 — Con Backend (datos persistentes)

### Desarrollo local

**Requisitos:** Docker Desktop instalado.

```bash
# 1. Clonar o descomprimir el proyecto
cd protactics

# 2. Levantar todo (PostgreSQL + API)
docker-compose up --build

# 3. Abrir en el navegador
# API:      http://localhost:8000
# Docs API: http://localhost:8000/docs
# Frontend: abrir frontend/index.html (o http://localhost:8000/app)
```

### Activar la conexión en el frontend

En `frontend/index.html`, buscar la línea:
```javascript
const USE_API = false;
```
Cambiar a:
```javascript
const USE_API = true;
```

---

## Opción 3 — Deploy en Producción (Railway + Vercel)

### Backend en Railway

1. Crear cuenta en https://railway.app
2. Nuevo proyecto → "Deploy from GitHub repo"
3. Seleccionar la carpeta `backend/`
4. Railway detecta el `Dockerfile` automáticamente
5. Agregar servicio PostgreSQL → Railway genera `DATABASE_URL`
6. En Variables de entorno del backend, Railway ya inyecta `DATABASE_URL`
7. Anotar la URL pública del backend (ej: `https://protactics-api.up.railway.app`)

### Frontend en Vercel

1. Crear cuenta en https://vercel.com
2. Nuevo proyecto → importar desde GitHub
3. Seleccionar carpeta `frontend/`
4. En `frontend/index.html` cambiar:

```javascript
const USE_API = true;
const API_URL = 'https://TU-URL-DE-RAILWAY.up.railway.app';
```

5. Deploy → Vercel genera URL pública del dashboard

---

## Endpoints de la API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/puertos` | Lista todos los puertos con stats |
| GET | `/meses/{puerto_id}` | Meses con datos para un puerto |
| GET | `/data/{puerto_id}/{year}/{mes}` | Dashboard data de un mes |
| POST | `/upload/{puerto_id}/{year}/{mes}` | Subir archivo XLS |
| PUT | `/disponibilidad/{puerto_id}/{year}/{mes}` | Guardar disponibilidad |
| GET | `/disponibilidad/{puerto_id}` | Historial de disponibilidad |

Documentación interactiva: `http://localhost:8000/docs`

---

## Formatos de Archivo Soportados

| Formato | Puertos | Identificación | Filtro |
|---------|---------|---------------|--------|
| Standard | SPR Buenaventura, Barranquilla, Santa Marta, Pto. Antioquia | Columna `Miniatura` con valor | Miniatura no-nula |
| Rapiscan | SPR Buenaventura (legacy), Aguadulce | Contiene "Scan Date & Time" | Tabla resumen diaria |
| TCBUEN | TCBUEN | Estado numérico 100/102 | Estado === 100 |

---

## Variables de Entorno (Backend)

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATABASE_URL` | URL de PostgreSQL | `sqlite:///./protactics.db` |
| `PORT` | Puerto del servidor | `8000` |

---

## Semáforo de Disponibilidad

| Rango | Color | Estado |
|-------|-------|--------|
| 95% – 100% | 🟢 Verde | Óptima |
| 90% – 94.9% | 🟡 Amarillo | Aceptable |
| < 90% | 🔴 Rojo | Por debajo del umbral |

---

*PROTACTICS · Dashboard Escáner Portuario Colombia · 2026*
