import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from models import Base, Puerto


def _resolve_database_url() -> str:
    """Resuelve la URL de la base de datos de forma robusta.

    - Variable AUSENTE  -> SQLite local (desarrollo).
    - Variable PRESENTE pero VACÍA (típico de una referencia mal configurada en
      Railway, p. ej. ${{Postgres.DATABASE_URL}} que no resuelve) -> se intenta
      reconstruir desde las variables individuales PG* (PGHOST, PGUSER, ...).
    - Si aún así no hay nada -> error claro y accionable (en vez del críptico
      "Could not parse SQLAlchemy URL from string ''").
    """
    raw = os.getenv("DATABASE_URL")
    if raw is None:
        url = "sqlite:///./protactics.db"          # desarrollo local
    else:
        url = raw.strip()

    if not url:
        # Reconstruir desde las variables que Railway/Heroku exponen para Postgres
        host = (os.getenv("PGHOST") or "").strip()
        if host:
            user = (os.getenv("PGUSER") or "postgres").strip()
            pw   = quote_plus((os.getenv("PGPASSWORD") or "").strip())
            port = (os.getenv("PGPORT") or "5432").strip()
            db   = (os.getenv("PGDATABASE") or "railway").strip()
            url = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    if not url:
        raise RuntimeError(
            "DATABASE_URL está definida pero vacía y no hay variables PG* para "
            "reconstruirla. En Railway, en el servicio de la app (no en el de la "
            "base), define la variable DATABASE_URL referenciando tu servicio "
            "PostgreSQL (p. ej. ${{Postgres.DATABASE_URL}}) o pega la cadena de "
            "conexión completa (postgresql://usuario:clave@host:puerto/base)."
        )

    # Railway/Heroku usan postgres:// — SQLAlchemy necesita postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _resolve_database_url()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

PUERTOS_SEED = [
    dict(id=0, nombre="Soc. Portuaria Regional de Buenaventura", nombre_corto="SPR Buenaventura",
         departamento="Valle del Cauca", lat=3.880, lng=-77.031, icono="⚓", sx=91.4, sy=309.0, formato="standard"),
    dict(id=1, nombre="Puerto Industrial de Aguadulce", nombre_corto="Aguadulce",
         departamento="Valle del Cauca", lat=3.848, lng=-77.118, icono="🏭", sx=83.0, sy=318.0, formato="rapiscan"),
    dict(id=2, nombre="Terminal de Contenedores de Buenaventura (TCBUEN)", nombre_corto="TCBUEN",
         departamento="Valle del Cauca", lat=3.856, lng=-77.075, icono="📦", sx=88.0, sy=323.0, formato="tcbuen"),
    dict(id=3, nombre="Puerto Antioquia — Escáner 1", nombre_corto="Pto. Antioquia E1",
         departamento="Antioquia", lat=7.823, lng=-76.628, icono="⚓", sx=104.0, sy=177.5, formato="standard"),
    dict(id=4, nombre="Puerto Antioquia — Escáner 2", nombre_corto="Pto. Antioquia E2",
         departamento="Antioquia", lat=7.823, lng=-76.628, icono="🔍", sx=116.0, sy=172.0, formato="standard"),
    dict(id=5, nombre="Soc. Portuaria de Barranquilla", nombre_corto="SPR Barranquilla",
         departamento="Atlántico", lat=10.968, lng=-74.781, icono="🚢", sx=174.8, sy=69.7, formato="standard"),
    dict(id=6, nombre="Puerto de Santa Marta", nombre_corto="Pto. Santa Marta",
         departamento="Magdalena", lat=11.241, lng=-74.199, icono="⛴", sx=196.3, sy=60.3, formato="standard"),
]

# Columnas añadidas a `users` después de su creación original. Si la tabla ya
# existía sin ellas (instalaciones previas), se agregan con ALTER TABLE para no
# perder datos. Las filas existentes quedan 'approved' para no bloquear cuentas.
_USER_COLUMNS = [
    ("role",                "VARCHAR DEFAULT 'observador'"),
    ("puerto_id",           "INTEGER"),
    ("status",              "VARCHAR DEFAULT 'approved'"),
    ("requested_role",      "VARCHAR"),
    ("requested_puerto_id", "INTEGER"),
    ("approved_by",         "INTEGER"),
    ("approved_at",         "TIMESTAMP"),
]


def _ensure_user_columns():
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    missing = [(n, ddl) for n, ddl in _USER_COLUMNS if n not in existing]
    if not missing:
        return
    with engine.begin() as conn:
        for name, ddl in missing:
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        # Cuentas previas al flujo de aprobación se consideran aprobadas.
        conn.execute(text("UPDATE users SET status='approved' WHERE status IS NULL"))


def init_db():
    _ensure_user_columns()              # migrar tablas preexistentes
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for p in PUERTOS_SEED:
            if not db.query(Puerto).filter_by(id=p["id"]).first():
                db.add(Puerto(**p))
        db.commit()
    finally:
        db.close()
