"""
PROTACTICS — Autenticación
─────────────────────────────────────────────────────────────
Sesiones del lado del servidor:
  • La contraseña se guarda únicamente como hash bcrypt (passlib).
  • Al iniciar sesión se crea una fila en `user_sessions` con un token
    aleatorio y opaco; ese token viaja en una cookie HttpOnly.
  • Cerrar sesión elimina la fila (revocación real del lado del servidor).
"""
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, Request
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserSession, Puerto
from audit import record_audit

# ── Configuración ──────────────────────────────────────────
COOKIE_NAME    = "protactics_session"
SESSION_DAYS   = 7
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() in ("1", "true", "yes")
# Registro público de cuentas. Deshabilitado por defecto (sitio privado).
REGISTRATION_ENABLED = os.getenv("REGISTRATION_ENABLED", "false").lower() in ("1", "true", "yes")
MIN_PASSWORD   = 8
MAX_PASSWORD   = 72          # límite de bytes de bcrypt
EMAIL_RE       = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ── Perfiles de acceso ─────────────────────────────────────
ROLE_ADMIN    = "admin"               # gestiona usuarios y permisos; acceso total
ROLE_GLOBAL   = "observador_global"   # ve todos los puertos, solo lectura
ROLE_OBSERVER = "observador"          # ve solo su puerto asignado, solo lectura
ROLE_FEEDER   = "alimentador"         # ve y sube XLS de su puerto asignado

ALL_ROLES        = {ROLE_ADMIN, ROLE_GLOBAL, ROLE_OBSERVER, ROLE_FEEDER}
SCOPED_ROLES     = {ROLE_OBSERVER, ROLE_FEEDER}   # perfiles atados a un puerto
# Roles que un usuario puede solicitar al registrarse (admin NO es elegible).
SELF_SIGNUP_ROLES = {ROLE_GLOBAL, ROLE_OBSERVER, ROLE_FEEDER}

# ── Estados de aprobación ──────────────────────────────────
STATUS_PENDING  = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def can_view_port(user: User, puerto_id: int) -> bool:
    if user.role in (ROLE_ADMIN, ROLE_GLOBAL):
        return True
    if user.role in SCOPED_ROLES:
        return user.puerto_id == puerto_id
    return False


def can_upload_port(user: User, puerto_id: int) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_FEEDER:
        return user.puerto_id == puerto_id
    return False


def allowed_port_ids(user: User):
    """IDs de puertos visibles. None significa 'todos'."""
    if user.role in (ROLE_ADMIN, ROLE_GLOBAL):
        return None
    return [user.puerto_id] if user.puerto_id is not None else []


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Esquemas ───────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: str
    password: str
    nombre: Optional[str] = None
    role: Optional[str] = None
    puerto_id: Optional[int] = None


class LoginIn(BaseModel):
    email: str
    password: str


# ── Helpers ────────────────────────────────────────────────
def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _user_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nombre": user.nombre,
        "role": user.role,
        "puerto_id": user.puerto_id,
        "puerto_nombre": user.puerto.nombre_corto if user.puerto else None,
        "status": user.status,
        "requested_role": user.requested_role,
        "requested_puerto_id": user.requested_puerto_id,
        "requested_puerto_nombre": user.requested_puerto.nombre_corto if user.requested_puerto else None,
    }


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
        path="/",
    )


def _create_session(db: Session, user: User, response: Response):
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    db.add(UserSession(token=token, user_id=user.id, expires_at=expires))
    user.last_login_at = datetime.utcnow()
    db.commit()
    _set_session_cookie(response, token)


def user_from_token(db: Session, token: Optional[str]) -> Optional[User]:
    """Resuelve un token de cookie a un usuario, o None si no es válido/expiró.

    No lanza excepciones — pensado para las rutas de página que necesitan
    decidir entre servir HTML o redirigir.
    """
    if not token:
        return None
    sess = db.query(UserSession).filter_by(token=token).first()
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        db.delete(sess)
        db.commit()
        return None
    return sess.user


