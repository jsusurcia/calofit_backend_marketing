"""
Recalcula la meta diaria (kcal y macros) del plan más reciente de cada cliente.

Los planes creados por /nutricion/generar-plan-automatico antes de la corrección quedaron con
valores fijos (2000 kcal, 100/200/60 g). Este script los reemplaza por la meta calculada con el
perfil actual del cliente (misma fórmula que el recálculo al editar el perfil).

Uso (desde la raíz del backend, dentro del contenedor):
    python -m scripts.recalcular_metas_planes            # solo muestra qué cambiaría
    python -m scripts.recalcular_metas_planes --aplicar  # guarda los cambios
"""
import sys
from datetime import date

import app.models  # noqa: F401  (registra todos los modelos)
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.nutricion import PlanDiario, PlanNutricional
from app.services.calculador_dieta import CalculadorDietaAutomatica


def main(aplicar: bool) -> None:
    db = SessionLocal()
    try:
        cambios = 0
        for cliente in db.query(Client).all():
            plan = (
                db.query(PlanNutricional)
                .filter(PlanNutricional.client_id == cliente.id)
                .order_by(PlanNutricional.fecha_creacion.desc())
                .first()
            )
            if not plan:
                continue

            edad = 30
            if cliente.birth_date:
                hoy = date.today()
                edad = hoy.year - cliente.birth_date.year - (
                    (hoy.month, hoy.day) < (cliente.birth_date.month, cliente.birth_date.day)
                )

            meta = CalculadorDietaAutomatica.calcular_recomendacion_dieta(
                peso=float(cliente.weight or 70),
                altura=float(cliente.height or 170),
                edad=edad,
                genero=cliente.gender or "M",
                nivel_actividad=cliente.activity_level or "Moderado",
                objetivo=cliente.goal or "Mantener peso",
            )
            kcal = round(meta.calorias_diarias)

            dias = db.query(PlanDiario).filter(PlanDiario.plan_id == plan.id).all()
            if all(round(d.calorias_dia or 0) == kcal for d in dias):
                continue

            actual = round(dias[0].calorias_dia or 0) if dias else 0
            print(f"cliente {cliente.id} ({cliente.email}): {actual} -> {kcal} kcal "
                  f"[{cliente.goal}, {cliente.activity_level}]")
            cambios += 1
            if aplicar:
                plan.calorias_ia_base = kcal
                for d in dias:
                    d.calorias_dia = kcal
                    d.proteinas_g = meta.proteinas_g
                    d.carbohidratos_g = meta.carbohidratos_g
                    d.grasas_g = meta.grasas_g

        if aplicar:
            db.commit()
            print(f"Listo: {cambios} plan(es) actualizado(s).")
        else:
            print(f"{cambios} plan(es) cambiarían. Ejecuta con --aplicar para guardar.")
    finally:
        db.close()


if __name__ == "__main__":
    main("--aplicar" in sys.argv)
