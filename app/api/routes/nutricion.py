from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
# Asegúrate de importar PlanDiario
from app.models.nutricion import PlanNutricional, PlanDiario
from app.schemas.nutricion import PlanNutricionalCreate, PlanNutricionalResponse
from typing import List, Optional, Any, Dict
from datetime import datetime

from app.api.routes.auth import get_current_staff, get_current_user
from app.services.ia_service import ia_engine 

router = APIRouter()


@router.post("/", response_model=PlanNutricionalResponse)
async def crear_plan_nutricional(
    plan_data: PlanNutricionalCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_staff)
):
    # 1. Seguridad
    if current_user.role_name not in ["nutritionist", "admin"]:
        raise HTTPException(status_code=403, detail="No autorizado")

    # 2. IA: Cálculo de Calorías Base
    try:
        calorias_base = ia_engine.calcular_requerimiento(
            genero=plan_data.genero, edad=plan_data.edad,
            peso=plan_data.peso, talla=plan_data.talla,
            nivel_actividad=plan_data.nivel_actividad, objetivo=plan_data.objetivo
        )
    except Exception as e:
        print(f"Error en calcular_requerimiento: {str(e)}")
        # Fallback: Usar fórmula de Harris-Benedict
        if plan_data.genero == 1:  # Masculino
            tmb = 88.362 + (13.397 * plan_data.peso) + (4.799 * plan_data.talla) - (5.677 * plan_data.edad)
        else:  # Femenino
            tmb = 447.593 + (9.247 * plan_data.peso) + (3.098 * plan_data.talla) - (4.330 * plan_data.edad)
        
        calorias_mantenimiento = tmb * plan_data.nivel_actividad
        
        if plan_data.objetivo == "ganar":
            calorias_base = calorias_mantenimiento + 500
        elif plan_data.objetivo == "perder":
            calorias_base = calorias_mantenimiento - 500
        else:
            calorias_base = calorias_mantenimiento
        
        calorias_base = round(calorias_base, 2)
        print(f"Usando cálculo alternativo: {calorias_base} kcal")

    # 3. IA Avanzada: Recomendaciones con Groq + CBF
    perfil_usuario = {
        "edad": plan_data.edad,
        "genero": plan_data.genero,
        "peso": plan_data.peso,
        "talla": plan_data.talla,
        "objetivo": plan_data.objetivo,
        "nivel_actividad": plan_data.nivel_actividad
    }
    try:
        recomendacion_groq = ia_engine.recomendar_alimentos_con_groq(perfil_usuario)
    except Exception as e:
        recomendacion_groq = "Error al generar recomendación avanzada. Usa plan básico."

    # 4. Guardar Plan Maestro (Encabezado)
    nuevo_plan = PlanNutricional(
        client_id=plan_data.client_id,
        nutricionista_id=current_user.id,
        genero=plan_data.genero, edad=plan_data.edad,
        peso=plan_data.peso, talla=plan_data.talla,
        nivel_actividad=plan_data.nivel_actividad,
        objetivo=plan_data.objetivo,
        calorias_ia_base=calorias_base,
        es_contingencia_ia=False, # Plan oficial creado en consulta
        observaciones=plan_data.observaciones
    )

    try:
        db.add(nuevo_plan)
        db.flush() 

        # 4. Generación Semanal Inteligente
        for i in range(1, 8):
            # Diferenciamos carga: Días 1-5 (Entreno) vs 6-7 (Descanso)
            factor = 1.1 if i <= 5 else 0.9
            cals_dia = round(calorias_base * factor, 2)
            
            # IA genera consejos para el Coach y el Cliente
            sugerencia_entreno = ia_engine.generar_sugerencia_entrenamiento(plan_data.objetivo, i)
            nota_ia = "Plan generado automáticamente para dar continuidad a tu progreso."

            dia = PlanDiario(
                plan_id=nuevo_plan.id,
                dia_numero=i,
                calorias_dia=cals_dia,
                # Repartición de macros basada en calorías del día
                proteinas_g=round((cals_dia * 0.25) / 4, 1),
                carbohidratos_g=round((cals_dia * 0.50) / 4, 1),
                grasas_g=round((cals_dia * 0.25) / 9, 1),
                # Campos de asistencia
                sugerencia_entrenamiento_ia=sugerencia_entreno,
                nota_asistente_ia=nota_ia,
                estado="sugerencia_ia", # Disponible para el cliente al instante
                validado_nutri=True
            )
            db.add(dia)

        db.commit()
        db.refresh(nuevo_plan)
        
        # Devolver el plan completo con sus relaciones cargadas
        return nuevo_plan

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")


# =================================================================
# 🍎 NUEVOS ENDPOINTS: GESTIÓN DE PLANES (FLUJO GYM REAL)
# =================================================================

@router.get("/planes/pendientes", response_model=list[PlanNutricionalResponse])
async def listar_planes_pendientes(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_staff)
):
    """
    Lista los planes en estado 'draft_ia' (generados por IA)
    que pertenecen a los clientes asignados al nutricionista logueado.
    """
    from app.models.client import Client
    
    query = db.query(PlanNutricional).filter(PlanNutricional.status == "draft_ia")
    
    # Si el usuario es nutricionista, solo ver sus asignados
    if current_user.role_name == "nutritionist":
        query = query.join(Client).filter(Client.assigned_nutri_id == current_user.id)
    
    return query.all()

