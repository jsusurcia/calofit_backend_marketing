"""
Helpers para obtener el plan nutricional activo del cliente.

Exporta:
  obtener_plan_hoy(perfil, edad, db) → (plan_maestro, plan_hoy_data, usa_fallback)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.utils import get_peru_date
from app.models.nutricion import PlanDiario, PlanNutricional


def obtener_plan_hoy(perfil, edad: int, db: Session):
    """
    Devuelve (plan_maestro, plan_hoy_data dict, usa_fallback bool).

    Si el cliente no tiene plan validado, calcula TMB + TDEE con Mifflin-St Jeor
    y devuelve un objeto PlanFallback compatible con los campos que usa el asistente.
    """
    plan_maestro = (
        db.query(PlanNutricional)
        .filter(PlanNutricional.client_id == perfil.id)
        .order_by(PlanNutricional.fecha_creacion.desc())
        .first()
    )

    if not plan_maestro:
        from app.services.calculador_dieta import CalculadorDietaAutomatica

        genero = getattr(perfil, "gender", "M") or "M"
        nivel = getattr(perfil, "activity_level", "Moderado") or "Moderado"
        if nivel == "Intenso": nivel = "Activo"
        elif nivel == "Muy intenso": nivel = "Muy activo"
        
        objetivo_raw = getattr(perfil, "goal", "Mantener peso") or "Mantener peso"
        objetivo = "Mantener peso"
        if "ganar" in objetivo_raw.lower(): objetivo = "Ganar masa"
        elif "perder" in objetivo_raw.lower() or "bajar" in objetivo_raw.lower(): objetivo = "Perder peso"

        recomendacion = CalculadorDietaAutomatica.calcular_recomendacion_dieta(
            peso=float(perfil.weight or 70),
            altura=float(perfil.height or 170),
            edad=edad,
            genero=genero,
            nivel_actividad=nivel,
            objetivo=objetivo,
        )
        macros = {
            "calorias_objetivo": recomendacion.calorias_diarias,
            "proteinas_g": recomendacion.proteinas_g,
            "carbohidratos_g": recomendacion.carbohidratos_g,
            "grasas_g": recomendacion.grasas_g,
        }

        class _PlanFallback:
            def __init__(self, objetivo):
                self.objetivo       = objetivo
                self.status         = "calculado_ia"
                self.id             = None
                self.fecha_creacion = datetime.now()

        return (
            _PlanFallback(objetivo=perfil.goal),
            {
                "calorias_dia":              macros.get("calorias_objetivo", 2000),
                "proteinas_g":               macros["proteinas_g"],
                "carbohidratos_g":           macros["carbohidratos_g"],
                "grasas_g":                  macros["grasas_g"],
                "sugerencia_entrenamiento_ia": "Plan calculado automáticamente por IA",
            },
            True,
        )

    dia_semana = get_peru_date().isoweekday()
    plan_hoy   = (
        db.query(PlanDiario)
        .filter(PlanDiario.plan_id == plan_maestro.id, PlanDiario.dia_numero == dia_semana)
        .first()
        or db.query(PlanDiario).filter(PlanDiario.plan_id == plan_maestro.id).first()
    )
    if not plan_hoy:
        raise ValueError("Tu plan nutricional está incompleto.")

    return (
        plan_maestro,
        {
            "calorias_dia":              plan_hoy.calorias_dia,
            "proteinas_g":               plan_hoy.proteinas_g,
            "carbohidratos_g":           plan_hoy.carbohidratos_g,
            "grasas_g":                  plan_hoy.grasas_g,
            "sugerencia_entrenamiento_ia": plan_hoy.sugerencia_entrenamiento_ia,
        },
        False,
    )
