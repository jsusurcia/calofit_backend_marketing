"""
Servicio LLM centralizado — Gemini primario, Groq fallback.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Gemini ────────────────────────────────────────────────────────────────
try:
    from google import genai                          # ← nuevo SDK
    from google.genai import types as genai_types    # ← para GenerateContentConfig
    _gemini_available = True
except ImportError:
    genai = None
    genai_types = None
    _gemini_available = False

# ── Groq (fallback) ───────────────────────────────────────────────────────
try:
    from groq import AsyncGroq
    _groq_available = True
except ImportError:
    AsyncGroq = None
    _groq_available = False

_GEMINI_MODEL_DEFAULT = "gemini-2.5-flash"
_GROQ_MODEL_DEFAULT   = "llama-3.1-8b-instant"
_DEFAULT_TEMP         = 0.3
_DEFAULT_TOKENS       = 512


class LLMService:
    """
    Wrapper asíncrono. Gemini primario, Groq como fallback automático.

    Uso:
        llm = LLMService()
        texto = await llm.completar("¿Qué comer en el desayuno?")
        data  = await llm.generar_json("Dame 3 ingredientes...")
    """

    def __init__(self) -> None:
        # Gemini
        self._gemini_client = None
        self._gemini_model_name = _GEMINI_MODEL_DEFAULT

        if _gemini_available and getattr(settings, "GEMINI_API_KEY", ""):
            self._gemini_client = genai.Client(
                api_key=settings.GEMINI_API_KEY
            )
            self._gemini_model_name = getattr(settings, "GEMINI_MODEL", _GEMINI_MODEL_DEFAULT)
            logger.info("LLMService: Gemini configurado (%s)", self._gemini_model_name)
        else:
            logger.warning("LLMService: Gemini no disponible — revisar GEMINI_API_KEY o instalar google-genai")

        # Groq (fallback)
        self._groq_client = None
        if _groq_available and getattr(settings, "GROQ_API_KEY", ""):
            self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            logger.info("LLMService: Groq configurado como fallback")

        if not self._gemini_client and not self._groq_client:
            logger.error("LLMService: ningún proveedor LLM disponible. Modo offline.")

    # ──────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────

    async def completar(
        self,
        prompt: str,
        system: str = "",
        temperature: float = _DEFAULT_TEMP,
        max_tokens: int = _DEFAULT_TOKENS,
    ) -> str:
        """Genera texto libre. Gemini primario, Groq fallback."""
        # Combinar system + prompt para Gemini (no tiene rol system separado de la misma forma)
        full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

        if self._gemini_client:
            try:
                response = await self._gemini_client.aio.models.generate_content(
                    model=self._gemini_model_name,
                    contents=full_prompt,
                    config=genai_types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                )
                return response.text.strip()
            except Exception as exc:
                logger.warning("LLMService Gemini error, fallback a Groq: %s", exc)

        return await self._completar_groq(prompt, system=system, temperature=temperature, max_tokens=max_tokens)


    async def generar_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.05,
        max_tokens: int = 600,
    ) -> Optional[Any]:
        """Genera respuesta y la parsea como JSON. None si JSON inválido."""
        system_json = (system + "\nResponde SOLO con JSON válido, sin texto adicional.").strip()
        raw = await self.completar(
            prompt=prompt,
            system=system_json,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._parsear_json(raw)

    async def analizar_intencion(
        self,
        mensaje: str,
        opciones: List[str],
    ) -> str:
        """Clasifica mensaje en una de las opciones. Retorna primera opción si falla."""
        opciones_str = " | ".join(opciones)
        system = (
            f"Clasifica el mensaje del usuario en UNA de estas categorías: {opciones_str}. "
            "Responde SOLO con el nombre exacto de la categoría, sin explicación."
        )
        resultado = await self.completar(
            prompt=mensaje,
            system=system,
            temperature=0.0,
            max_tokens=32,
        )
        resultado = resultado.strip().lower()
        for op in opciones:
            if op.lower() in resultado:
                return op
        return opciones[0]

    def disponible(self) -> bool:
        return bool(self._gemini_client or self._groq_client)

    # ──────────────────────────────────────────────────────────────────────
    # Privados
    # ──────────────────────────────────────────────────────────────────────

    async def _completar_groq(
        self,
        prompt: str,
        system: str = "",
        temperature: float = _DEFAULT_TEMP,
        max_tokens: int = _DEFAULT_TOKENS,
    ) -> str:
        if not self._groq_client:
            return ""
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = await self._groq_client.chat.completions.create(
                model=_GROQ_MODEL_DEFAULT,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error("LLMService Groq error: %s", exc)
            return ""

    @staticmethod
    def _parsear_json(texto: str) -> Optional[Any]:
        bloque = re.search(r"```(?:json)?\s*([\s\S]*?)```", texto)
        candidato = bloque.group(1).strip() if bloque else texto.strip()
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            inicio = candidato.find("{") if "{" in candidato else candidato.find("[")
            if inicio != -1:
                try:
                    return json.loads(candidato[inicio:])
                except json.JSONDecodeError:
                    pass
        logger.warning("LLMService: no se pudo parsear JSON: %.80s", texto)
        return None
