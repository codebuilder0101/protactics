from sqlalchemy import (Column, Integer, Float, String, DateTime, ForeignKey,
                        UniqueConstraint, Boolean, Text, CheckConstraint, Index,
                        JSON, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

# JSON portable: JSONB en PostgreSQL (producción), JSON en SQLite (dev/test).
JSONType = JSON().with_variant(JSONB, "postgresql")

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
    dia         = Column(Integer, nullable=False, default=0)   # 1-31 (por día para acumular)
    hora        = Column(Integer, nullable=False)   # 0-23
    total       = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("puerto_id","year","mes","dia","hora"),)


class Operadores(Base):
    __tablename__ = "operadores"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    year        = Column(Integer, nullable=False)
    mes         = Column(Integer, nullable=False)
    dia         = Column(Integer, nullable=False, default=0)   # 1-31 (por día para acumular)
    nombre      = Column(String, nullable=False)
    total       = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("puerto_id","year","mes","dia","nombre"),)


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
    # Perfil de acceso: admin | observador_global | observador | alimentador
    role          = Column(String, nullable=False, default="observador")
    # Puerto asignado para perfiles con alcance (observador / alimentador).
    # NULL para admin / observador_global, o para cuentas aún sin configurar.
    puerto_id     = Column(Integer, ForeignKey("puertos.id"), nullable=True)
    # Aprobación: pending | approved | rejected
    status        = Column(String, nullable=False, default="pending")
    # Lo que el usuario pidió al registrarse (contexto para el administrador).
    requested_role       = Column(String)
    requested_puerto_id  = Column(Integer, ForeignKey("puertos.id"), nullable=True)
    approved_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at   = Column(DateTime)
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)

    puerto           = relationship("Puerto", foreign_keys=[puerto_id])
    requested_puerto = relationship("Puerto", foreign_keys=[requested_puerto_id])
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


# ══════════════════════════════════════════════════════════════
#  SEMANA 1 — Alertas, SLA, Infracciones y Auditoría
# ══════════════════════════════════════════════════════════════

class Alerta(Base):
    """Alerta operativa de un puerto (incumplimiento de SLA, falta de carga, etc.).

    El ciclo de vida es open → acknowledged → resolved. El generador de alertas
    (lógica de semanas posteriores) escribe aquí; en Semana 1 solo se define el
    esquema. Ver [[infracciones]] para el detalle numérico que origina la alerta.
    """
    __tablename__ = "alertas"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id   = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    tipo        = Column(String, nullable=False)   # sla_breach|no_upload|availability_low
    severidad   = Column(String, nullable=False, default="warning")  # info|warning|critical
    mensaje     = Column(Text, nullable=False)
    estado      = Column(String, nullable=False, default="open")     # open|acknowledged|resolved
    payload     = Column(JSONType)                 # datos de contexto (libre)
    creada_en   = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    resuelta_en = Column(DateTime(timezone=True))
    resuelta_por= Column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        CheckConstraint("tipo in ('sla_breach','no_upload','availability_low')",
                        name="ck_alertas_tipo"),
        CheckConstraint("severidad in ('info','warning','critical')",
                        name="ck_alertas_severidad"),
        CheckConstraint("estado in ('open','acknowledged','resolved')",
                        name="ck_alertas_estado"),
        # Índice parcial en Postgres (solo alertas abiertas); índice normal en SQLite.
        Index("ix_alertas_open", "puerto_id",
              postgresql_where=text("estado = 'open'")),
    )


class SLA(Base):
    """Umbral de servicio. puerto_id NULL = valor por defecto global."""
    __tablename__ = "sla"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id      = Column(Integer, ForeignKey("puertos.id"), nullable=True)
    metrica        = Column(String, nullable=False)  # availability|upload_deadline|min_daily_scans
    umbral         = Column(Float, nullable=False)
    periodo        = Column(String, nullable=False, default="mensual")  # mensual|diario
    activo         = Column(Boolean, nullable=False, default=True)
    actualizado_en = Column(DateTime(timezone=True), default=datetime.utcnow,
                            onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("puerto_id", "metrica", name="uq_sla_puerto_metrica"),
        CheckConstraint("metrica in ('availability','upload_deadline','min_daily_scans')",
                        name="ck_sla_metrica"),
        CheckConstraint("periodo in ('mensual','diario')", name="ck_sla_periodo"),
    )


class Infraccion(Base):
    """Registro de un valor observado que incumplió un [[sla]] en un período."""
    __tablename__ = "infracciones"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    puerto_id       = Column(Integer, ForeignKey("puertos.id"), nullable=False)
    sla_id          = Column(Integer, ForeignKey("sla.id"), nullable=False)
    year            = Column(Integer, nullable=False)
    mes             = Column(Integer, nullable=False)
    dia             = Column(Integer, nullable=True)    # NULL para infracciones mensuales
    valor_observado = Column(Float)
    valor_esperado  = Column(Float)
    detectada_en    = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    alerta_id       = Column(Integer, ForeignKey("alertas.id"), nullable=True)

    __table_args__ = (
        Index("ix_infracciones_periodo", "puerto_id", "year", "mes"),
    )


class AuditLog(Base):
    """Pista de auditoría INMUTABLE (append-only).

    No lleva claves foráneas a propósito: debe sobrevivir al borrado de usuarios
    o puertos sin romperse, y nunca debe bloquear la acción auditada. La identidad
    del actor se conserva desnormalizada (actor_email). La inmutabilidad se refuerza
    en la capa de aplicación (sin update/delete) y, en Postgres, con un trigger que
    rechaza UPDATE/DELETE. La cadena hash/prev_hash hace cualquier alteración
    posterior detectable.
    """
    __tablename__ = "auditoria"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    actor_user_id = Column(Integer)            # sin FK (login fallido = sin usuario)
    actor_email   = Column(String)             # snapshot denormalizado
    accion        = Column(String, nullable=False)   # login_success, upload, approve_user, ...
    entidad       = Column(String, nullable=False)   # tabla/recurso afectado
    entidad_id    = Column(String)             # string: admite claves compuestas
    puerto_id     = Column(Integer)            # sin FK (denormalizado)
    detalle       = Column(JSONType)           # antes/después, contexto
    ip            = Column(String)
    user_agent    = Column(String)
    creado_en     = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    hash          = Column(String, nullable=False)   # H(prev_hash + fila canónica)
    prev_hash     = Column(String)                   # hash de la fila anterior

    __table_args__ = (
        Index("ix_auditoria_creado", "creado_en"),
        Index("ix_auditoria_entidad", "entidad", "entidad_id"),
    )
