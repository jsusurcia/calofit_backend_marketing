"""
Rate limiting para endpoints que consumen cupo de Groq.

Límites por usuario autenticado (email extraído del JWT):
  - /asistente/consultar     → 20 req/min   (llama LLM)
  - /asistente/log-inteligente → 20 req/min (llama LLM)

Fallback a IP si el token está ausente o es ilegible.
"""
from __future__ import annotations

from starlette.requests import Request
from slowapi import Limiter

try:
    from jose import jwt as _jwt
    _jose_available = True
except ImportError:
    _jose_available = False


def _key_por_usuario(request: Request) -> str:
    """
    Extrae el email (claim 'sub') del JWT Bearer sin verificar firma.
    Solo necesitamos identidad para el límite; la verificación real
    ya ocurre en get_current_user().
    Fallback a IP si no hay token o no es parseable.
    """
    if _jose_available:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            try:
                payload = _jwt.get_unverified_claims(token)
                sub = payload.get("sub")
                if sub:
                    return sub
            except Exception:
                pass
    # Fallback: IP del cliente
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_key_por_usuario)
