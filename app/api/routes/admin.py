from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.user import User
from app.models.client import Client
from app.models.auditoria import AuditoriaAdmin
from app.schemas.user import UserCreate, UserResponse, PasswordUpdate, UserUpdate
from app.core.security import security
from app.api.routes.auth import get_current_user
from app.models.pago import Pago
from sqlalchemy import func
from datetime import datetime

router = APIRouter()

@router.get("/dashboard-stats")
async def get_admin_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_is_admin(current_user)
    
    total_clientes = db.query(Client).count()
    clientes_activos = db.query(Client).filter(Client.is_active == True).count()
    pagos_pendientes = db.query(Pago).filter(Pago.estado == "pendiente").count()
    
    # Calcular ingresos del mes
    now = datetime.utcnow()
    # Pagos aprobados en el mes y año actual
    pagos_mes = db.query(Pago).filter(
        Pago.estado == "aprobado",
        func.extract('year', Pago.fecha_pago) == now.year,
        func.extract('month', Pago.fecha_pago) == now.month
    ).all()
    
    ingresos_mes = sum((p.monto or 0) for p in pagos_mes)
    
    return {
        "total_clientes": total_clientes,
        "clientes_activos": clientes_activos,
        "pagos_pendientes": pagos_pendientes,
        "ingresos_mes": ingresos_mes
    }



@router.get("/clientes")
async def listar_clientes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_is_admin(current_user)
    clientes = db.query(Client).all()
    return [
        {
            "id": c.id,
            "nombre": c.first_name or "",
            "apellido": c.last_name_paternal or "",
            "email": c.email,
            "telefono": None,
            "is_active": c.is_active,
            "is_profile_complete": c.is_profile_complete,
            "fecha_creacion": c.created_at.isoformat() if c.created_at else "",
        }
        for c in clientes
    ]


@router.delete("/clientes/{cliente_id}")
async def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_is_admin(current_user)
    cliente = db.query(Client).filter(Client.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cliente.is_active = False
    db.commit()

    _log_admin_action(
        db, current_user.id, "CLIENTE_DESACTIVADO",
        f"Se desactivó la cuenta de {cliente.first_name} {cliente.last_name_paternal} ({cliente.email})",
        "clients", cliente.id
    )

    return {"message": f"Cliente {cliente.email} desactivado correctamente", "is_active": False}


def check_is_admin(current_user):
    if str(getattr(current_user, "role_name", "")).lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el administrador puede realizar esta acción"
        )
    return True

def _log_admin_action(db: Session, admin_id: int, accion: str, descripcion: str, tabla: str = None, reg_id: int = None):
    log = AuditoriaAdmin(
        admin_id=admin_id,
        accion=accion,
        descripcion=descripcion,
        tabla_afectada=tabla,
        registro_id=reg_id
    )
    db.add(log)
    db.commit()

