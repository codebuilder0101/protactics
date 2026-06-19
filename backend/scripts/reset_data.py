"""
Vacía los DATOS de la base de datos conservando el ESQUEMA (tablas y columnas).

Qué borra (TRUNCATE … RESTART IDENTITY):
    escaneos_horarios, escaneos_diarios, operadores, disponibilidad,
    archivos_cargados, infracciones, alertas, auditoria
Qué CONSERVA por defecto: puertos (los 7 puertos) y users (tus cuentas).

Notas:
  • auditoria se vacía con TRUNCATE (el trigger de inmutabilidad bloquea
    DELETE/UPDATE, pero NO se dispara con TRUNCATE).
  • Es una acción DESTRUCTIVA en producción: exige confirmación explícita.

USO (con tu CLI autenticada; la credencial no sale de tu máquina):
    cd backend
    railway login
    railway link                       # elige el proyecto
    railway run --service protactics-db .venv/Scripts/python.exe scripts/reset_data.py --yes

Opciones:
    --yes            Confirma y ejecuta (sin esto, solo muestra qué haría).
    --wipe-users     ADEMÁS borra users y user_sessions (tendrás que volver a
                     registrar el primer admin). Úsalo solo si quieres empezar
                     totalmente de cero.
    --wipe-sessions  Cierra todas las sesiones (no borra usuarios).
"""
import os
import sys

try:
    import psycopg2
except ImportError:
    sys.exit("Falta psycopg2. Instala las deps del backend: pip install -r requirements.txt")

CONFIRM        = ("--yes" in sys.argv) or os.getenv("CONFIRM_RESET") == "YES"
WIPE_USERS     = "--wipe-users" in sys.argv
WIPE_SESSIONS  = "--wipe-sessions" in sys.argv

DATA_TABLES = [
    "escaneos_horarios", "escaneos_diarios", "operadores", "disponibilidad",
    "archivos_cargados", "infracciones", "alertas", "auditoria",
]
if WIPE_USERS:
    DATA_TABLES += ["user_sessions", "users"]   # users referencia user_sessions
elif WIPE_SESSIONS:
    DATA_TABLES += ["user_sessions"]

url = (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or "").strip()
if not url:
    sys.exit("DATABASE_URL no está definida.\n"
             "Ejecuta con:  railway run --service protactics-db python scripts/reset_data.py --yes")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

conn = psycopg2.connect(url)
cur = conn.cursor()

# Conteo antes (informativo).
print("Filas actuales por tabla:")
for t in DATA_TABLES:
    cur.execute(f"SELECT count(*) FROM {t}")
    print(f"  {t:20s} {cur.fetchone()[0]}")

if not CONFIRM:
    print("\n[simulación] No se borró nada. Añade --yes para ejecutar de verdad.")
    print("Se conservan: puertos" + ("" if WIPE_USERS else ", users"))
    cur.close(); conn.close()
    sys.exit(0)

# TRUNCATE en una sola sentencia (resuelve dependencias entre las tablas listadas).
stmt = "TRUNCATE " + ", ".join(DATA_TABLES) + " RESTART IDENTITY CASCADE"
cur.execute(stmt)
conn.commit()

print("\nListo. Tablas vaciadas:", ", ".join(DATA_TABLES))
print("Conservadas: puertos" + ("" if WIPE_USERS else ", users"))
print("El esquema (tablas/columnas/trigger) queda intacto.")
cur.close()
conn.close()
