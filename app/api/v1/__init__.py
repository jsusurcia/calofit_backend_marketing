"""
API v1 - Endpoints principales.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["v1"])

from app.api.v1.nutrition import plates, progress, parser, templates
from app.api.v1 import health

router.include_router(plates.router)
router.include_router(progress.router)
router.include_router(parser.router, prefix="/nutrition")
router.include_router(templates.router)
router.include_router(health.router)

__all__ = ["router"]
