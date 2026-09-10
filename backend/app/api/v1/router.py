from fastapi import APIRouter
from app.api.v1 import (
    appointments,
    departments,
    doctors,
    health,
    hospitals,
    patients,
    queues,
    specialties,
    triage,
)

api_router = APIRouter()

# Health & System
api_router.include_router(health.router)

# Domain Routers
api_router.include_router(hospitals.router, prefix="/hospitals", tags=["Hospitals"])
api_router.include_router(departments.router, prefix="/departments", tags=["Departments"])
api_router.include_router(specialties.router, prefix="/specialties", tags=["Specialties"])
api_router.include_router(doctors.router, prefix="/doctors", tags=["Doctors"])
api_router.include_router(patients.router, prefix="/patients", tags=["Patients"])

# Operational Routers
api_router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
api_router.include_router(queues.router, prefix="/queues", tags=["Queues"])

# Triage & Safety Router
api_router.include_router(triage.router, prefix="/triage", tags=["Triage"])

# Future Routers (Stage 5+):
# api_router.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
