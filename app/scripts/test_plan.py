import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.ia_service import ia_engine

async def main():
    perfil = {
        "age": 25,
        "gender": "M",
        "goal": "Mantener peso",
        "activity_level": "Moderado"
    }
    res = await ia_engine._llamar_llm("Di hola en JSON: {\"hola\":\"mundo\"}", max_tokens=100)
    print("RAW:", repr(res))
    
    # Try plan
    res_plan = await ia_engine.generar_plan_semanal_porciones(perfil)
    print("RESULT PLAN:")
    print(res_plan)
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
