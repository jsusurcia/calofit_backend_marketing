from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    registrado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    validado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # "yape" | "efectivo"
    metodo_pago = Column(String(20), nullable=False)
    # "pendiente" | "aprobado" | "rechazado"
    estado = Column(String(20), nullable=False, default="pendiente")

    monto = Column(Float, nullable=True)
    concepto = Column(String(200), nullable=True, default="Membresía")
    comprobante_url = Column(String, nullable=True)
    notas_admin = Column(Text, nullable=True)

    fecha_pago = Column(DateTime, default=datetime.utcnow)
    fecha_validacion = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Client", back_populates="pagos")
    registrado_por = relationship("User", foreign_keys=[registrado_por_id])
    validado_por = relationship("User", foreign_keys=[validado_por_id])
