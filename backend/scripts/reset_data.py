"""
Vacía los DATOS de la base conservando el ESQUEMA y los datos maestros.

QUÉ CONSERVA SIEMPRE
    puertos   Los 7 puertos. Son datos maestros: media base los referencia por
              clave foránea y sin ellos el sistema no arranca.
    users     Las cuentas y sus contraseñas.

QUÉ BORRA
    Todas las demás tablas de datos. La lista NO está escrita a mano: se deriva
    de los modelos en tiempo de ejecución, de modo que una tabla nueva queda
    cubierta automáticamente. Una versión anterior de este script tenía la lista
    fija y se quedó corta en 4 tablas, dejando el índice de contenedores vivo.

NOTAS
    · auditoria se vacía con TRUNCATE. El trigger de inmutabilidad bloquea
      DELETE y UPDATE pero no se dispara con TRUNCATE. Tras el reinicio la
      cadena hash vuelve a empezar desde cero, lo cual es correcto.
    · user_sessions se conserva por defecto para no cerrar la sesión de quien
      esté trabajando. Con --wipe-sessions se vacía también.
    · Es una acción DESTRUCTIVA e irreversible. Sin --yes solo simula.

USO
    Con la CLI de Railway autenticada:
        railway run --service Postgres python scripts/reset_data.py
        railway run --service Postgres python scripts/reset_data.py --yes

    O con la cadena de conexión en el entorno:
        DATABASE_PUBLIC_URL="postgresql://..." python scripts/reset_data.py --yes

OPCIONES
    --yes             Ejecuta de verdad. Sin esto solo muestra qué haría.
    --wipe-sessions   Vacía además user_sessions, cerrando todas las sesiones.
    --wipe-users      Vacía además users y user_sessions. Deja el sistema sin
                      ninguna cuenta: habrá que registrar el primer admin.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    import psycopg2
except ImportError:
    sys.exit("Falta psycopg2. Instala las dependencias: pip install -r requirements.txt")

from models import Base

CONFIRM       = ("--yes" in sys.argv) or os.getenv("CONFIRM_RESET") == "YES"
WIPE_USERS    = "--wipe-users" in sys.argv
WIPE_SESSIONS = "--wipe-sessions" in sys.argv

# Datos maestros que nunca se tocan.
CONSERVAR = {"puertos", "users", "user_sessions"}
if WIPE_USERS:
    CONSERVAR -= {"users", "user_sessions"}
elif WIPE_SESSIONS:
    CONSERVAR -= {"user_sessions"}

# La lista sale de los modelos, no de una constante que se desactualiza.
TODAS = [t.name for t in Base.metadata.sorted_tables]
BORRAR = [t for t in TODAS if t not in CONSERVAR]

url = (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or "").strip()
if not url:
    sys.exit("No hay cadena de conexión.\n"
             "Ejecuta con:  railway run --service Postgres python scripts/reset_data.py")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

conn = psycopg2.connect(url)
conn.autocommit = False
cur = conn.cursor()

# Aviso de a qué base estamos apuntando, para no equivocarse de entorno.
cur.execute("SELECT current_database(), inet_server_addr()::text, current_user")
bd, host, usuario = cur.fetchone()
print(f"Base de datos : {bd}")
print(f"Servidor      : {host or 'local'}")
print(f"Usuario       : {usuario}")
print()

# Comprobación de que el esquema es el esperado antes de tocar nada.
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
existentes = {r[0] for r in cur.fetchall()}
faltan = [t for t in TODAS if t not in existentes]
if faltan:
    sys.exit(f"El esquema no coincide con los modelos. Faltan tablas: {faltan}\n"
             "No se toca nada. Revisa que apuntas a la base correcta.")

sobran = sorted(existentes - set(TODAS) - {"alembic_version"})
if sobran:
    print(f"Aviso: hay tablas en la base que no están en los modelos y NO se tocarán: {sobran}")
    print()

def contar(tablas):
    out = {}
    for t in tablas:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        out[t] = cur.fetchone()[0]
    return out

antes_borrar   = contar(BORRAR)
antes_conservar = contar(sorted(CONSERVAR))

print("SE VACÍAN:")
for t in BORRAR:
    print(f"  {t:26} {antes_borrar[t]:>10}")
print()
print("SE CONSERVAN:")
for t in sorted(CONSERVAR):
    print(f"  {t:26} {antes_conservar[t]:>10}")
print()

if not CONFIRM:
    print("SIMULACIÓN. No se borró nada. Añade --yes para ejecutar de verdad.")
    cur.close(); conn.close()
    sys.exit(0)

stmt = "TRUNCATE " + ", ".join(f'"{t}"' for t in BORRAR) + " RESTART IDENTITY CASCADE"
try:
    cur.execute(stmt)
except Exception as e:
    conn.rollback()
    cur.close(); conn.close()
    sys.exit(f"El borrado falló y se revirtió por completo. No se perdió nada.\n{e}")

# Verificación dentro de la misma transacción: si algo no quedó en cero, se revierte.
restantes = {t: n for t, n in contar(BORRAR).items() if n}
conservadas_ok = contar(sorted(CONSERVAR))
perdidas = {t: (antes_conservar[t], conservadas_ok[t])
            for t in CONSERVAR if conservadas_ok[t] != antes_conservar[t]}

if restantes or perdidas:
    conn.rollback()
    cur.close(); conn.close()
    sys.exit(f"Resultado inesperado, se revirtió todo.\n"
             f"  sin vaciar: {restantes}\n  alteradas por cascada: {perdidas}")

conn.commit()

print("LISTO. Tablas vaciadas:", len(BORRAR))
print("Conservado intacto:")
for t in sorted(CONSERVAR):
    print(f"  {t:26} {conservadas_ok[t]:>10}")
print()
print("El esquema, los índices y el trigger de auditoría quedan intactos.")
print("La cadena de auditoría vuelve a empezar desde cero en la próxima acción.")

cur.close()
conn.close()
