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


async def _registrar_comidas_del_dia(mensaje: str, cliente, db: Session) -> ChatResponse:
    """Extrae macros del mensaje y registra en ProgresoCalorias + PreferenciaAlimento."""
    from app.models.historial import ProgresoCalorias
    from app.models.preferencias import PreferenciaAlimento
    from app.core.utils import get_peru_date
    from datetime import datetime

    peso_kg = float(cliente.weight or 70.0)

    prompt = (
        "Eres nutricionista. El usuario describe lo que comió hoy en un solo mensaje. "
        "Extrae TODOS los alimentos/platos mencionados y estima sus macros (porciones típicas peruanas). "
        "Responde SOLO JSON válido:\n"
        '{"alimentos": [{"nombre": "string", "calorias": 0, "proteinas_g": 0, "carbohidratos_g": 0, "grasas_g": 0}], '
        '"totales": {"calorias": 0, "proteinas_g": 0, "carbohidratos_g": 0, "grasas_g": 0}}\n\n'
        f"Mensaje: \"{mensaje[:800]}\""
    )
    raw = await ia_engine._llamar_llm(prompt, max_tokens=600, temp=0.1, json_mode=True)

    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(m.group() if m else raw)
    except Exception:
        return None

    alimentos = parsed.get("alimentos", [])
    totales = parsed.get("totales", {})
    if not alimentos or not totales.get("calorias"):
        return None

    cal   = round(float(totales.get("calorias", 0)), 1)
    prot  = round(float(totales.get("proteinas_g", 0)), 1)
    carb  = round(float(totales.get("carbohidratos_g", 0)), 1)
    gras  = round(float(totales.get("grasas_g", 0)), 1)

    hoy = get_peru_date()

    # Actualizar o crear ProgresoCalorias
    progreso = db.query(ProgresoCalorias).filter(
        ProgresoCalorias.client_id == cliente.id,
        ProgresoCalorias.fecha == hoy
    ).first()
    if progreso:
        progreso.calorias_consumidas = round((progreso.calorias_consumidas or 0) + cal)
        progreso.proteinas_consumidas = round((progreso.proteinas_consumidas or 0.0) + prot, 1)
        progreso.carbohidratos_consumidos = round((progreso.carbohidratos_consumidos or 0.0) + carb, 1)
        progreso.grasas_consumidas = round((progreso.grasas_consumidas or 0.0) + gras, 1)
    else:
        progreso = ProgresoCalorias(
            client_id=cliente.id,
            fecha=hoy,
            calorias_consumidas=round(cal),
            calorias_quemadas=0,
            proteinas_consumidas=prot,
            carbohidratos_consumidos=carb,
            grasas_consumidas=gras,
        )
        db.add(progreso)

    # Crear PreferenciaAlimento por cada ítem (para que aparezca en /balance/hoy)
    ahora = datetime.utcnow()
    for item in alimentos:
        nombre = str(item.get("nombre", "")).strip().lower()
        if not nombre:
            continue
        existente = db.query(PreferenciaAlimento).filter(
            PreferenciaAlimento.client_id == cliente.id,
            PreferenciaAlimento.alimento == nombre
        ).first()
        if existente:
            existente.frecuencia = (existente.frecuencia or 0) + 1
            existente.calorias = round(float(item.get("calorias", 0)), 1)
            existente.proteinas = round(float(item.get("proteinas_g", 0)), 1)
            existente.carbohidratos = round(float(item.get("carbohidratos_g", 0)), 1)
            existente.grasas = round(float(item.get("grasas_g", 0)), 1)
            existente.ultima_vez = ahora
        else:
            db.add(PreferenciaAlimento(
                client_id=cliente.id,
                alimento=nombre,
                frecuencia=1,
                puntuacion=1.0,
                calorias=round(float(item.get("calorias", 0)), 1),
                proteinas=round(float(item.get("proteinas_g", 0)), 1),
                carbohidratos=round(float(item.get("carbohidratos_g", 0)), 1),
                grasas=round(float(item.get("grasas_g", 0)), 1),
                ultima_vez=ahora,
            ))

    db.commit()

    nombres = ", ".join(a.get("nombre", "") for a in alimentos if a.get("nombre"))
    reply = (
        f"Registrado ✅ Anoté lo que comiste hoy:\n{nombres}\n\n"
        f"Total: {round(cal)} kcal | P: {prot}g | C: {carb}g | G: {gras}g"
    )
    return ChatResponse(reply=reply, action_taken="registrar")


