from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Puerto(Base):
    __tablename__ = "puertos"
    id          = Column(Integer, primary_key=True)
    nombre      = Column(String, nullable=False)
    nombre_corto= Column(String, nullable=False)
    departamento= Column(String, nullable=False)
    lat         = Column(Float, nullable=False)
    lng         = Column(Float, nullable=False)
    icono       = Column(String, default="⚓")
    sx          = Column(Float)   # SVG pin X
    sy          = Column(Float)   # SVG pin Y
    formato     = Column(String, default="standard")  # standard|rapiscan|tcbuen

    escaneos    = relationship("EscaneosDiarios", back_populates="puerto", cascade="all, delete-orphan")
    disponibilidad = relationship("Disponibilidad", back_populates="puerto", cascade="all, delete-orphan")


class EscaneosDiarios(Base):
    __tablename__ = "escaneos_diarios"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    year        = Column(Integer, nullable=False)
    mes         = Column(Integer, nullable=False)   # 1-12
    dia         = Column(Integer, nullable=False)   # 1-31
    total       = Column(Integer, default=0)
    puerto      = relationship("Puerto", back_populates="escaneos")
    __table_args__ = (UniqueConstraint("puerto_id","year","mes","dia"),)


class EscaneosHorarios(Base):
    __tablename__ = "escaneos_horarios"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    year        = Column(Integer, nullable=False)
    mes         = Column(Integer, nullable=False)
    hora        = Column(Integer, nullable=False)   # 0-23
    total       = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("puerto_id","year","mes","hora"),)


class Operadores(Base):
    __tablename__ = "operadores"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    year        = Column(Integer, nullable=False)
    mes         = Column(Integer, nullable=False)
    nombre      = Column(String, nullable=False)
    total       = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("puerto_id","year","mes","nombre"),)


class Disponibilidad(Base):
    __tablename__ = "disponibilidad"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    year        = Column(Integer, nullable=False)
    mes         = Column(Integer, nullable=False)
    valor       = Column(Float, nullable=True)      # 0.0 - 100.0
    actualizado = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    puerto      = relationship("Puerto", back_populates="disponibilidad")
    __table_args__ = (UniqueConstraint("puerto_id","year","mes"),)


class ArchivosCargados(Base):
    __tablename__ = "archivos_cargados"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    year        = Column(Integer, nullable=False)
    mes         = Column(Integer, nullable=False)
    nombre_archivo = Column(String)
    formato     = Column(String)
    total_escaneos = Column(Integer)
    cargado_en  = Column(DateTime, default=datetime.utcnow)


# ── AUTENTICACIÓN ──────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    email         = Column(String, nullable=False, unique=True, index=True)
    nombre        = Column(String)                       # nombre para mostrar
    password_hash = Column(String, nullable=False)       # bcrypt — nunca texto plano
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

    sessions = relationship("UserSession", back_populates="user",
                            cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    token        = Column(String, nullable=False, unique=True, index=True)  # opaco, aleatorio
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)
    expires_at   = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
