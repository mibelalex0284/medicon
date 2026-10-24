from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import logger
from app.services.llm import get_llm_provider, close_llm_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application Startup: Initialize application-lifetime LLM provider / connection pool
    logger.info("Initializing CareRoute-X application resources...")
    settings.validate_production_configuration()
    try:
        get_llm_provider()
    except Exception as exc:
        logger.warning(f"Could not eagerly initialize Gemini client at startup: {exc}")
    yield
    # Application Shutdown: Cleanly release HTTP connection pools and client resources
    logger.info("Closing CareRoute-X application resources...")
    close_llm_provider()


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
        lifespan=lifespan,
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
