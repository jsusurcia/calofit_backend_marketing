import json
import re
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.client import Client
from app.models.nutricion import PlanNutricional, PlanDiario
from app.models.chat_message import ChatMessage as ChatMessageDB
from app.api.routes.auth import get_current_user
from app.services.ia_service import ia_engine

router = APIRouter()

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    action_taken: str | None = None
    # Solo con action_taken="swap_propuesta": {dia, dia_numero, tipo_comida, plato}
    propuesta: dict | None = None

class ChatHistorialItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

class ChatHistorialResponse(BaseModel):
    mensajes: List[ChatHistorialItem]
    hay_mas: bool


def _guardar_mensaje(db: Session, client_id: int, role: str, content: str) -> None:
    """Persiste un mensaje del hilo continuo de chat del cliente."""
    db.add(ChatMessageDB(client_id=client_id, role=role, content=content))
    db.commit()


async def _registrar_comida_por_chat(mensaje: str, db: Session, current_user) -> ChatResponse | None:
    """
    Registra la comida con el mismo flujo que POST /asistente/log-inteligente: una fila por alimento en
    comida_registros (con su momento: se infiere del texto o de la hora de Perú), progreso del día y
    preferencias. Devuelve None si el mensaje no se pudo tratar como registro, para que siga el chat normal.
    """
    from app.services.asistente_service import asistente_service

    res = await asistente_service.registrar_por_nlp(mensaje, db, current_user)
    if not isinstance(res, dict):
        return None

    tipo = res.get("tipo_detectado")
    datos = res.get("datos") or {}

    if res.get("success") and tipo == "comida" and datos.get("calorias"):
        nombres = [str(n).strip() for n in (res.get("alimentos") or []) if str(n).strip()]
        lista = ", ".join(n[:1].upper() + n[1:] for n in nombres) or "Tu comida"
        reply = (
            f"Registrado ✅ Anoté lo que comiste hoy:\n{lista}\n\n"
            f"Total: {round(float(datos.get('calorias', 0)))} kcal | "
            f"P: {round(float(datos.get('proteinas_g', 0)), 1)}g | "
            f"C: {round(float(datos.get('carbohidratos_g', 0)), 1)}g | "
            f"G: {round(float(datos.get('grasas_g', 0)), 1)}g"
        )
        avisos = [res.get(k) for k in ("advertencia_prohibido", "advertencia_gula", "advertencia_gramaje") if res.get(k)]
        if avisos:
            reply += "\n\n" + "\n".join(avisos)
        return ChatResponse(reply=reply, action_taken="registrar")

    # Respuestas informativas del registro (duplicado, "no comí nada", ingrediente ficticio, corrección)
    informativa = (
        tipo in ("ficcion_bloqueada", "ingrediente_desconocido", "correccion_requerida")
        or (res.get("success") and (tipo == "ninguno" or (tipo == "comida" and not datos)))
    )
    if informativa and res.get("mensaje"):
        return ChatResponse(reply=res["mensaje"])
    return None


