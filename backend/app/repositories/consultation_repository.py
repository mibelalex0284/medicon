from typing import Optional
from sqlalchemy.orm import Session
from app.models.consultation import Consultation, ConsultationStatus
from app.repositories.base import BaseRepository
from app.schemas.consultation import ConsultationCreate


class ConsultationRepository(
    BaseRepository[Consultation, ConsultationCreate, ConsultationCreate]
):
    def __init__(self):
        super().__init__(Consultation)

    def get_by_queue_entry_id(
        self, db: Session, queue_entry_id: str
    ) -> Optional[Consultation]:
        return (
            db.query(Consultation)
            .filter(Consultation.queue_entry_id == queue_entry_id)
            .first()
        )

    def get_by_appointment_id(
        self, db: Session, appointment_id: str
    ) -> Optional[Consultation]:
        return (
            db.query(Consultation)
            .filter(Consultation.appointment_id == appointment_id)
            .first()
        )

    def get_active_by_doctor(
        self, db: Session, doctor_id: str
    ) -> Optional[Consultation]:
        return (
            db.query(Consultation)
            .filter(
                Consultation.doctor_id == doctor_id,
                Consultation.status == ConsultationStatus.IN_PROGRESS,
            )
            .first()
        )


consultation_repo = ConsultationRepository()