def get_current_user(
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    """Dependencia para endpoints de API protegidos. Lanza 401 (JSON) si no hay sesión."""
    if not session_token:
        raise HTTPException(401, "No autenticado")
    sess = db.query(UserSession).filter_by(token=session_token).first()
    if not sess:
        raise HTTPException(401, "Sesión inválida")
    if sess.expires_at < datetime.utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(401, "Sesión expirada")
    # Defensa: si la cuenta dejó de estar aprobada (suspendida), invalida la sesión.
    if sess.user.status != STATUS_APPROVED:
        db.delete(sess)
        db.commit()
        raise HTTPException(401, "Cuenta no autorizada")
    sess.last_seen_at = datetime.utcnow()
    db.commit()
    return sess.user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependencia para endpoints solo de administrador."""
    if user.role != ROLE_ADMIN:
        raise HTTPException(403, "Se requiere perfil de administrador")
    return user


# ── Endpoints ──────────────────────────────────────────────
@router.post("/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    if not REGISTRATION_ENABLED:
        raise HTTPException(403, "El registro de cuentas está deshabilitado")
    email = _normalize_email(body.email)
    password = body.password or ""

    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Correo electrónico inválido")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres")
    if len(password.encode("utf-8")) > MAX_PASSWORD:
        raise HTTPException(422, f"La contraseña no puede superar {MAX_PASSWORD} caracteres")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "Ese correo ya está registrado")

    nombre = (body.nombre or "").strip() or email.split("@")[0]

    # Arranque: el primer usuario del sistema es el administrador y queda
    # aprobado e iniciado sesión de inmediato (no hay nadie que lo apruebe).
    if db.query(User).count() == 0:
        user = User(email=email, nombre=nombre, role=ROLE_ADMIN,
                    status=STATUS_APPROVED, password_hash=pwd_context.hash(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        _create_session(db, user, response)
        return _user_public(user)

    # Resto de usuarios: eligen su perfil (admin NO es elegible) y quedan
    # PENDIENTES de aprobación. No se crea sesión.
    role = body.role
    if role not in SELF_SIGNUP_ROLES:
        raise HTTPException(422, "Selecciona un perfil válido")

    requested_port = None
    if role in SCOPED_ROLES:
        if body.puerto_id is None:
            raise HTTPException(422, "Selecciona el puerto que necesitas")
        if not db.query(Puerto).filter_by(id=body.puerto_id).first():
            raise HTTPException(422, "El puerto seleccionado no existe")
        requested_port = body.puerto_id

    user = User(
        email=email, nombre=nombre,
        role=role,                       # provisional, el admin lo confirma al aprobar
        puerto_id=None,                  # se asigna al aprobar
        status=STATUS_PENDING,
        requested_role=role,
        requested_puerto_id=requested_port,
        password_hash=pwd_context.hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # Sin sesión: la cuenta debe ser aprobada antes de poder ingresar.
    return _user_public(user)


@router.post("/login")
def login(body: LoginIn, response: Response, request: Request,
          db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    user = db.query(User).filter_by(email=email).first()
    # Mensaje genérico — no revela si el correo existe (anti-enumeración).
    if not user or not pwd_context.verify(body.password or "", user.password_hash):
        record_audit(accion="login_failure", entidad="auth", entidad_id=email,
                     actor_email=email, request=request,
                     detalle={"motivo": "credenciales inválidas"})
        raise HTTPException(401, "Credenciales inválidas")
    # Puerta de aprobación (solo se revela tras contraseña correcta).
    if user.status == STATUS_PENDING:
        record_audit(accion="login_denied", entidad="auth", entidad_id=user.id,
                     actor=user, request=request, detalle={"motivo": "pendiente"})
        raise HTTPException(403, "Tu cuenta está pendiente de aprobación por un administrador")
    if user.status == STATUS_REJECTED:
        record_audit(accion="login_denied", entidad="auth", entidad_id=user.id,
                     actor=user, request=request, detalle={"motivo": "rechazada"})
        raise HTTPException(403, "Tu solicitud de acceso fue rechazada")
    _create_session(db, user, response)
    record_audit(accion="login_success", entidad="auth", entidad_id=user.id,
                 actor=user, request=request)
    return _user_public(user)


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
):
    if session_token:
        db.query(UserSession).filter_by(token=session_token).delete()
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_public(user)


# ── Usuarios de demostración (uno por perfil, ya aprobados) ─
# Pensados para pruebas. El sembrado es idempotente (no duplica) y se puede
# desactivar con SEED_DEMO_USERS=false. ⚠ Cambia/elimina estas cuentas antes
# de producción: usan contraseñas conocidas.
DEMO_USERS = [
    dict(email="admin@protactics.co",       password="admin1234",
         nombre="Administrador General",      role=ROLE_ADMIN,    puerto_id=None),
    dict(email="global@protactics.co",       password="global1234",
         nombre="Observador Global",          role=ROLE_GLOBAL,   puerto_id=None),
    dict(email="observador@protactics.co",   password="observador1234",
         nombre="Observador TCBUEN",          role=ROLE_OBSERVER, puerto_id=2),   # TCBUEN
    dict(email="alimentador@protactics.co",  password="alimentador1234",
         nombre="Alimentador Buenaventura",   role=ROLE_FEEDER,   puerto_id=0),   # SPR Buenaventura
]


def seed_demo_users(db: Session) -> list[str]:
    """Crea las cuentas de demostración si no existen. Devuelve las creadas."""
    created = []
    for u in DEMO_USERS:
        if db.query(User).filter_by(email=u["email"]).first():
            continue
        db.add(User(
            email=u["email"], nombre=u["nombre"], role=u["role"],
            puerto_id=u["puerto_id"], status=STATUS_APPROVED,
            approved_at=datetime.utcnow(),
            password_hash=pwd_context.hash(u["password"]),
        ))
        created.append(u["email"])
    if created:
        db.commit()
    return created


# ── Gestión de usuarios (solo admin) ───────────────────────
class UserCreate(BaseModel):
    email: str
    password: str
    nombre: Optional[str] = None
    role: str
    puerto_id: Optional[int] = None


class UserUpdate(BaseModel):
    role: Optional[str] = None
    puerto_id: Optional[int] = None
    nombre: Optional[str] = None
    password: Optional[str] = None     # opcional: restablecer contraseña


def _validate_role_port(db: Session, role: str, puerto_id: Optional[int]):
    if role not in ALL_ROLES:
        raise HTTPException(422, "Perfil inválido")
    if role in SCOPED_ROLES:
        if puerto_id is None:
            raise HTTPException(422, "Este perfil requiere un puerto asignado")
        if not db.query(Puerto).filter_by(id=puerto_id).first():
            raise HTTPException(422, "El puerto asignado no existe")
        return puerto_id
    # admin / observador_global no llevan puerto
    return None


@router.get("/users")
def list_users(status: Optional[str] = None, db: Session = Depends(get_db),
               _admin: User = Depends(require_admin)):
    q = db.query(User).order_by(User.id)
    if status:
        q = q.filter(User.status == status)
    return [_user_public(u) for u in q.all()]


@router.post("/users")
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                _admin: User = Depends(require_admin)):
    email = _normalize_email(body.email)
    password = body.password or ""
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Correo electrónico inválido")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres")
    if len(password.encode("utf-8")) > MAX_PASSWORD:
        raise HTTPException(422, f"La contraseña no puede superar {MAX_PASSWORD} caracteres")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "Ese correo ya está registrado")

    puerto_id = _validate_role_port(db, body.role, body.puerto_id)
    nombre = (body.nombre or "").strip() or email.split("@")[0]
    # Creado por un administrador → aprobado directamente.
    user = User(email=email, nombre=nombre, role=body.role, puerto_id=puerto_id,
                status=STATUS_APPROVED, approved_at=datetime.utcnow(),
                password_hash=pwd_context.hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit(accion="create_user", entidad="users", entidad_id=user.id,
                 actor=_admin, request=request,
                 detalle={"email": user.email, "role": user.role,
                          "puerto_id": user.puerto_id})
    return _user_public(user)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserUpdate, request: Request,
                db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    old_role, old_port = user.role, user.puerto_id
    new_role = body.role if body.role is not None else user.role
    # Un puerto explícito en el body manda; si no, se conserva el actual.
    new_port = body.puerto_id if body.puerto_id is not None else user.puerto_id
    new_port = _validate_role_port(db, new_role, new_port)

    # Salvaguardas: no dejar el sistema sin administrador.
    if user.id == admin.id and new_role != ROLE_ADMIN:
        raise HTTPException(400, "No puedes quitarte a ti mismo el perfil de administrador")
    if user.role == ROLE_ADMIN and new_role != ROLE_ADMIN:
        admins = db.query(User).filter_by(role=ROLE_ADMIN).count()
        if admins <= 1:
            raise HTTPException(400, "Debe quedar al menos un administrador")

    user.role = new_role
    user.puerto_id = new_port
    if body.nombre is not None:
        user.nombre = body.nombre.strip() or user.nombre
    if body.password:
        if len(body.password) < MIN_PASSWORD:
            raise HTTPException(422, f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres")
        if len(body.password.encode("utf-8")) > MAX_PASSWORD:
            raise HTTPException(422, f"La contraseña no puede superar {MAX_PASSWORD} caracteres")
        user.password_hash = pwd_context.hash(body.password)
        # Al cambiar la contraseña se cierran las sesiones abiertas del usuario.
        db.query(UserSession).filter_by(user_id=user.id).delete()

    db.commit()
    db.refresh(user)
    record_audit(accion="update_user", entidad="users", entidad_id=user.id,
                 actor=admin, request=request,
                 detalle={"role": {"antes": old_role, "despues": user.role},
                          "puerto_id": {"antes": old_port, "despues": user.puerto_id},
                          "password_cambiada": bool(body.password)})
    return _user_public(user)


class ApproveIn(BaseModel):
    role: Optional[str] = None
    puerto_id: Optional[int] = None


@router.post("/users/{uid}/approve")
def approve_user(uid: int, body: ApproveIn, request: Request,
                 db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    old_status = user.status
    # Rol final: el que confirme el admin, o el solicitado por el usuario.
    role = body.role or user.requested_role or user.role
    # El puerto enviado manda; si no, el solicitado en el registro.
    port = body.puerto_id if body.puerto_id is not None else user.requested_puerto_id
    port = _validate_role_port(db, role, port)   # 422 si perfil con alcance sin puerto

    user.role = role
    user.puerto_id = port
    user.status = STATUS_APPROVED
    user.approved_by = admin.id
    user.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    record_audit(accion="approve_user", entidad="users", entidad_id=user.id,
                 actor=admin, request=request,
                 detalle={"status": {"antes": old_status, "despues": user.status},
                          "role": user.role, "puerto_id": user.puerto_id,
                          "approved_by": admin.id})
    return _user_public(user)


@router.post("/users/{uid}/reject")
def reject_user(uid: int, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    if user.id == admin.id:
        raise HTTPException(400, "No puedes rechazar tu propia cuenta")
    if user.role == ROLE_ADMIN and user.status == STATUS_APPROVED:
        admins = db.query(User).filter_by(role=ROLE_ADMIN, status=STATUS_APPROVED).count()
        if admins <= 1:
            raise HTTPException(400, "Debe quedar al menos un administrador")

    old_status = user.status
    user.status = STATUS_REJECTED
    # Suspender corta cualquier sesión abierta del usuario.
    db.query(UserSession).filter_by(user_id=user.id).delete()
    db.commit()
    db.refresh(user)
    record_audit(accion="reject_user", entidad="users", entidad_id=user.id,
                 actor=admin, request=request,
                 detalle={"status": {"antes": old_status, "despues": user.status}})
    return _user_public(user)


@router.delete("/users/{uid}")
def delete_user(uid: int, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    if user.id == admin.id:
        raise HTTPException(400, "No puedes eliminar tu propia cuenta")
    if user.role == ROLE_ADMIN:
        admins = db.query(User).filter_by(role=ROLE_ADMIN).count()
        if admins <= 1:
            raise HTTPException(400, "Debe quedar al menos un administrador")
    deleted = {"email": user.email, "role": user.role, "puerto_id": user.puerto_id}
    db.delete(user)
    db.commit()
    record_audit(accion="delete_user", entidad="users", entidad_id=uid,
                 actor=admin, request=request, detalle=deleted)
    return {"ok": True}
