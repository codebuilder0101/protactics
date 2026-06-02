# ============================================================
#  PROTACTICS — Imagen de producción (servicio único)
#  Sirve la API FastAPI Y el dashboard estático desde un solo
#  contenedor. Pensada para Railway / Render / Fly.io.
#  Contexto de build: la RAÍZ del repositorio.
# ============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Dependencias primero (mejor cacheo de capas)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 2) Código del backend y el frontend que sirve
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# 3) Ejecutar desde backend/ para que las rutas relativas de
#    main.py ("../frontend") resuelvan correctamente.
WORKDIR /app/backend

EXPOSE 8000

# 4) Escuchar en el puerto que asigne la plataforma ($PORT) o 8000 en local.
#    init_db() crea las tablas y siembra los 7 puertos al arrancar.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
