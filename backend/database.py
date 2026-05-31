import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Puerto

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./protactics.db")

# Railway PostgreSQL uses postgres:// — SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for p in PUERTOS_SEED:
            if not db.query(Puerto).filter_by(id=p["id"]).first():
                db.add(Puerto(**p))
        db.commit()
    finally:
        db.close()
