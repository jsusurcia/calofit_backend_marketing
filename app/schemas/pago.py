from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PagoCreate(BaseModel):
    client_id: int
    metodo_pago: str = Field(..., pattern="^(yape|efectivo)$")
    monto: Optional[float] = None
    concepto: Optional[str] = "Membresía"


class PagoRechazar(BaseModel):
    notas_admin: Optional[str] = None


class PagoResponse(BaseModel):
    id: int
    client_id: int
    metodo_pago: str
    estado: str
    monto: Optional[float]
    concepto: Optional[str]
    comprobante_url: Optional[str]
    notas_admin: Optional[str]
    registrado_por_id: Optional[int]
    validado_por_id: Optional[int]
    fecha_pago: datetime
    fecha_validacion: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class PagoListItem(BaseModel):
    id: int
    client_id: int
    client_nombre: str
    client_email: str
    metodo_pago: str
    estado: str
    monto: Optional[float]
    concepto: Optional[str]
    comprobante_url: Optional[str]
    fecha_pago: datetime

    class Config:
        from_attributes = True
