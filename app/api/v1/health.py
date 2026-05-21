"""
Health check endpoints.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.api.dependencies import get_db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", name="Health Check")
async def health_check(db: Session = Depends(get_db)):
    """Verifica API y BD."""
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error("Health check DB error: %s", e)

    status = "OK" if db_ok else "ERROR"
    code   = 200 if db_ok else 503

    return JSONResponse(status_code=code, content={
        "status":    status,
        "timestamp": datetime.utcnow().isoformat(),
        "version":   "1.0.0",
        "db":        "Connected" if db_ok else "Disconnected",
    })
