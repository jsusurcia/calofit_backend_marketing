from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.nutricion import PlanNutricional, PlanDiario
from app.schemas.nutricion import PlanNutricionalCreate, PlanNutricionalResponse
from typing import List, Optional, Any, Dict
from datetime import datetime

from app.api.routes.auth import get_current_staff, get_current_user
from app.services.ia_service import ia_engine

router = APIRouter()

@router.get("/plan-actual")
async def obtener_plan_actual(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from app.models.client import Client
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    plan = db.query(PlanNutricional).filter(
        PlanNutricional.client_id == cliente.id
    ).order_by(PlanNutricional.fecha_creacion.desc()).first()
    
    if not plan:
        return {"plan_id": None, "dias": []}
        
    dias = db.query(PlanDiario).filter(PlanDiario.plan_id == plan.id).order_by(PlanDiario.dia_numero).all()
    
    return {
        "plan_id": plan.id,
        "objetivo": plan.objetivo,
        "dias": [
            {
                "dia_numero": d.dia_numero,
                "comidas": d.comidas
            }
            for d in dias
        ]
    }

@router.post("/", response_model=PlanNutricionalResponse)
async def crear_plan_nutricional(
    plan_data: PlanNutricionalCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_staff)
):

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

    # 3. Guardar Plan Maestro (Encabezado)
    nuevo_plan = PlanNutricional(
        client_id=plan_data.client_id,
        nutricionista_id=None,
        genero=plan_data.genero, edad=plan_data.edad,
        peso=plan_data.peso, talla=plan_data.talla,
        nivel_actividad=plan_data.nivel_actividad,
        objetivo=plan_data.objetivo,
        calorias_ia_base=calorias_base,
        es_contingencia_ia=False,
        observaciones=plan_data.observaciones,
        status="aprobado_ia",
    )

    try:
        db.add(nuevo_plan)
        db.flush() 

        # 4. Generación Semanal Inteligente (Porciones)
        # Generamos de Lunes a Domingo (días 1 a 7)
        dias_nombres = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        
        # Generar JSON de la IA
        perfil_usuario = {
            "age": plan_data.edad,
            "gender": "M" if plan_data.genero == 1 else "F",
            "goal": plan_data.objetivo,
            "activity_level": plan_data.nivel_actividad,
        }
        
        plan_semanal_json = await ia_engine.generar_plan_semanal_porciones(perfil_usuario)
        
        for i, nombre_dia in enumerate(dias_nombres, 1):
            cals_dia = round(calorias_base * 1.1, 2) # factor genérico
            
            # Obtener comidas del día desde la respuesta de IA, o vacío si falló
            comidas_del_dia = plan_semanal_json.get(nombre_dia, {})

            dia = PlanDiario(
                plan_id=nuevo_plan.id,
                dia_numero=i,
                calorias_dia=cals_dia,
                proteinas_g=round((cals_dia * 0.25) / 4, 1),
                carbohidratos_g=round((cals_dia * 0.50) / 4, 1),
                grasas_g=round((cals_dia * 0.25) / 9, 1),
                comidas=comidas_del_dia, # ← NUEVO CAMPO MVP
                nota_asistente_ia="Plan por porciones generado automáticamente.",
                estado="sugerencia_ia",
                validado_nutri=True
            )
            db.add(dia)

        db.commit()
        db.refresh(nuevo_plan)
        
        return nuevo_plan

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")

# --- NUEVOS ENDPOINTS MVP GIMNASIOS ---

