"""
Verifica, en SOLO LECTURA, que la base de datos de Railway tiene los permisos y
objetos necesarios para la auditoría inmutable (Semana 1).

No modifica nada: solo consulta privilegios y comprueba si el trigger/función y
las tablas nuevas existen.

USO (la credencial nunca sale de tu máquina):
    cd backend
    railway login          # autentícate en TU cuenta (una vez)
    railway link           # elige el proyecto/servicio de la app
    railway run .venv/Scripts/python.exe scripts/check_db_privileges.py

`railway run` inyecta DATABASE_URL del servicio enlazado en el entorno del
comando, así que el script lo lee de ahí automáticamente.
"""
import os
import sys

try:
    import psycopg2
except ImportError:
    sys.exit("Falta psycopg2. Instala las deps del backend: pip install -r requirements.txt")

# Prefiere la URL pública (proxy TCP) para poder conectar desde fuera de Railway;
# si no, la interna (solo resuelve dentro de la red de Railway).
url = (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or "").strip()
if not url:
    sys.exit("DATABASE_URL no está definida.\n"
             "Ejecútalo con la CLI de Railway:  railway run python scripts/check_db_privileges.py")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()


def one(sql):
    cur.execute(sql)
    return cur.fetchone()


print("── Conexión a Railway Postgres ──────────────────────")
print("usuario actual        :", one("SELECT current_user")[0])
print("base de datos         :", one("SELECT current_database()")[0])
print("es superusuario       :", one("SELECT usesuper FROM pg_user WHERE usename = current_user")[0])

print("\n── Permisos para crear el trigger de auditoría ──────")
can_schema = one("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")[0]
print("CREATE en schema public:", can_schema)
print("USAGE en lenguaje plpgsql:",
      one("SELECT has_language_privilege(current_user, 'plpgsql', 'USAGE')")[0])

print("\n── Estado de los objetos de Semana 1 ────────────────")
cur.execute("""SELECT table_name FROM information_schema.tables
               WHERE table_schema='public'
                 AND table_name IN ('alertas','sla','infracciones','auditoria')
               ORDER BY table_name""")
tablas = [r[0] for r in cur.fetchall()]
print("tablas nuevas presentes :", tablas or "(ninguna — la app aún no ha arrancado contra esta BD)")

func = one("SELECT 1 FROM pg_proc WHERE proname='protactics_audit_immutable'")
print("función inmutabilidad   :", "INSTALADA" if func else "ausente")
trig = one("SELECT 1 FROM pg_trigger WHERE tgname='trg_audit_immutable'")
print("trigger inmutabilidad   :", "INSTALADO" if trig else "ausente")

# ¿El usuario podrá adjuntar el trigger? (es dueño de la tabla o tiene TRIGGER)
if "auditoria" in tablas:
    owns = one("""SELECT pg_get_userbyid(relowner)=current_user
                  FROM pg_class WHERE relname='auditoria'""")[0]
    has_trig = one("SELECT has_table_privilege(current_user, 'auditoria', 'TRIGGER')")[0]
    print("dueño de 'auditoria'    :", owns)
    print("privilegio TRIGGER      :", has_trig)

print("\n── Veredicto ────────────────────────────────────────")
ok = bool(can_schema) and (("auditoria" not in tablas) or
                           one("SELECT pg_get_userbyid(relowner)=current_user OR "
                               "has_table_privilege(current_user,'auditoria','TRIGGER') "
                               "FROM pg_class WHERE relname='auditoria'")[0])
if ok:
    print("OK: el usuario puede crear la función y el trigger. No hay que ajustar permisos.")
else:
    print("ATENCIÓN: faltan permisos. Como usuario dueño/superusuario, ejecuta:")
    print("  GRANT CREATE ON SCHEMA public TO current_user;")
    print("  ALTER TABLE auditoria OWNER TO <usuario_app>;   -- o: GRANT TRIGGER ON auditoria TO <usuario_app>;")

cur.close()
conn.close()