@router.post("/mensaje", response_model=ChatResponse)
async def procesar_mensaje_chat(
    data: ChatMessage,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Detectar intención de registro de comida ANTES de Gemini
    try:
        modo = await ia_engine.clasificar_modo_asistente(data.message)
        if modo == "registrar_nutricion":
            resultado = await _registrar_comidas_del_dia(data.message, cliente, db)
            if resultado:
                return resultado
    except Exception as e:
        print(f"[Chat] Error en clasificación/registro: {e}")

    plan_activo = db.query(PlanNutricional).filter(
        PlanNutricional.client_id == cliente.id
    ).order_by(PlanNutricional.fecha_creacion.desc()).first()

    dias_nombres = {1: "Lunes", 2: "Martes", 3: "Miercoles", 4: "Jueves", 5: "Viernes", 6: "Sabado", 7: "Domingo"}
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

REGLA DE CAMBIO DE MENÚ (SWAP):
Si el usuario pide CAMBIAR una comida de su menú (ej: "cámbiame el pollo del martes", "dame otra cena para hoy"):
1. Verifica si tienes la información del DÍA y el TIPO DE COMIDA (desayuno, media_manana, almuerzo, cena).
2. Si FALTA el día o la comida, responde con TEXTO NORMAL preguntando qué día o qué comida quiere cambiar.
3. Si TIENES ambos datos, responde ÚNICA Y EXCLUSIVAMENTE con el siguiente objeto JSON (sin markdown, sin texto antes ni después):

{{
  "action": "swap",
  "dia": "Lunes|Martes|Miercoles|Jueves|Viernes|Sabado|Domingo",
  "tipo_comida": "desayuno|media_manana|almuerzo|cena"
}}

IMPORTANTE: El campo "dia" DEBE ser uno de los 7 días de la semana. Si el usuario dice "hoy" o "mañana", debes inferir el día correcto de la semana (ej. si hoy es Lunes y dice mañana, el dia es "Martes").

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
        
        # Intentar extraer JSON de manera más segura
        match = re.search(r"\{[\s\S]*\}", raw_response)
        if match:
            try:
                json_str = match.group()
                # Eliminar backticks si quedaron dentro del match
                json_str = re.sub(r"```json|```", "", json_str).strip()
                json_data = json.loads(json_str)
                
                if json_data.get("action") == "swap":
                    dia_str = json_data.get("dia", "").lower()
                    tipo = json_data.get("tipo_comida", "").lower()
                    
                    dia_num = nombres_inversos.get(dia_str)
                    if dia_num and plan_activo:
                        dia_db = db.query(PlanDiario).filter(
                            PlanDiario.plan_id == plan_activo.id,
                            PlanDiario.dia_numero == dia_num
                        ).first()
                        
                        if dia_db and dia_db.comidas and tipo in dia_db.comidas:
                            comida_actual = dia_db.comidas[tipo]
                            perfil = {"goal": plan_activo.objetivo}
                            swap_res = await ia_engine.generar_swap_comida(comida_actual, tipo, perfil)
                            nueva_comida = swap_res.get("nueva_comida")
                            
                            if nueva_comida:
                                comidas_dict = dict(dia_db.comidas)
                                comidas_dict[tipo] = nueva_comida
                                dia_db.comidas = comidas_dict
                                db.commit()
                                
                                return ChatResponse(
                                    reply=f"¡Listo! He cambiado tu {tipo.replace('_', ' ')} del {dia_str.capitalize()} por: {nueva_comida}.",
                                    action_taken="swap"
                                )
                        return ChatResponse(reply=f"No pude encontrar el {tipo.replace('_', ' ')} en tu plan del {dia_str.capitalize()}.", action_taken=None)
                    else:
                        return ChatResponse(reply=f"Lo siento, no pude procesar el día '{dia_str}'.", action_taken=None)
            except json.JSONDecodeError:
                pass
                
        # Si no hubo JSON de acción válida, devolver el texto limpio
        texto_limpio = re.sub(r"```(?:json)?\s*[\s\S]*?```", "", raw_response).strip()
        if not texto_limpio:
            texto_limpio = raw_response.strip()
        
        return ChatResponse(reply=texto_limpio, action_taken=None)

    except Exception as e:
        print(f"Error en chat: {e}")
        return ChatResponse(reply="Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?")
