"""
Historial persistente del chat con CaloCoach.

Hilo unico y continuo por cliente (no hay conversaciones separadas).
`id` sirve como cursor para paginar mensajes antiguos.
"""
from sqlalchemy import Column, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    role = Column(String(20), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)

    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    cliente = relationship("Client", back_populates="chat_messages")
