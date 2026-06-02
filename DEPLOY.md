# PROTACTICS — Guía de Despliegue Online

Este proyecto se despliega como **un solo servicio**: el backend FastAPI sirve
tanto la API como el dashboard estático (`frontend/index.html`). No necesitas un
host separado para el frontend (no hace falta Vercel).

El frontend detecta su propia URL automáticamente:

```js
const API_URL = window.location.hostname === 'localhost'
  ? 'http://localhost:8000' : window.location.origin;
```

Por eso, al servirse desde el mismo dominio que la API, **no requiere ninguna
configuración**: funciona sin tocar CORS ni URLs.

---

## Archivos de despliegue incluidos

| Archivo | Para qué sirve |
|---------|----------------|
| `Dockerfile` (raíz) | Imagen de producción que empaqueta backend **y** frontend |
| `.dockerignore` | Excluye `.venv`, `*.db`, `*.xlsx`, `reference/`, etc. de la imagen |
| `railway.json` | Configuración de build para Railway |
| `render.yaml` | Blueprint para Render (web + PostgreSQL) |

> El `Dockerfile` de la raíz es el de **producción**. El `backend/Dockerfile`
> existente se sigue usando solo para `docker-compose` en local.

---

## Opción A — Railway (recomendada)

1. Sube el repositorio a GitHub (ver "Antes de desplegar" más abajo).
2. En https://railway.app → **New Project → Deploy from GitHub repo** → elige este repo.
   Railway detecta el `Dockerfile` de la raíz y construye la imagen.
3. En el proyecto: **+ New → Database → PostgreSQL**. Railway crea la base y genera
   su variable `DATABASE_URL`.
4. En tu **servicio web → Variables**, añade `DATABASE_URL` referenciando la del
   servicio PostgreSQL (Railway permite `${{Postgres.DATABASE_URL}}`).
   - `database.py` ya convierte `postgres://` → `postgresql://`, así que no hay que tocar código.
5. Deploy. Al primer arranque, `init_db()` crea las tablas y siembra los 7 puertos.
6. **Settings → Networking → Generate Domain** → obtienes una URL pública
   (ej. `https://protactics.up.railway.app`). Ábrela: el dashboard carga y ya
   está conectado a su propia API.

Coste aproximado: ~5 USD/mes tras el crédito de prueba. Sin "cold starts".

---

## Opción B — Render (alternativa gratuita)

**Con Blueprint (automático):**
1. Sube el repo a GitHub.
2. En https://render.com → **New → Blueprint** → selecciona el repo.
   Render lee `render.yaml` y crea el servicio web + la base PostgreSQL,
   inyectando `DATABASE_URL` automáticamente.
3. Deploy. Abre la URL pública que genera Render.

**Manual (sin Blueprint):**
1. **New → PostgreSQL** (plan free) → copia su *Internal Database URL*.
2. **New → Web Service** → conecta el repo → Runtime **Docker**.
3. En *Environment*, añade `DATABASE_URL` con el valor del paso 1.
4. Render asigna `$PORT` (el `Dockerfile` ya lo respeta). Deploy.

Nota: el plan free "duerme" tras ~15 min de inactividad (arranque en frío de ~30s)
y la base gratuita expira a los 90 días.

---

## Antes de desplegar

```bash
git add Dockerfile .dockerignore railway.json render.yaml DEPLOY.md
git commit -m "Deploy: Dockerfile produccion (frontend+backend) + configs"
git push
```

Checklist:
- [ ] No subir los `.xlsx` grandes (130MB/75MB), ni `.venv`, ni `*.db`.
      Ya están en `.gitignore` y `.dockerignore`. ✅
- [ ] `DATABASE_URL` lo provee la plataforma (NO reutilices la contraseña local
      `TopDeveloper123!@#`; es solo para tu PostgreSQL de desarrollo).
- [ ] Tras desplegar, abre `/docs` y sube un reporte real para confirmar que
      persiste en la base de producción.

---

## Verificación post-despliegue

| Comprobación | Resultado esperado |
|--------------|--------------------|
| `GET /` | Carga el dashboard |
| `GET /docs` | Swagger UI de la API |
| `GET /puertos` | Lista los 7 puertos (sembrados al arrancar) |
| Subir XLS en `/docs` | `{"ok": true, ...}` y datos visibles en el dashboard |

---

## Notas importantes

- **Subida de archivos grandes:** los reportes de mes completo pesan mucho
  (130MB/75MB). Las plataformas tienen límites de tamaño de petición y *timeouts*
  (p. ej. Render free corta a ~100s). Si subes archivos enormes, considera un plan
  de pago o pre-procesarlos. Los archivos pequeños/normales funcionan sin problema.
- **Base de datos persistente:** las bases gratuitas son pequeñas o temporales.
  Para algo más que una demo, presupuesta ~5–7 USD/mes por una PostgreSQL estable.
- **CORS:** actualmente `allow_origins=["*"]`. Al ser un único dominio no es
  necesario, pero si algún día separas el frontend, restríngelo a tu dominio.
- **Un solo worker:** el `Dockerfile` arranca uvicorn con un worker, suficiente
  para esta app. Si necesitas más capacidad, escala con réplicas en la plataforma.
