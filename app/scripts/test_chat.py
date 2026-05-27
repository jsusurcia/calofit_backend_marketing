import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.ia_service import ia_engine

async def main():
    prompt = """Eres el Coach Nutricional de CaloFit, un asistente amigable y directo (sin formalismos).
El usuario te hablará, a veces mediante voz (texto dictado) o texto.
Si el usuario te hace preguntas de nutrición o te saluda, responde de forma breve, concisa y amigable (máx 2 párrafos).

PERO, si el usuario te pide CAMBIAR una comida de su menú (ej: "cámbiame el pollo del martes", "no me gusta la avena del desayuno", "dame otra cena para hoy"), DEBES responder ÚNICAMENTE con un objeto JSON (sin texto adicional, sin formato markdown).

ESTRUCTURA DEL JSON:
{
  "action": "swap",
  "dia": "Lunes|Martes|Miercoles|Jueves|Viernes|Sabado|Domingo",
  "tipo_comida": "desayuno|media_manana|almuerzo|cena"
}
Asegúrate de inferir bien el día y la comida de la que habla. Si dice "hoy", asume que se refiere al día actual (hoy es un día de semana).

PLAN ACTUAL DEL USUARIO:
- Lunes: {'desayuno': 'Avena', 'almuerzo': 'Pollo'}

Hoy es: Lunes
Mensaje del usuario: hola calo, modifica mi plan para mañana
Respuesta:"""

    res = await ia_engine._llamar_llm(prompt, max_tokens=300, temp=0.2)
    print("RESPONSE:")
    print(repr(res))

if __name__ == "__main__":
    asyncio.run(main())
