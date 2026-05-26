from fastapi import APIRouter
from .routes import usuarios, nutricion, auth, clientes, asistente, dashboard, admin, balance, alimentos, pagos, chat

api_router = APIRouter()


api_router.include_router(auth.router, prefix="/auth", tags=["Autenticación"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Usuarios"])
api_router.include_router(clientes.router, prefix="/clientes", tags=["Clientes"])
api_router.include_router(nutricion.router, prefix="/nutricion", tags=["Nutrición"])
api_router.include_router(asistente.router, prefix="/asistente", tags=["Asistente Cliente"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administración"])
api_router.include_router(balance.router, prefix="/balance", tags=["Mi Balance"])
api_router.include_router(alimentos.router, prefix="/alimentos", tags=["Detalle de Alimentos"])
api_router.include_router(pagos.router, prefix="/pagos", tags=["Pagos"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])