@router.post("/mensaje", response_model=ChatResponse)
async def procesar_mensaje_chat(
    data: ChatMessage,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    _guardar_mensaje(db, cliente.id, "user", data.message)

    # Detectar intención de registro de comida ANTES de Gemini
    try:
        modo = await ia_engine.clasificar_modo_asistente(data.message)
        if modo == "registrar_nutricion":
            resultado = await _registrar_comida_por_chat(data.message, db, current_user)
            if resultado:
                _guardar_mensaje(db, cliente.id, "assistant", resultado.reply)
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
                            
                            if nueva_comida and str(nueva_comida).strip() != str(comida_actual).strip():
                                respuesta = ChatResponse(
                                    reply=f"¡Claro! Te propongo para tu {_nombre_comida(tipo)} del {dia_str.capitalize()}:",
                                    action_taken="swap_propuesta",
                                    propuesta={
                                        "dia": dia_str.capitalize(),
                                        "dia_numero": dia_num,
                                        "tipo_comida": tipo,
                                        "plato": str(nueva_comida).strip(),
                                    },
                                )
                                _guardar_mensaje(db, cliente.id, "assistant", f"{respuesta.reply}\n{nueva_comida}")
                                return respuesta
                            respuesta = ChatResponse(reply="No encontré una alternativa distinta por ahora. Intenta de nuevo en un momento.", action_taken=None)
                            _guardar_mensaje(db, cliente.id, "assistant", respuesta.reply)
                            return respuesta
                        respuesta = ChatResponse(reply=f"No pude encontrar el {tipo.replace('_', ' ')} en tu plan del {dia_str.capitalize()}.", action_taken=None)
                        _guardar_mensaje(db, cliente.id, "assistant", respuesta.reply)
                        return respuesta
                    else:
                        respuesta = ChatResponse(reply=f"Lo siento, no pude procesar el día '{dia_str}'.", action_taken=None)
                        _guardar_mensaje(db, cliente.id, "assistant", respuesta.reply)
                        return respuesta
            except json.JSONDecodeError:
                pass

        # Si no hubo JSON de acción válida, devolver el texto limpio
        texto_limpio = re.sub(r"```(?:json)?\s*[\s\S]*?```", "", raw_response).strip()
        if not texto_limpio:
            texto_limpio = raw_response.strip()

        _guardar_mensaje(db, cliente.id, "assistant", texto_limpio)
        return ChatResponse(reply=texto_limpio, action_taken=None)

    except Exception as e:
        print(f"Error en chat: {e}")
        mensaje_error = "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentar de nuevo?"
        _guardar_mensaje(db, cliente.id, "assistant", mensaje_error)
        return ChatResponse(reply=mensaje_error)


# ── Cambio de comida con confirmación ────────────────────────────────────────

_DIAS_NOMBRES = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo"}
_TIPOS_COMIDA = {"desayuno", "media_manana", "almuerzo", "cena"}


def _nombre_comida(tipo: str) -> str:
    return "snack" if tipo == "media_manana" else tipo


class SwapConfirmarRequest(BaseModel):
    dia_numero: int
    tipo_comida: str
    nueva_comida: str
    texto_usuario: str | None = None


class SwapOtraRequest(BaseModel):
    dia_numero: int
    tipo_comida: str
    plato_anterior: str | None = None
    texto_usuario: str | None = None


def _plan_y_dia(db: Session, cliente, dia_numero: int, tipo_comida: str):
    """Plan más reciente del cliente y el día pedido; valida que exista esa comida."""
    if tipo_comida not in _TIPOS_COMIDA:
        raise HTTPException(status_code=400, detail="Tipo de comida no válido")
    plan = db.query(PlanNutricional).filter(
        PlanNutricional.client_id == cliente.id
    ).order_by(PlanNutricional.fecha_creacion.desc()).first()
    if not plan:
        raise HTTPException(status_code=404, detail="El cliente no tiene un plan")
    dia = db.query(PlanDiario).filter(
        PlanDiario.plan_id == plan.id, PlanDiario.dia_numero == dia_numero
    ).first()
    if not dia or not dia.comidas or tipo_comida not in dia.comidas:
        raise HTTPException(status_code=404, detail="No se encontró esa comida en tu plan")
    return plan, dia


@router.post("/swap/confirmar", response_model=ChatResponse)
async def confirmar_swap(
    data: SwapConfirmarRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Aplica al plan una comida propuesta previamente y deja el intercambio en el historial del chat."""
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    nueva = (data.nueva_comida or "").strip()[:500]
    if not nueva:
        raise HTTPException(status_code=400, detail="Falta la comida a aplicar")
    _, dia = _plan_y_dia(db, cliente, data.dia_numero, data.tipo_comida)

    _guardar_mensaje(db, cliente.id, "user", (data.texto_usuario or "Sí, cámbiala")[:500])

    comidas = dict(dia.comidas)
    comidas[data.tipo_comida] = nueva
    dia.comidas = comidas
    db.commit()

    reply = (
        f"¡Listo! Cambié tu {_nombre_comida(data.tipo_comida)} del "
        f"{_DIAS_NOMBRES.get(data.dia_numero, 'día')} por: {nueva}."
    )
    _guardar_mensaje(db, cliente.id, "assistant", reply)
    return ChatResponse(reply=reply, action_taken="swap")


@router.post("/swap/otra", response_model=ChatResponse)
async def otra_opcion_swap(
    data: SwapOtraRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Genera otra alternativa para la misma comida (sin aplicarla) y la deja en el historial."""
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    plan, dia = _plan_y_dia(db, cliente, data.dia_numero, data.tipo_comida)
    _guardar_mensaje(db, cliente.id, "user", (data.texto_usuario or "Otra opción")[:500])

    base = (data.plato_anterior or "").strip() or str(dia.comidas[data.tipo_comida])
    resultado = await ia_engine.generar_swap_comida(base, data.tipo_comida, {"goal": plan.objetivo})
    nueva = (resultado.get("nueva_comida") or "").strip()

    if not nueva or nueva == base:
        reply = "No encontré otra alternativa por ahora. Puedes intentarlo de nuevo en un momento."
        _guardar_mensaje(db, cliente.id, "assistant", reply)
        return ChatResponse(reply=reply)

    nombre_dia = _DIAS_NOMBRES.get(data.dia_numero, "día")
    reply = f"Otra opción para tu {_nombre_comida(data.tipo_comida)} del {nombre_dia}:"
    _guardar_mensaje(db, cliente.id, "assistant", f"{reply}\n{nueva}")
    return ChatResponse(
        reply=reply,
        action_taken="swap_propuesta",
        propuesta={
            "dia": nombre_dia,
            "dia_numero": data.dia_numero,
            "tipo_comida": data.tipo_comida,
            "plato": nueva,
        },
    )


@router.get("/historial", response_model=ChatHistorialResponse)
async def obtener_historial_chat(
    before_id: int | None = None,
    limite: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Historial paginado del hilo continuo de chat (cursor-based).

    - Sin `before_id`: devuelve los `limite` mensajes más recientes.
    - Con `before_id`: devuelve los `limite` mensajes anteriores a ese ID
      (para "cargar más" al scrollear hacia arriba).

    Siempre se devuelve en orden cronológico ascendente (viejo -> nuevo).
    """
    cliente = db.query(Client).filter(Client.email == current_user.email).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    limite = max(1, min(limite, 100))

    query = db.query(ChatMessageDB).filter(ChatMessageDB.client_id == cliente.id)
    if before_id is not None:
        query = query.filter(ChatMessageDB.id < before_id)

    # Pedimos uno de más para saber si queda historial anterior sin cargar
    filas = query.order_by(ChatMessageDB.id.desc()).limit(limite + 1).all()

    hay_mas = len(filas) > limite
    filas = filas[:limite]
    filas.reverse()

    return ChatHistorialResponse(
        mensajes=[
            ChatHistorialItem(id=f.id, role=f.role, content=f.content, created_at=f.created_at)
            for f in filas
        ],
        hay_mas=hay_mas,
    )
