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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CaloFit - Gimnasio World Light API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
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