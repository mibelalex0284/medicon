from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import logger


def create_application() -> FastAPI:
    """Creates and configures the FastAPI application."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "CareRoute-X Outpatient Care-Navigation and Queue-Management Platform API. "
            "Exposes server-authoritative queue, appointments, triage safety, and consultation endpoints."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Unified Exception Envelope Handlers
    register_exception_handlers(application)

    # Include API Routers
    application.include_router(api_router, prefix=settings.API_V1_STR)

    @application.get("/", tags=["Root"])
    def root_info():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "operational",
            "docs": "/docs",
            "api_v1": f"{settings.API_V1_STR}/health",
        }

    logger.info(f"{settings.PROJECT_NAME} initialized (env={settings.ENVIRONMENT})")
    return application


app = create_application()
