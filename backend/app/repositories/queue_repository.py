from datetime import date
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.queue_entry import QueueEntry, QueueStatus
from app.repositories.base import BaseRepository
from app.schemas.queue_entry import QueueEntryCreate


class QueueRepository(BaseRepository[QueueEntry, QueueEntryCreate, QueueEntryCreate]):
    def __init__(self):
        super().__init__(QueueEntry)

    def get_by_appointment_id(
        self, db: Session, appointment_id: str
    ) -> Optional[QueueEntry]:
        return (
            db.query(QueueEntry)
            .filter(QueueEntry.appointment_id == appointment_id)
            .first()
        )

    def get_active_patient_entry(
        self, db: Session, patient_id: str
    ) -> Optional[QueueEntry]:
        """Finds the patient's current non-completed, non-cancelled queue entry."""
        return (
            db.query(QueueEntry)
            .filter(
                QueueEntry.patient_id == patient_id,
                QueueEntry.status.in_(
                    [
                        QueueStatus.CHECKED_IN,
                        QueueStatus.WAITING,
                        QueueStatus.CALLED,
                        QueueStatus.IN_CONSULTATION,
                    ]
                ),
            )
            .order_by(QueueEntry.checked_in_at.desc())
            .first()
        )

    def get_active_queue_for_doctor(
        self, db: Session, doctor_id: str, queue_date: date
    ) -> List[QueueEntry]:
        """Retrieves active queue entries for a doctor on a specific date, deterministically ordered.
        
        Ordering hierarchy:
        1. CALLED (patient is actively called into doctor's room)
        2. IN_CONSULTATION
        3. WAITING / CHECKED_IN (ordered by checked_in_at ASC, token_number ASC)
        """
        return (
            db.query(QueueEntry)
            .filter(
                QueueEntry.doctor_id == doctor_id,
                QueueEntry.queue_date == queue_date,
                QueueEntry.status.in_(
                    [
                        QueueStatus.CALLED,
                        QueueStatus.IN_CONSULTATION,
                        QueueStatus.WAITING,
                        QueueStatus.CHECKED_IN,
                    ]
                ),
            )
            .order_by(
                QueueEntry.checked_in_at.asc(),
                QueueEntry.token_number.asc(),
            )
            .all()
        )

    def generate_token_number(
        self, db: Session, hospital_id: str, doctor_id: str, queue_date: date
    ) -> str:
        """Generates the next sequential token number for this doctor and date (e.g. A01, A02...)."""
        count = (
            db.query(func.count(QueueEntry.id))
            .filter(
                QueueEntry.hospital_id == hospital_id,
                QueueEntry.doctor_id == doctor_id,
                QueueEntry.queue_date == queue_date,
            )
            .scalar()
            or 0
        )
        seq = count + 1
        return f"A{seq:02d}"

    def count_patients_ahead(
        self, db: Session, doctor_id: str, queue_date: date, entry: QueueEntry
    ) -> int:
        """Counts how many active patients are ahead of this entry in the waiting line."""
        if entry.status in [QueueStatus.IN_CONSULTATION, QueueStatus.COMPLETED]:
            return 0

        # Count patients who are WAITING or CALLED and checked in earlier
        count = (
            db.query(func.count(QueueEntry.id))
            .filter(
                QueueEntry.doctor_id == doctor_id,
                QueueEntry.queue_date == queue_date,
                QueueEntry.status.in_([QueueStatus.WAITING, QueueStatus.CALLED]),
                QueueEntry.checked_in_at < entry.checked_in_at,
                QueueEntry.id != entry.id,
            )
            .scalar()
            or 0
        )
        return count


queue_repo = QueueRepository()
