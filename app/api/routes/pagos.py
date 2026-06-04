import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.core.database import get_db
from app.models.client import Client
from app.models.pago import Pago
from app.models.user import User
from app.api.routes.auth import get_current_user, get_current_staff
from app.schemas.pago import PagoCreate, PagoRechazar, PagoResponse, PagoListItem, PagoAprobar
from typing import Optional

router = APIRouter()

UPLOAD_DIR = "app/uploads/pagos"
os.makedirs(UPLOAD_DIR, exist_ok=True)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def _save_comprobante(file_bytes: bytes, original_filename: str) -> str:
    ext = os.path.splitext(original_filename)[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return f"{BASE_URL}/uploads/pagos/{filename}"


def _check_staff(current_user):
    if not isinstance(current_user, User):
        raise HTTPException(status_code=403, detail="Solo staff puede realizar esta acción")
    return current_user


def _pago_to_list_item(p: Pago, cliente: Client | None) -> PagoListItem:
    nombre = f"{cliente.first_name or ''} {cliente.last_name_paternal or ''}".strip() if cliente else "—"
    return PagoListItem(
        id=p.id,
        client_id=p.client_id,
        client_nombre=nombre or (cliente.email if cliente else "—"),
        client_email=cliente.email if cliente else "—",
        client_phone=cliente.phone if cliente else None,
        metodo_pago=p.metodo_pago,
        estado=p.estado,
        monto=p.monto,
        concepto=p.concepto,
        comprobante_url=p.comprobante_url,
        fecha_pago=p.fecha_pago,
    )


def _build_pago_list(db: Session, estado: str | None = None) -> list[PagoListItem]:
    query = db.query(Pago)
    if estado:
        query = query.filter(Pago.estado == estado)
    pagos = query.order_by(Pago.created_at.desc()).all()
    client_ids = list({p.client_id for p in pagos})
    clientes = db.query(Client).filter(Client.id.in_(client_ids)).all() if client_ids else []
    cliente_map = {c.id: c for c in clientes}
    return [_pago_to_list_item(p, cliente_map.get(p.client_id)) for p in pagos]


def _check_admin(current_user):
    _check_staff(current_user)
    role = str(getattr(current_user, "role_name", "")).lower()
    if role not in {"admin", "superadmin", "administrador"}:
        raise HTTPException(status_code=403, detail="Solo administradores pueden validar pagos")
    return current_user


@router.post("/registrar", response_model=PagoResponse)
def registrar_pago(
    data: PagoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Staff registra un pago (Yape o efectivo) para un cliente."""
    cliente = db.query(Client).filter(Client.id == data.client_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    pago = Pago(
        client_id=data.client_id,
        metodo_pago=data.metodo_pago,
        monto=data.monto,
        concepto=data.concepto,
        estado="aprobado",  # Cambiado de pendiente a aprobado
        registrado_por_id=current_user.id,
        validado_por_id=current_user.id,
        fecha_validacion=datetime.utcnow()
    )
    
    # Activar al cliente directamente
    cliente.is_active = True
    
    db.add(pago)
    db.commit()
    db.refresh(pago)
    return pago


@router.post("/{pago_id}/comprobante", response_model=PagoResponse)
async def subir_comprobante(
    pago_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Sube imagen de comprobante Yape al pago. Solo para metodo_pago='yape'."""
    pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.metodo_pago != "yape":
        raise HTTPException(status_code=400, detail="Comprobante solo aplica a pagos Yape")
    if pago.estado != "pendiente":
        raise HTTPException(status_code=400, detail="El pago ya fue procesado")
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")

    file_bytes = await file.read()
    url = _save_comprobante(file_bytes, file.filename)

    pago.comprobante_url = url
    db.commit()
    db.refresh(pago)
    return pago


@router.get("/pendientes", response_model=list[PagoListItem])
def listar_pendientes(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Admin/Staff: lista todos los pagos en estado pendiente."""
    return _build_pago_list(db, estado="pendiente")


@router.get("/lista", response_model=list[PagoListItem])
def listar_pagos(
    estado: Optional[str] = Query(None, description="pendiente | aprobado | rechazado"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Admin/Staff: lista todos los pagos, con filtro opcional por estado."""
    return _build_pago_list(db, estado=estado)


@router.get("/buscar", response_model=list[PagoListItem])
def buscar_pagos(
    q: str = Query(..., min_length=1, description="Nombre, apellido, correo o celular del cliente"),
    estado: Optional[str] = Query(None, description="pendiente | aprobado | rechazado"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Admin/Staff: busca pagos por nombre, apellido, correo o celular del cliente."""
    term = f"%{q.strip().lower()}%"
    clientes = (
        db.query(Client)
        .filter(
            or_(
                func.lower(Client.first_name).like(term),
                func.lower(Client.last_name_paternal).like(term),
                func.lower(Client.last_name_maternal).like(term),
                func.lower(Client.email).like(term),
                Client.phone.like(term),
            )
        )
        .all()
    )
    if not clientes:
        return []

    client_ids = [c.id for c in clientes]
    query = db.query(Pago).filter(Pago.client_id.in_(client_ids))
    if estado:
        query = query.filter(Pago.estado == estado)
    pagos = query.order_by(Pago.created_at.desc()).all()

    cliente_map = {c.id: c for c in clientes}
    return [_pago_to_list_item(p, cliente_map.get(p.client_id)) for p in pagos]


@router.get("/cliente/{client_id}", response_model=list[PagoResponse])
def listar_pagos_cliente(
    client_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Staff: historial de pagos de un cliente."""
    return (
        db.query(Pago)
        .filter(Pago.client_id == client_id)
        .order_by(Pago.created_at.desc())
        .all()
    )


@router.get("/{pago_id}", response_model=PagoResponse)
def detalle_pago(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    return pago


@router.put("/{pago_id}/aprobar", response_model=PagoResponse)
def aprobar_pago(
    pago_id: int,
    data: PagoAprobar,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Admin aprueba pago → activa cuenta del cliente."""
    _check_admin(current_user)

    pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"El pago ya está en estado '{pago.estado}'")

    pago.estado = "aprobado"
    pago.metodo_pago = data.metodo_pago
    pago.monto = 15.0
    pago.validado_por_id = current_user.id
    pago.fecha_validacion = datetime.utcnow()

    cliente = db.query(Client).filter(Client.id == pago.client_id).first()
    if cliente:
        cliente.is_active = True

    db.commit()
    db.refresh(pago)
    return pago


@router.put("/{pago_id}/rechazar", response_model=PagoResponse)
def rechazar_pago(
    pago_id: int,
    data: PagoRechazar,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_staff),
):
    """Admin rechaza pago. La cuenta del cliente sigue inactiva."""
    _check_admin(current_user)

    pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    if pago.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"El pago ya está en estado '{pago.estado}'")

    pago.estado = "rechazado"
    pago.validado_por_id = current_user.id
    pago.fecha_validacion = datetime.utcnow()
    pago.notas_admin = data.notas_admin

    db.commit()
    db.refresh(pago)
    return pago
