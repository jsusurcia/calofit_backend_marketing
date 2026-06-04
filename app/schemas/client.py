from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import date

# --- TUS ESQUEMAS EXISTENTES ---

class ClientCreate(BaseModel):
    first_name: str
    last_name_paternal: str
    last_name_maternal: str
    email: EmailStr
    password: str = Field(..., min_length=6)
    birth_date: date
    weight: float = Field(..., gt=0, description="Peso en kilogramos")
    height: float = Field(..., gt=0, description="Altura en centímetros")
    gender: str = Field(..., pattern="^[MF]$", description="Género: M (Masculino) o F (Femenino)")
    
    medical_conditions: List[str] = Field(default=[], description="Lista de condiciones médicas")
    
    activity_level: Optional[str] = Field(default="Sedentario", description="Nivel de actividad física")
    goal: Optional[str] = Field(default="Mantener peso", description="Objetivo de salud")
    workout_type: Optional[str] = Field(default=None, description="Tipo de entrenamiento preferido (para ML)")
    session_duration: Optional[float] = Field(default=None, description="Duración de sesión en horas (para ML)")
    flutter_uid: Optional[str] = None

    class Config:
        from_attributes = True


class ClientResponse(BaseModel):
    id: int
    first_name: str
    last_name_paternal: str
    last_name_maternal: str
    email: EmailStr
    birth_date: Optional[date]
    weight: float
    height: float
    gender: Optional[str] = 'M'
    activity_level: Optional[str] = 'Sedentario'
    goal: Optional[str] = 'Mantener peso'
    workout_type: Optional[str] = 'Cardio'
    session_duration: Optional[float] = 1.0
    medical_conditions: List[str] = []
    profile_picture_url: Optional[str] = None
    is_profile_complete: bool = False
    meal_reminder_time: Optional[str] = None

    class Config:
        from_attributes = True

class ClientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name_paternal: Optional[str] = None
    last_name_maternal: Optional[str] = None
    email: Optional[EmailStr] = None
    birth_date: Optional[date] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    gender: Optional[str] = None
    medical_conditions: Optional[List[str]] = None
    activity_level: Optional[str] = None
    goal: Optional[str] = None
    workout_type: Optional[str] = None
    session_duration: Optional[float] = None
    profile_picture_url: Optional[str] = None
    is_profile_complete: Optional[bool] = None
    meal_reminder_time: Optional[str] = None


class AdminCreateClient(BaseModel):
    """Schema para que el Admin cree un paciente con credenciales mínimas"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = ""
    last_name_paternal: Optional[str] = ""
    last_name_maternal: Optional[str] = ""

class ClientExpressCreate(BaseModel):
    """Schema para la creación B2B de un paciente solo usando DNI y Correo."""
    email: EmailStr
    dni: str = Field(..., min_length=7, max_length=15, description="El DNI será usado como clave temporal")

class ChangePassword(BaseModel):
    new_password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)

# --- 🚀 NUEVOS ESQUEMAS ESTRATÉGICOS (v80.0) ---

class StrategicGuideUpdate(BaseModel):
    """Admin actualiza guía estratégica del cliente"""
    ai_strategic_focus: Optional[str] = None
    recommended_foods: Optional[List[str]] = None
    forbidden_foods: Optional[List[str]] = None
    medical_conditions: Optional[List[str]] = None
    workout_type: Optional[str] = None
    session_duration: Optional[float] = None

ACTIVITY_LEVELS = {"Sedentario", "Ligero", "Moderado", "Intenso", "Muy intenso"}
GOALS = {"Perder peso", "Mantener peso", "Ganar masa"}

class ClientDatosUpdate(BaseModel):
    """Actualización de datos físicos y de salud del cliente."""
    weight: Optional[float] = Field(default=None, gt=0, description="Peso en kilogramos")
    height: Optional[float] = Field(default=None, gt=0, description="Altura en centímetros")
    activity_level: Optional[str] = Field(default=None, description="Nivel de actividad física")
    goal: Optional[str] = Field(default=None, description="Objetivo de salud")
    medical_conditions: Optional[List[str]] = Field(default=None, description="Lista de condiciones médicas")

    @field_validator("activity_level")
    @classmethod
    def validate_activity_level(cls, v):
        if v is not None and v not in ACTIVITY_LEVELS:
            raise ValueError(f"Nivel de actividad inválido. Opciones: {', '.join(sorted(ACTIVITY_LEVELS))}")
        return v

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v):
        if v is not None and v not in GOALS:
            raise ValueError(f"Objetivo inválido. Opciones: {', '.join(sorted(GOALS))}")
        return v

    class Config:
        from_attributes = True


class ResetPasswordRequest(BaseModel):
    """Para cuando el usuario ingresa su email para recibir el código"""
    email: EmailStr

class ResetPasswordVerify(BaseModel):
    """Para cuando el usuario ingresa el código de 6 dígitos y su nueva clave"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)

    @field_validator('confirm_password')
    @classmethod
    def passwords_match_reset(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Las contraseñas no coinciden')
        return v