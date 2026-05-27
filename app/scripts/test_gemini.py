import asyncio
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv("d:/calofit/calofit_backend_marketing/.env")
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

async def main():
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Test 1: With max_output_tokens = 100
    res1 = await model.generate_content_async(
        "Escribe un parrafo largo",
        generation_config={"max_output_tokens": 100, "temperature": 0.5}
    )
    print("TEST 1 (100 tokens):", repr(res1.text))
    
    # Test 2: Without max_output_tokens
    res2 = await model.generate_content_async(
        "Escribe un parrafo largo",
        generation_config={"temperature": 0.5}
    )
    print("TEST 2 (No limit):", repr(res2.text))

if __name__ == "__main__":
    asyncio.run(main())
