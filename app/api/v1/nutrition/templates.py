"""
Endpoints de meal templates con filtros de budget y estilo.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from app.api.dependencies import get_db
from app.models.plato import Plato

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


@router.get("/templates")
def listar_templates(
    tipo: Optional[str] = Query(None, description="desayuno|almuerzo|cena|snack"),
    budget: Optional[str] = Query(None, description="economico|moderado|premium"),
    style: Optional[str] = Query(None, description="peruano|vegetariano|alto_proteina|ligero|express"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> List[dict]:
    """
    Lista meal templates del catálogo filtrados por tipo, budget y estilo.

    Los macros se calculan en tiempo real desde los ingredientes reales.
    """
    q = db.query(Plato).options(
        joinedload(Plato.ingredientes).joinedload("alimento")
    )

    if tipo:
        q = q.filter(
            (Plato.tipo_plato == tipo) | (Plato.tipo_plato == "cualquiera")
        )
    if budget:
        q = q.filter(Plato.budget_level == budget)
    if style:
        q = q.filter(Plato.meal_style == style)

    platos = q.limit(limit).all()

    result = []
    for p in platos:
        macros = p.calcular_macros()
        result.append({
            "id":           p.id,
            "nombre":       p.nombre,
            "tipo_plato":   p.tipo_plato,
            "budget_level": p.budget_level,
            "meal_style":   p.meal_style,
            "calorias":     macros["calorias"],
            "proteinas_g":  macros["proteinas_g"],
            "carbohidratos_g": macros["carbohidratos_g"],
            "grasas_g":     macros["grasas_g"],
            "ingredientes": [
                {
                    "nombre":  ing.alimento.nombre if ing.alimento else "?",
                    "gramos":  ing.gramos,
                }
                for ing in p.ingredientes
            ],
        })

    return result
