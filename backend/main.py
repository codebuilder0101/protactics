"""
PROTACTICS — Backend API
FastAPI + SQLAlchemy + PostgreSQL (SQLite para desarrollo local)
"""
import io
import os
import calendar
from datetime import datetime
from typing import Optional

import openpyxl
import xlrd
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, init_db, SessionLocal
from models import (Puerto, EscaneosDiarios, EscaneosHorarios,
                    Operadores, Disponibilidad, ArchivosCargados, User)
from parsers import parse_file
from auth import (router as auth_router, get_current_user,
                  user_from_token, COOKIE_NAME, can_view_port, can_upload_port,
                  allowed_port_ids, ROLE_ADMIN, seed_demo_users)

# ── App ────────────────────────────────────────────────────
app = FastAPI(title="PROTACTICS API", version="1.0.0")

# CORS restringido + credenciales (cookies). Un "*" es incompatible con
# cookies en el navegador, por eso se fija el/los origen(es) del frontend.
FRONTEND_ORIGINS = [o.strip() for o in os.getenv(
    "FRONTEND_ORIGIN", "http://localhost:8000,http://127.0.0.1:8000"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.on_event("startup")
def startup():
    init_db()
    # Sembrar usuarios de demostración (uno por perfil) para pruebas.
    if os.getenv("SEED_DEMO_USERS", "true").lower() in ("1", "true", "yes"):
        db = SessionLocal()
        try:
            seed_demo_users(db)
        finally:
            db.close()


# ── Frontend (páginas) ─────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def _page(name: str) -> FileResponse:
    return FileResponse(
        os.path.join(FRONTEND_DIR, name),
        headers={"Cache-Control": "no-store"},  # evita ver páginas cacheadas tras logout
    )


@app.get("/")
def landing():
    """Página de aterrizaje pública (misión y propósito)."""
    return _page("landing.html")


@app.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if user_from_token(db, request.cookies.get(COOKIE_NAME)):
        return RedirectResponse("/dashboard", status_code=302)
    return _page("login.html")


@app.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    if user_from_token(db, request.cookies.get(COOKIE_NAME)):
        return RedirectResponse("/dashboard", status_code=302)
    return _page("register.html")


@app.get("/dashboard")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    if not user_from_token(db, request.cookies.get(COOKIE_NAME)):
        return RedirectResponse("/login", status_code=302)
    return _page("index.html")


@app.get("/admin")
def admin_page(request: Request, db: Session = Depends(get_db)):
    user = user_from_token(db, request.cookies.get(COOKIE_NAME))
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != ROLE_ADMIN:
        return RedirectResponse("/dashboard", status_code=302)
    return _page("admin.html")


@app.get("/admin/approvals")
def approvals_page(request: Request, db: Session = Depends(get_db)):
    user = user_from_token(db, request.cookies.get(COOKIE_NAME))
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != ROLE_ADMIN:
        return RedirectResponse("/dashboard", status_code=302)
    return _page("approvals.html")


# ── Lista pública de puertos (solo nombres) para el registro ─
@app.get("/api/puertos/public")
def get_puertos_public(db: Session = Depends(get_db)):
    puertos = db.query(Puerto).order_by(Puerto.id).all()
    return [{"id": p.id, "nombre_corto": p.nombre_corto, "nombre": p.nombre}
            for p in puertos]


# ── MESES ──────────────────────────────────────────────────
MONTHS = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
          "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


# ── HELPERS ────────────────────────────────────────────────
def read_excel_rows(content: bytes, filename: str) -> list:
    """Lee XLS o XLSX y retorna lista de dicts o lista de listas (header:1)."""
    if filename.lower().endswith(".xls"):
        book = xlrd.open_workbook(file_contents=content)
        sheet = book.sheet_by_index(0)
        rows = []
        for i in range(sheet.nrows):
            rows.append(sheet.row_values(i))
        return rows
    else:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        return rows


def rows_to_dicts(rows: list) -> list[dict]:
    """Convierte lista de arrays a lista de dicts usando la primera fila como header."""
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
    result = []
    for row in rows[1:]:
        result.append({headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))})
    return result


def compute_availability(daily: dict, year: int, mes: int) -> float:
    """Estima la disponibilidad del servicio a partir de los días operativos.

    Disponibilidad = (días con actividad de escaneo / días del mes) × 100.
    Para el mes en curso se usan los días transcurridos hasta hoy.
    Devuelve un porcentaje realista entre 0 y 100 (1 decimal).
    """
    days_active = len([d for d, t in daily.items() if t])
    if days_active == 0:
        return 0.0
    days_in_month = calendar.monthrange(year, mes)[1]
    today = datetime.utcnow()
    eff_days = today.day if (year == today.year and mes == today.month) else days_in_month
    eff_days = max(eff_days, days_active)  # nunca dividir por menos que los días activos
    return round(min(100.0, days_active / eff_days * 100.0), 1)


