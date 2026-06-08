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

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserSession

# ── Configuración ──────────────────────────────────────────
COOKIE_NAME    = "protactics_session"
SESSION_DAYS   = 7
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() in ("1", "true", "yes")
MIN_PASSWORD   = 8
MAX_PASSWORD   = 72          # límite de bytes de bcrypt
EMAIL_RE       = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Esquemas ───────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: str
    password: str
    nombre: Optional[str] = None


class LoginIn(BaseModel):
    email: str
    password: str


# ── Helpers ────────────────────────────────────────────────
def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _user_public(user: User) -> dict:
    return {"id": user.id, "email": user.email, "nombre": user.nombre}


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
    sess.last_seen_at = datetime.utcnow()
    db.commit()
    return sess.user


# ── Endpoints ──────────────────────────────────────────────
@router.post("/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
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
    user = User(email=email, nombre=nombre, password_hash=pwd_context.hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    _create_session(db, user, response)
    return _user_public(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    user = db.query(User).filter_by(email=email).first()
    # Mensaje genérico — no revela si el correo existe (anti-enumeración).
    if not user or not pwd_context.verify(body.password or "", user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    _create_session(db, user, response)
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
