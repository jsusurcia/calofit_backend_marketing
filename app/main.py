from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import logging
from app.core.database import engine, Base
from app.core import firebase
from app.core.rate_limit import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

_startup_log = logging.getLogger("calofit.startup")

from app.models import user, client, role, historial
from app.api import api_router
from app.api.routes.websockets import router as websocket_router
import asyncio
from app.scripts.cron_meal_reminder import run_meal_reminders
from datetime import datetime
from zoneinfo import ZoneInfo

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CaloFit - Gimnasio World Light API")

async def meal_reminder_loop():
    """Ejecuta el chequeo de recordatorios al inicio de cada hora"""
    while True:
        try:
            tz_peru = ZoneInfo('America/Lima')
            now = datetime.now(tz_peru)
            # Sleep until the start of the next minute (check every minute to be accurate, but script filters by hour)
            # Para evitar enviar muchas veces en la misma hora, cron_meal_reminder.py tendría que registrar,
            # pero dado que el cron debe ejecutarse una vez por hora, calcularemos el sleep hasta la próxima hora exacta.
            next_hour = now.replace(minute=0, second=0, microsecond=0)
            if next_hour <= now:
                import datetime as dt
                next_hour += dt.timedelta(hours=1)
            
            sleep_seconds = (next_hour - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
            
            # Correr de manera asíncrona pero llamando a la función sincrona en threadpool
            await asyncio.to_thread(run_meal_reminders)
        except Exception as e:
            _startup_log.error(f"Error en meal_reminder_loop: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    # Iniciar la tarea de recordatorios en background
    asyncio.create_task(meal_reminder_loop())

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://calofit-frontend-production.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(websocket_router, tags=["WebSockets"])

# Incluir router general de API v1 (PASO 6)
from app.api.v1 import router as api_v1_router
app.include_router(api_v1_router)

# Crear directorio de subidas si no existe
UPLOAD_DIR = "app/uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Servir archivos estáticos
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/assets", StaticFiles(directory="app/assets"), name="assets")

# ✅ REMOVER REGISTRO DIRECTO - YA ESTÁ EN api_router
# app.include_router(clientes_router, prefix="/clientes", tags=["clientes"])


@app.get("/")
def read_root():
    return {"message": "Asistente CaloFit Operativo en Gimnasio World Light"}


@app.get("/health")
def health_check_root():
    return {"status": "OK", "version": "1.0.0"}


@app.get("/test")
def test_endpoint():
    return {"status": "OK", "birth_date_field": "working"}