@router.post("/generar-plan-automatico")
async def generar_plan_automatico_endpoint(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from app.models.client import Client
    from datetime import date
    
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    # Verificar si ya tiene un plan
    plan_activo = db.query(PlanNutricional).filter(
        PlanNutricional.client_id == cliente.id
    ).first()
    
    if plan_activo:
        raise HTTPException(status_code=400, detail="El cliente ya tiene un plan")
        
    edad = (date.today() - cliente.birth_date).days // 365 if cliente.birth_date else 25
    
    perfil_usuario = {
        "age": edad,
        "gender": cliente.gender or "M",
        "goal": cliente.goal or "Mantener peso",
        "activity_level": cliente.activity_level or "Moderado",
    }
    
    # Generar con IA
    plan_semanal_json = await ia_engine.generar_plan_semanal_porciones(perfil_usuario)
    if not plan_semanal_json:
        raise HTTPException(status_code=500, detail="Error al generar plan con IA")
        
    plan_maestro = PlanNutricional(
        client_id=cliente.id,
        genero=1 if cliente.gender == "M" else 2,
        edad=edad,
        peso=cliente.weight or 0,
        talla=cliente.height or 0,
        nivel_actividad=1.55,
        objetivo=cliente.goal or "Mantener peso",
        es_contingencia_ia=False,
        calorias_ia_base=2000,
        status="draft_ia"
    )
    db.add(plan_maestro)
    db.flush()
    
    dias_nombres = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    for i, nombre_dia in enumerate(dias_nombres, 1):
        comidas_del_dia = plan_semanal_json.get(nombre_dia, {})
        plan_dia = PlanDiario(
            plan_id=plan_maestro.id,
            dia_numero=i,
            calorias_dia=2000,
            proteinas_g=100,
            carbohidratos_g=200,
            grasas_g=60,
            comidas=comidas_del_dia,
            sugerencia_entrenamiento_ia="Entrenamiento sugerido por IA",
            nota_asistente_ia="Plan generado automáticamente",
            validado_nutri=False,
            estado="sugerencia_ia"
        )
        db.add(plan_dia)
        
    db.commit()
    return {"success": True, "message": "Plan generado exitosamente"}


from pydantic import BaseModel
class SwapRequest(BaseModel):
    tipo_comida: str # 'desayuno', 'almuerzo', etc
    comida_actual: str

@router.post("/{plan_id}/dia/{dia_numero}/swap")
async def swap_comida(
    plan_id: int,
    dia_numero: int,
    body: SwapRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reemplaza una comida específica por una alternativa generada por IA."""
    dia = db.query(PlanDiario).filter(PlanDiario.plan_id == plan_id, PlanDiario.dia_numero == dia_numero).first()
    if not dia or not dia.comidas:
        raise HTTPException(status_code=404, detail="Día o menú no encontrado")
        
    plan = db.query(PlanNutricional).filter(PlanNutricional.id == plan_id).first()
    perfil_usuario = {"goal": plan.objetivo}
    
    # Generar alternativa
    respuesta_ia = await ia_engine.generar_swap_comida(body.comida_actual, body.tipo_comida, perfil_usuario)
    nueva_comida = respuesta_ia.get("nueva_comida", "Error generando alternativa")
    
    # Actualizar DB
    comidas_dict = dict(dia.comidas)
    comidas_dict[body.tipo_comida] = nueva_comida
    dia.comidas = comidas_dict
    db.commit()
    
    return {"success": True, "nueva_comida": nueva_comida, "dia_comidas": dia.comidas}

@router.get("/{plan_id}/compras")
async def generar_compras(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Genera la lista de compras basada en el menú semanal."""
    dias = db.query(PlanDiario).filter(PlanDiario.plan_id == plan_id).all()
    if not dias:
        raise HTTPException(status_code=404, detail="No hay días en este plan")
        
    # Construir el JSON consolidado del menú
    menu_completo = {}
    nombres_dias = {1: "Lunes", 2: "Martes", 3: "Miercoles", 4: "Jueves", 5: "Viernes", 6: "Sabado", 7: "Domingo"}
    
    for d in dias:
        if d.comidas:
            nombre = nombres_dias.get(d.dia_numero, f"Dia_{d.dia_numero}")
            menu_completo[nombre] = d.comidas
            
    lista_json = await ia_engine.generar_lista_compras(menu_completo)
    return lista_json



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