def save_parsed_data(db: Session, puerto_id: int, year: int, mes: int,
                     data: dict, filename: str):
    """Guarda los datos parseados en la base de datos."""

    # Eliminar datos previos del mismo período
    db.query(EscaneosDiarios).filter_by(puerto_id=puerto_id, year=year, mes=mes).delete()
    db.query(EscaneosHorarios).filter_by(puerto_id=puerto_id, year=year, mes=mes).delete()
    db.query(Operadores).filter_by(puerto_id=puerto_id, year=year, mes=mes).delete()

    # Insertar escaneos diarios
    for dia, total in data["daily"].items():
        db.add(EscaneosDiarios(
            puerto_id=puerto_id, year=year, mes=mes,
            dia=int(dia), total=int(total)
        ))

    # Insertar distribución horaria
    for hora, total in data["hourly"].items():
        db.add(EscaneosHorarios(
            puerto_id=puerto_id, year=year, mes=mes,
            hora=int(hora), total=int(total)
        ))

    # Insertar operadores
    for nombre, total in data.get("operators", {}).items():
        db.add(Operadores(
            puerto_id=puerto_id, year=year, mes=mes,
            nombre=str(nombre), total=int(total)
        ))

    # Registro de archivo
    existing = db.query(ArchivosCargados).filter_by(
        puerto_id=puerto_id, year=year, mes=mes).first()
    if existing:
        existing.nombre_archivo = filename
        existing.formato = data["format"]
        existing.total_escaneos = data["total_scans"]
        existing.cargado_en = datetime.utcnow()
    else:
        db.add(ArchivosCargados(
            puerto_id=puerto_id, year=year, mes=mes,
            nombre_archivo=filename, formato=data["format"],
            total_escaneos=data["total_scans"]
        ))

    # Disponibilidad estimada automáticamente a partir de los datos.
    # Solo se rellena si el usuario NO ha fijado un valor manual antes.
    disp = db.query(Disponibilidad).filter_by(
        puerto_id=puerto_id, year=year, mes=mes).first()
    auto = compute_availability(data["daily"], year, mes)
    if disp is None:
        db.add(Disponibilidad(puerto_id=puerto_id, year=year, mes=mes, valor=auto))
    elif disp.valor is None:
        disp.valor = auto

    db.commit()


# ══════════════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════════════

# ── GET /puertos ────────────────────────────────────────────
@app.get("/puertos")
def get_puertos(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    q = db.query(Puerto).order_by(Puerto.id)
    ids = allowed_port_ids(user)        # None = todos
    if ids is not None:
        if not ids:                     # perfil con alcance sin puerto asignado
            return []
        q = q.filter(Puerto.id.in_(ids))
    puertos = q.all()
    result = []
    for p in puertos:
        # Sumar todos los escaneos del puerto
        total = sum(e.total for e in p.escaneos)
        meses = db.query(EscaneosDiarios.mes, EscaneosDiarios.year)\
                  .filter_by(puerto_id=p.id)\
                  .distinct().count()
        # Disponibilidad más reciente
        last_avail = db.query(Disponibilidad)\
            .filter_by(puerto_id=p.id)\
            .order_by(Disponibilidad.year.desc(), Disponibilidad.mes.desc())\
            .first()
        result.append({
            "id": p.id, "nombre": p.nombre, "nombre_corto": p.nombre_corto,
            "departamento": p.departamento, "lat": p.lat, "lng": p.lng,
            "icono": p.icono, "sx": p.sx, "sy": p.sy, "formato": p.formato,
            "total_escaneos": total, "meses_cargados": meses,
            "ultima_disponibilidad": {
                "valor": last_avail.valor,
                "mes": last_avail.mes,
                "year": last_avail.year,
                "mes_nombre": MONTHS[last_avail.mes - 1]
            } if last_avail and last_avail.valor is not None else None
        })
    return result


# ── POST /upload/{puerto_id}/{year}/{mes} ───────────────────
@app.post("/upload/{puerto_id}/{year}/{mes}")
async def upload_file(
    puerto_id: int, year: int, mes: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not can_upload_port(user, puerto_id):
        raise HTTPException(403, "No tienes permiso para cargar datos en este puerto")
    puerto = db.query(Puerto).filter_by(id=puerto_id).first()
    if not puerto:
        raise HTTPException(404, "Puerto no encontrado")

    content = await file.read()
    raw_rows = read_excel_rows(content, file.filename)

    # Para Rapiscan necesitamos arrays; para otros necesitamos dicts
    # detect_format trabaja con ambos
    from parsers import detect_format
    fmt = detect_format(raw_rows)

    if fmt in ("standard", "tcbuen"):
        rows = rows_to_dicts(raw_rows)
    else:
        rows = raw_rows

    month_name = MONTHS[mes - 1]
    data = parse_file(rows, puerto.nombre_corto, month_name, year, mes)
    save_parsed_data(db, puerto_id, year, mes, data, file.filename)

    return {
        "ok": True,
        "formato": data["format"],
        "total_escaneos": data["total_scans"],
        "dias_activos": data["days_active"],
        "pico_diario": data["peak_day"],
        "promedio_diario": data["avg_daily"],
    }


# ── GET /data/{puerto_id}/{year}/{mes} ──────────────────────
@app.get("/data/{puerto_id}/{year}/{mes}")
def get_data(puerto_id: int, year: int, mes: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    if not can_view_port(user, puerto_id):
        raise HTTPException(403, "No tienes permiso para ver este puerto")
    puerto = db.query(Puerto).filter_by(id=puerto_id).first()
    if not puerto:
        raise HTTPException(404, "Puerto no encontrado")

    diarios = db.query(EscaneosDiarios)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes)\
        .order_by(EscaneosDiarios.dia).all()

    if not diarios:
        raise HTTPException(404, "Sin datos para ese período")

    horarios = db.query(EscaneosHorarios)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).all()

    ops = db.query(Operadores)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).all()

    avail = db.query(Disponibilidad)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).first()

    archivo = db.query(ArchivosCargados)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).first()

    daily  = {str(d.dia): d.total for d in diarios}
    hourly = {str(h.hora): h.total for h in horarios}
    operators = {o.nombre: o.total for o in ops}

    total     = sum(d.total for d in diarios)
    days      = len(diarios)
    peak      = max(d.total for d in diarios)
    avg       = round(total / days) if days else 0

    return {
        "puerto_id": puerto_id,
        "puerto_nombre": puerto.nombre_corto,
        "year": year,
        "mes": mes,
        "mes_nombre": MONTHS[mes - 1],
        "total_scans": total,
        "days_active": days,
        "peak_day": peak,
        "avg_daily": avg,
        "daily": daily,
        "hourly": hourly,
        "operators": operators,
        "operator_count": len(operators),
        "disponibilidad": avail.valor if avail else None,
        "formato": archivo.formato if archivo else None,
    }


