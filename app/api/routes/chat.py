import json
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.client import Client
from app.models.nutricion import PlanNutricional, PlanDiario
from app.api.routes.auth import get_current_user
from app.services.ia_service import ia_engine

router = APIRouter()

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    action_taken: str | None = None

@router.post("/mensaje", response_model=ChatResponse)
async def procesar_mensaje_chat(
    data: ChatMessage,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    plan_activo = db.query(PlanNutricional).filter(
        PlanNutricional.client_id == cliente.id
    ).order_by(PlanNutricional.fecha_creacion.desc()).first()

    dias_nombres = {1: "Lunes", 2: "Martes", 3: "Miercoles", 4: "Jueves", 5: "Viernes"}
    nombres_inversos = {v.lower(): k for k, v in dias_nombres.items()}
    nombres_inversos["miércoles"] = 3
    
    plan_context = ""
    if plan_activo:
        dias = db.query(PlanDiario).filter(PlanDiario.plan_id == plan_activo.id).all()
        for d in dias:
            nombre = dias_nombres.get(d.dia_numero, f"Dia {d.dia_numero}")
            plan_context += f"- {nombre}: {d.comidas}\n"

    system_prompt = f"""Eres el Coach Nutricional de CaloFit, un asistente amigable y directo (sin formalismos).
El usuario te hablará, a veces mediante voz (texto dictado) o texto.
Si el usuario te hace preguntas de nutrición o te saluda, responde de forma breve, concisa y amigable (máx 2 párrafos).

PERO, si el usuario te pide CAMBIAR una comida de su menú (ej: "cámbiame el pollo del martes", "no me gusta la avena del desayuno", "dame otra cena para hoy"), DEBES responder ÚNICAMENTE con un objeto JSON (sin texto adicional, sin formato markdown).

ESTRUCTURA DEL JSON:
{{
  "action": "swap",
  "dia": "Lunes|Martes|Miercoles|Jueves|Viernes",
  "tipo_comida": "desayuno|media_manana|almuerzo|cena"
}}
Asegúrate de inferir bien el día y la comida de la que habla. Si dice "hoy", asume que se refiere al día actual (hoy es un día de semana).

PLAN ACTUAL DEL USUARIO:
{plan_context}
"""

    # Llamar a Gemini (usando el cliente interno configurado en ia_service)
    try:
        from app.core.utils import get_peru_now
        dia_actual = get_peru_now().isoweekday()
        hoy_str = dias_nombres.get(dia_actual, "Lunes")
        
        prompt_final = system_prompt + f"\nHoy es: {hoy_str}\nMensaje del usuario: {data.message}\nRespuesta:"
        raw_response = await ia_engine._llamar_llm(prompt_final, max_tokens=300, temp=0.2)
        
        # Intentar detectar si devolvió JSON de acción
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            try:
                json_data = json.loads(match.group())
                if json_data.get("action") == "swap":
                    dia_str = json_data.get("dia", "").lower()
                    tipo = json_data.get("tipo_comida", "").lower()
                    
                    dia_num = nombres_inversos.get(dia_str)
                    if dia_num and plan_activo:
                        # Buscar el dia en la base de datos
                        dia_db = db.query(PlanDiario).filter(
                            PlanDiario.plan_id == plan_activo.id,
                            PlanDiario.dia_numero == dia_num
                        ).first()
                        
                        if dia_db and dia_db.comidas and tipo in dia_db.comidas:
                            comida_actual = dia_db.comidas[tipo]
                            # Ejecutar swap usando la funcion que ya existe
                            perfil = {"goal": plan_activo.objetivo}
                            swap_res = await ia_engine.generar_swap_comida(comida_actual, tipo, perfil)
                            nueva_comida = swap_res.get("nueva_comida")
                            
                            if nueva_comida:
                                # Actualizar DB
                                comidas_dict = dict(dia_db.comidas)
                                comidas_dict[tipo] = nueva_comida
                                dia_db.comidas = comidas_dict
                                db.commit()
                                
                                return ChatResponse(
                                    reply=f"¡Listo! He cambiado tu {tipo} del {dia_str.capitalize()} por: {nueva_comida}.",
                                    action_taken="swap"
                                )
            except json.JSONDecodeError:
                pass
                
        # Si no fue una acción, devolver el texto tal cual
        return ChatResponse(reply=raw_response.strip(), action_taken=None)

    except Exception as e:
        print(f"Error en chat: {e}")
        return ChatResponse(reply="Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?")
