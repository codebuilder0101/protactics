"""
Restaura los datos de UN período concreto desde un respaldo JSON.

Pensado para el caso de "se vació la base y hay que devolver solo un mes".
Escribe directamente contra la base, sin pasar por la aplicación, así que los
motores no se ejecutan y no se generan alertas nuevas.

QUÉ RESTAURA
    archivos_cargados, escaneos_diarios, escaneos_horarios, operadores,
    escaneo_filas y su indice_identificadores.

QUÉ NO RESTAURA, a propósito
    disponibilidad   Es un dato de gestión que informa el administrador a mano.
                     Los valores del respaldo son los que generaba el código
                     viejo de forma automática; devolverlos reintroduce el
                     problema que se acaba de eliminar.
    alertas          Derivadas de esa disponibilidad falsa y hoy ocultas.
    infracciones     Igual que las alertas.

PUNTO CRÍTICO
    Un TRUNCATE con RESTART IDENTITY deja las secuencias en 1. Como aquí se
    reinsertan filas con su identificador original, que llega a valores altos,
    hay que reajustar las secuencias al terminar. Si no, la primera carga que
    haga un usuario falla por identificador duplicado. Se hace siempre y se
    verifica antes de confirmar.

USO
    railway run --service Postgres -- python scripts/restaurar_respaldo.py RESPALDO YEAR MES [--yes]

    Sin --yes solo simula.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import psycopg2
from psycopg2.extras import Json, execute_values

if len(sys.argv) < 4:
    sys.exit(__doc__)

RESPALDO = sys.argv[1]
YEAR = int(sys.argv[2])
MES = int(sys.argv[3])
CONFIRM = "--yes" in sys.argv

# Orden de inserción: los padres antes que los hijos.
TABLAS = ["archivos_cargados", "escaneos_diarios", "escaneos_horarios",
          "operadores", "escaneo_filas", "indice_identificadores"]
EXCLUIDAS = ["disponibilidad", "alertas", "infracciones"]
COLUMNAS_JSON = {"escaneo_filas": ["datos"]}
# Hijos primero para el borrado previo de idempotencia.
ORDEN_BORRADO = ["escaneo_filas", "operadores", "escaneos_horarios",
                 "escaneos_diarios", "archivos_cargados"]

url = (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or "").strip()
if not url:
    sys.exit("No hay cadena de conexion.")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
os.environ["DATABASE_URL"] = url          # para el modulo de auditoria

with io.open(RESPALDO, encoding="utf-8") as fh:
    bk = json.load(fh)


def del_periodo(tabla):
    return [r for r in bk.get(tabla, [])
            if r.get("year") == YEAR and r.get("mes") == MES]


sel = {t: del_periodo(t) for t in TABLAS if t != "indice_identificadores"}
ids_filas = {r["id"] for r in sel["escaneo_filas"]}
# El indice no tiene year ni mes: cuelga de escaneo_filas por fila_id.
sel["indice_identificadores"] = [r for r in bk.get("indice_identificadores", [])
                                 if r["fila_id"] in ids_filas]

conn = psycopg2.connect(url)
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT current_database(), current_user")
bd, usuario = cur.fetchone()
print("Base de datos : %s" % bd)
print("Usuario       : %s" % usuario)
print("Periodo       : %d/%02d" % (YEAR, MES))
print("Respaldo      : %s" % os.path.basename(RESPALDO))
print()

print("SE RESTAURA:")
for t in TABLAS:
    print("  %-26s %7d" % (t, len(sel[t])))
print()
print("NO SE RESTAURA, a proposito:")
for t in EXCLUIDAS:
    print("  %-26s %7d   se omite" % (t, len(del_periodo(t))))
print()

if not CONFIRM:
    print("SIMULACION. No se escribio nada. Anade --yes para ejecutar.")
    cur.close()
    conn.close()
    sys.exit(0)

try:
    # Idempotencia: se limpia el periodo antes de insertarlo, hijos primero.
    cur.execute("DELETE FROM indice_identificadores WHERE fila_id IN "
                "(SELECT id FROM escaneo_filas WHERE year=%s AND mes=%s)",
                (YEAR, MES))
    borrados = {"indice_identificadores": cur.rowcount}
    for t in ORDEN_BORRADO:
        cur.execute("DELETE FROM %s WHERE year=%%s AND mes=%%s" % t, (YEAR, MES))
        borrados[t] = cur.rowcount
    if any(borrados.values()):
        print("Se limpiaron filas previas del periodo antes de insertar:")
        for t, n in borrados.items():
            if n:
                print("  %-26s %7d" % (t, n))
        print()

    # Insercion conservando el identificador original.
    for t in TABLAS:
        filas = sel[t]
        if not filas:
            continue
        cols = list(filas[0].keys())
        jscols = COLUMNAS_JSON.get(t, [])
        valores = [tuple(Json(r[c]) if c in jscols and r[c] is not None else r[c]
                         for c in cols)
                   for r in filas]
        lista = ", ".join('"%s"' % c for c in cols)
        execute_values(cur, "INSERT INTO %s (%s) VALUES %%s" % (t, lista),
                       valores, page_size=500)
        print("  insertadas en %-26s %7d" % (t, len(valores)))

    # Reajuste de TODAS las secuencias, no solo las tocadas.
    print()
    print("Reajuste de secuencias:")
    from models import Base
    for tabla in [x.name for x in Base.metadata.sorted_tables]:
        cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (tabla,))
        fila = cur.fetchone()
        seq = fila[0] if fila else None
        if not seq:
            continue
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM %s" % tabla)
        maximo = cur.fetchone()[0]
        if maximo > 0:
            cur.execute("SELECT setval(%s, %s, true)", (seq, maximo))
            print("  %-26s siguiente id = %d" % (tabla, maximo + 1))

    # Verificacion dentro de la transaccion.
    problemas = []
    for t in TABLAS:
        if t == "indice_identificadores":
            cur.execute("SELECT count(*) FROM indice_identificadores i "
                        "JOIN escaneo_filas f ON f.id=i.fila_id "
                        "WHERE f.year=%s AND f.mes=%s", (YEAR, MES))
        else:
            cur.execute("SELECT count(*) FROM %s WHERE year=%%s AND mes=%%s" % t,
                        (YEAR, MES))
        n = cur.fetchone()[0]
        if n != len(sel[t]):
            problemas.append("%s: esperado %d, hay %d" % (t, len(sel[t]), n))

    cur.execute("SELECT count(*) FROM indice_identificadores i "
                "LEFT JOIN escaneo_filas f ON f.id=i.fila_id WHERE f.id IS NULL")
    huerfanos = cur.fetchone()[0]
    if huerfanos:
        problemas.append("identificadores huerfanos: %d" % huerfanos)

    if problemas:
        conn.rollback()
        cur.close()
        conn.close()
        sys.exit("Verificacion fallida, se revirtio todo:\n  " + "\n  ".join(problemas))

    conn.commit()
    print()
    print("RESTAURACION CONFIRMADA.")

except Exception as e:
    conn.rollback()
    cur.close()
    conn.close()
    sys.exit("Fallo y se revirtio por completo. No se escribio nada.\n%s" % e)

cur.close()
conn.close()

# Constancia en la pista de auditoria, con la cadena hash correcta.
try:
    from audit import record_audit
    record_audit(accion="restaurar_respaldo", entidad="datos",
                 entidad_id="%d/%02d" % (YEAR, MES),
                 actor_email="operacion@protactics",
                 detalle={"origen": os.path.basename(RESPALDO),
                          "restaurado": {t: len(sel[t]) for t in TABLAS},
                          "omitido": EXCLUIDAS})
    print("Registrado en la pista de auditoria.")
except Exception as e:
    print("Aviso: la restauracion quedo bien, pero no se pudo auditar: %s" % e)