# ── GET /meses/{puerto_id} ──────────────────────────────────
@app.get("/meses/{puerto_id}")
def get_meses(puerto_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Retorna qué meses tienen datos para un puerto."""
    if not can_view_port(user, puerto_id):
        raise HTTPException(403, "No tienes permiso para ver este puerto")
    archivos = db.query(ArchivosCargados)\
        .filter_by(puerto_id=puerto_id)\
        .order_by(ArchivosCargados.year, ArchivosCargados.mes).all()

    disponibilidades = db.query(Disponibilidad)\
        .filter_by(puerto_id=puerto_id).all()
    disp_map = {(d.year, d.mes): d.valor for d in disponibilidades}

    return [{
        "year": a.year,
        "mes": a.mes,
        "mes_nombre": MONTHS[a.mes - 1],
        "total_escaneos": a.total_escaneos,
        "formato": a.formato,
        "cargado_en": a.cargado_en.isoformat(),
        "disponibilidad": disp_map.get((a.year, a.mes))
    } for a in archivos]


# ── PUT /disponibilidad/{puerto_id}/{year}/{mes} ─────────────
class DispUpdate(BaseModel):
    valor: Optional[float] = None

@app.put("/disponibilidad/{puerto_id}/{year}/{mes}")
def set_disponibilidad(
    puerto_id: int, year: int, mes: int,
    body: DispUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not can_upload_port(user, puerto_id):
        raise HTTPException(403, "No tienes permiso para editar este puerto")
    if body.valor is not None and not (0 <= body.valor <= 100):
        raise HTTPException(400, "Valor debe estar entre 0 y 100")

    existing = db.query(Disponibilidad)\
        .filter_by(puerto_id=puerto_id, year=year, mes=mes).first()
    if existing:
        existing.valor = body.valor
        existing.actualizado = datetime.utcnow()
    else:
        db.add(Disponibilidad(puerto_id=puerto_id, year=year, mes=mes, valor=body.valor))
    db.commit()
    return {"ok": True, "puerto_id": puerto_id, "year": year, "mes": mes, "valor": body.valor}


# ── GET /disponibilidad/{puerto_id} ─────────────────────────
@app.get("/disponibilidad/{puerto_id}")
def get_disponibilidad(puerto_id: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    if not can_view_port(user, puerto_id):
        raise HTTPException(403, "No tienes permiso para ver este puerto")
    items = db.query(Disponibilidad)\
        .filter_by(puerto_id=puerto_id)\
        .order_by(Disponibilidad.year.desc(), Disponibilidad.mes.desc()).all()
    return [{
        "year": d.year, "mes": d.mes,
        "mes_nombre": MONTHS[d.mes - 1],
        "valor": d.valor
    } for d in items]