@router.put("/planes/{plan_id}/validar")
async def validar_plan_nutricional(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_staff)
):
    """
    El nutricionista revisa y aprueba el plan generado por la IA.
    1. Cambia el estado a 'validado'.
    2. Registra quién y cuándo lo validó.
    3. Cambia el estado de los detalles diarios a 'oficial'.
    """
    plan = db.query(PlanNutricional).filter(PlanNutricional.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
        
    # Seguridad: Un nutri solo puede validar si el cliente está asignado a él
    # o si es administrador
    from app.models.client import Client
    cliente = db.query(Client).filter(Client.id == plan.client_id).first()
    
    if current_user.role_name == "nutritionist" and cliente.assigned_nutri_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para validar planes de este cliente")

    # Actualizar cabecera del plan
    plan.status = "validado"
    plan.validated_by_id = current_user.id
    plan.validated_at = datetime.utcnow()
    plan.nutricionista_id = current_user.id # Asignar formalmente al plan
    
    # Actualizar todos los días del plan a oficial
    for dia in plan.detalles_diarios:
        dia.estado = "oficial"
        dia.validado_nutri = True
        
    db.commit()
    
    return {
        "message": "Plan validado exitosamente",
        "plan_id": plan.id,
        "validado_por": f"{current_user.first_name} {current_user.last_name_paternal}",
        "fecha": plan.validated_at.isoformat()
    }


@router.get("/recomendaciones")
async def obtener_recomendaciones_personalizadas(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🧠 SISTEMA DE APRENDIZAJE: Recomendaciones personalizadas de alimentos
    
    - Usuario NUEVO → Top 10 alimentos populares generales
    - Usuario CON historial → Sus favoritos + similares
    """
    from app.models.client import Client
    from app.models.preferencias import PreferenciaAlimento
    
    # Obtener cliente
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    # Consultar preferencias del cliente
    preferencias = db.query(PreferenciaAlimento).filter(
        PreferenciaAlimento.client_id == cliente.id
    ).order_by(PreferenciaAlimento.frecuencia.desc()).limit(10).all()
    
    if len(preferencias) < 3:  # Cold start - Usuario nuevo
        # Recomendaciones generales según objetivo
        recomendaciones_base = {
            "Perder peso": [
                {"nombre": "Pollo a la plancha", "categoria": "proteina", "calorias_aprox": 165},
                {"nombre": "Ensalada verde", "categoria": "verduras", "calorias_aprox": 50},
                {"nombre": "Pescado blanco", "categoria": "proteina", "calorias_aprox": 100},
            ],
            "Ganar masa": [
                {"nombre": "Arroz integral", "categoria": "carbohidratos", "calorias_aprox": 215},
                {"nombre": "Pollo con piel", "categoria": "proteina", "calorias_aprox": 230},
                {"nombre": "Batata", "categoria": "carbohidratos", "calorias_aprox": 180},
            ],
            "Mantener peso": [
                {"nombre": "Arroz con pollo", "categoria": "completo", "calorias_aprox": 350},
                {"nombre": "Salmon", "categoria": "proteina", "calorias_aprox": 206},
                {"nombre": "Quinoa", "categoria": "carbohidratos", "calorias_aprox": 222},
            ]
        }
        
        objetivo = cliente.goal or "Mantener peso"
        recomendaciones = recomendaciones_base.get(objetivo, recomendaciones_base["Mantener peso"])
        
        return {
            "tipo": "cold_start",
            "mensaje": "Recomendaciones generales segun tu objetivo",
            "recomendaciones": recomendaciones,
            "nota": "El sistema aprendera tus preferencias a medida que registres tus comidas"
        }
    
    else:  # Usuario con historial
        favoritos = [
            {
                "nombre": pref.alimento.capitalize(),
                "frecuencia": pref.frecuencia,
                "puntuacion": round(pref.puntuacion, 2),
                "ultima_vez": pref.ultima_vez.strftime("%Y-%m-%d")
            }
            for pref in preferencias
        ]
        
        return {
            "tipo": "personalizado",
            "mensaje": f"Basado en tus {len(favoritos)} alimentos favoritos",
            "favoritos": favoritos,
            "nota": "Estas son tus elecciones mas frecuentes"
        }

@router.delete("/comidas/{registro_id}")
async def eliminar_registro_comida(
    registro_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Elimina un registro de comida y descuenta sus calorías/macros del progreso diario.
    """
    from app.models.comida_registro import ComidaRegistro
    from app.models.historial import ProgresoCalorias
    from app.models.client import Client
    
    # 1. Verificar usuario
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=403, detail="Usuario no autorizado")
        
    # 2. Buscar registro
    registro = db.query(ComidaRegistro).filter(
        ComidaRegistro.id == registro_id,
        ComidaRegistro.client_id == cliente.id
    ).first()
    
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de comida no encontrado")
        
    # 3. Restar del progreso diario
    fecha_registro = registro.fecha
    progreso = db.query(ProgresoCalorias).filter(
        ProgresoCalorias.client_id == cliente.id,
        ProgresoCalorias.fecha == fecha_registro
    ).first()
    
    if progreso:
        kcal = float(registro.kcal or 0)
        prot = float(registro.proteina_g or 0)
        carb = float(registro.carbohidratos_g or 0)
        gras = float(registro.grasas_g or 0)
        
        progreso.calorias_consumidas = max(0.0, (progreso.calorias_consumidas or 0.0) - kcal)
        progreso.proteinas_consumidas = max(0.0, round((progreso.proteinas_consumidas or 0.0) - prot, 1))
        progreso.carbohidratos_consumidos = max(0.0, round((progreso.carbohidratos_consumidos or 0.0) - carb, 1))
        progreso.grasas_consumidas = max(0.0, round((progreso.grasas_consumidas or 0.0) - gras, 1))
        
    # 4. Eliminar el registro
    db.delete(registro)
    db.commit()
    
    return {"success": True, "message": "Comida eliminada exitosamente"}

