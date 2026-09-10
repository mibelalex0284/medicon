from datetime import datetime, timezone
from typing import Dict, Literal
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings
from app.db.session import check_database_health

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    environment: str
    database: Literal["connected", "disconnected"]
    timestamp: datetime


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Readiness Check",
    description="Returns the operational status of the CareRoute-X backend and database connectivity.",
)
def get_health() -> HealthResponse:
    db_connected = check_database_health()
    status = "healthy" if db_connected else "degraded"

    return HealthResponse(
        status=status,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database="connected" if db_connected else "disconnected",
        timestamp=datetime.now(timezone.utc),
    )