@router.post("/usuarios", response_model=UserResponse)
async def crear_personal_staff(
    usuario_data: UserCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permite al administrador crear cuentas para nutricionistas y entrenadores.
    """
    check_is_admin(current_user)
    
    usuario_existente = db.query(User).filter(User.email == usuario_data.email).first()
    if usuario_existente:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado")

    hashed_pwd = security.hash_password(usuario_data.password)
    
    nuevo_usuario = User(
        first_name=usuario_data.first_name,
        last_name_paternal=usuario_data.last_name_paternal,
        last_name_maternal=usuario_data.last_name_maternal,
        email=usuario_data.email,
        hashed_password=hashed_pwd,
        role_name=usuario_data.role, 
        role_id=usuario_data.role_id 
    )
    
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    _log_admin_action(
        db, current_user.id, "REGISTRO_STAFF", 
        f"Se registró a {nuevo_usuario.first_name} ({nuevo_usuario.role_name})",
        "users", nuevo_usuario.id
    )
    
    # ✉️ Enviar correo de bienvenida con credenciales usando Brevo
    try:
        from app.services.email_service import EmailService
        EmailService.send_welcome_credentials_brevo(
            email_to=usuario_data.email,
            dni=usuario_data.password, # Se asume que la contraseña inicial es asignada aquí
            nutricionista_name=f"{current_user.first_name} (Admin)"
        )
    except Exception as e:
        print(f"⚠️ No se pudo enviar el correo de bienvenida al staff: {e}")
    
    return nuevo_usuario

@router.get("/staff")
async def listar_personal_staff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista el personal del staff (nutricionistas, entrenadores y otros administradores).
    """
    # 1. Verificación de permisos
    check_is_admin(current_user)
    
    try:
        # 2. Obtener usuarios filtrados (Incluyendo todas las variantes de admin y staff)
        usuarios_db = db.query(User).filter(
            User.role_name.ilike("%admin%"), # Captura admin, administrador, Administrador, etc.
            User.id != current_user.id
        ).all()
        
        # 3. Mapeo manual a diccionario
        res = []
        for u in usuarios_db:
            res.append({
                "id": u.id,
                "first_name": u.first_name if u.first_name else "N/A",
                "last_name_paternal": u.last_name_paternal if u.last_name_paternal else "",
                "last_name_maternal": u.last_name_maternal if u.last_name_maternal else "",
                "email": u.email if u.email else "sin@email.com",
                "role_name": u.role_name if u.role_name else "admin",
                "is_active": u.is_active,
            })
        return res
    except Exception as e:
        print(f"❌ ERROR LISTAR STAFF: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error en el servidor al obtener personal: {str(e)}"
        )


@router.put("/staff/{user_id}/password")
async def cambiar_password_staff(
    user_id: int,
    password_data: PasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permite al administrador cambiar la contraseña de cualquier miembro del staff.
    """
    check_is_admin(current_user)
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario del staff no encontrado")
        
    usuario.hashed_password = security.hash_password(password_data.new_password)
    db.commit()
    
    _log_admin_action(
        db, current_user.id, "CAMBIO_PASSWORD", 
        f"Se cambió la contraseña de {usuario.first_name} ({usuario.email})",
        "users", usuario.id
    )
    
    return {"message": f"Contraseña de {usuario.first_name} actualizada correctamente"}

@router.put("/staff/{user_id}")
async def actualizar_personal_staff(
    user_id: int,
    usuario_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permite al administrador actualizar los datos básicos de un miembro del staff.
    """
    check_is_admin(current_user)
    
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario del staff no encontrado")

    # Validar duplicación de email si se intenta cambiar
    if usuario_data.email and usuario_data.email != usuario.email:
        email_existente = db.query(User).filter(User.email == usuario_data.email).first()
        if email_existente:
            raise HTTPException(status_code=400, detail="El nuevo correo electrónico ya está registrado")
        usuario.email = usuario_data.email

    # Actualizar campos opcionales
    if usuario_data.first_name:
        usuario.first_name = usuario_data.first_name
    if usuario_data.last_name_paternal:
        usuario.last_name_paternal = usuario_data.last_name_paternal
    if usuario_data.last_name_maternal:
        usuario.last_name_maternal = usuario_data.last_name_maternal
    if usuario_data.role_name:
        usuario.role_name = usuario_data.role_name
    if usuario_data.role_id:
        usuario.role_id = usuario_data.role_id

    db.commit()
    db.refresh(usuario)
    
    _log_admin_action(
        db, current_user.id, "ACTUALIZACION_STAFF", 
        f"Se actualizaron los datos de {usuario.first_name} ({usuario.email})",
        "users", usuario.id
    )
    
    return {"message": f"Datos de {usuario.first_name} actualizados correctamente"}

@router.put("/staff/{user_id}/status")
async def alternar_estado_staff(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permite al administrador suspender (dar de baja) o reactivar a un miembro del staff.
    """
    check_is_admin(current_user)
    
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario del staff no encontrado")

    # Invertir estado
    nuevo_estado = not usuario.is_active
    usuario.is_active = nuevo_estado
    db.commit()
    
    accion = "PERSONAL_SUSPENDIDO" if not nuevo_estado else "PERSONAL_REACTIVADO"
    descripcion = f"Se {'suspendió' if not nuevo_estado else 'reactivó'} la cuenta de {usuario.first_name} ({usuario.email})"
    
    _log_admin_action(
        db, current_user.id, accion, descripcion,
        "users", usuario.id
    )
    
    return {
        "message": descripcion,
        "is_active": nuevo_estado
    }

@router.delete("/staff/{user_id}")
async def eliminar_personal_staff(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permite al administrador eliminar permanentemente a un miembro del staff.
    """
    check_is_admin(current_user)
    
    usuario = db.query(User).filter(User.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario del staff no encontrado")

    nombre_baja = f"{usuario.first_name} ({usuario.email})"

    db.delete(usuario)
    db.commit()
    
    _log_admin_action(
        db, current_user.id, "PERSONAL_ELIMINADO", 
        f"Se eliminó permanentemente la cuenta de {nombre_baja}",
        "users", None
    )
    
    return {"message": f"Personal eliminado correctamente"}

@router.get("/logs")
async def listar_logs_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los eventos de auditoría administrativa.
    """
    check_is_admin(current_user)
    
    logs = db.query(AuditoriaAdmin).order_by(AuditoriaAdmin.fecha_evento.desc()).limit(100).all()
    
    return [
        {
            "id": log.id,
            "accion": log.accion,
            "descripcion": log.descripcion,
            "fecha": log.fecha_evento,
            "admin_id": log.admin_id
        }
        for log in logs
    ]
