from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime, Date, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.dialects.postgresql import ARRAY
from app.core.database import Base

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=True)
    last_name_paternal = Column(String, nullable=True)
    last_name_maternal = Column(String, nullable=True)
    dni = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    planes_nutricionales = relationship(
        "PlanNutricional",
        back_populates="cliente",
        cascade="all, delete-orphan",
    )
    
    
    birth_date = Column(Date, nullable=True)  # Fecha de nacimiento
    weight = Column(Float)  # Peso actual (kg)
    height = Column(Float)  # Altura (cm) - ESTANDARIZADA A CENTÍMETROS
    gender = Column(String(1), default='M', nullable=False)  # 'M' (Hombre) o 'F' (Mujer) - NECESARIO para fórmula Harris-Benedict
    medical_conditions = Column(ARRAY(String), nullable=True, default=[])
    activity_level = Column(String, nullable=True, default='Moderado')  # Nivel de actividad física: Sedentario, Ligero, Moderado, Intenso, Muy intenso
    goal = Column(String, nullable=True, default='Mantener peso')  # Objetivo principal: Perder peso, Mantener peso, Ganar masa
    workout_type = Column(String, nullable=True, default='Cardio')  # 🆕 Tipo de ejercicio preferido (para ML Random Forest)
    session_duration = Column(Float, nullable=True, default=1.0)   # 🆕 Duración de sesión en horas (para ML Random Forest)
    meal_reminder_time = Column(String, nullable=True) # Hora para recordar el registro de comidas (ej. "20:00")
    
    recommended_foods = Column(ARRAY(String), nullable=True, default=[])
    forbidden_foods = Column(ARRAY(String), nullable=True, default=[])
    ai_strategic_focus = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    is_profile_complete = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Nuevas relaciones para historial
    historial_peso = relationship("HistorialPeso", back_populates="cliente", cascade="all, delete-orphan")
    historial_imc = relationship("HistorialIMC", back_populates="cliente", cascade="all, delete-orphan")
    progreso_calorias = relationship("ProgresoCalorias", back_populates="cliente", cascade="all, delete-orphan")
    alertas_salud = relationship("AlertaSalud", back_populates="cliente", cascade="all, delete-orphan")
    sugerencias_guardadas = relationship("SugerenciaGuardada", back_populates="cliente", cascade="all, delete-orphan")
    
    # Relaciones para sistema de aprendizaje de preferencias
    preferencias_alimentos = relationship("PreferenciaAlimento", back_populates="cliente", cascade="all, delete-orphan")
    preferencias_ejercicios = relationship("PreferenciaEjercicio", back_populates="cliente", cascade="all, delete-orphan")

    comida_registros = relationship("ComidaRegistro", back_populates="cliente", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="cliente", cascade="all, delete-orphan")

    verification_code = Column(String(6), nullable=True)
    code_expires_at = Column(DateTime, nullable=True)