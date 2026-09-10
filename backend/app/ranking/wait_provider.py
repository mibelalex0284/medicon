from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.ranking.interfaces import WaitEstimationProvider
from app.repositories.queue_repository import queue_repo


class BaselineWaitEstimationProvider(WaitEstimationProvider):
    """Deterministic baseline wait estimation provider reusing Stage 3 queue logic.
    
    Calculates operational wait time based on the doctor's active waiting queue:
    expected_wait_minutes = max(5, active_patients_ahead * 15)
    
    This clean interface allows Stage 7 to plug in an ML-based wait prediction model
    without modifying the recommendation API contract.
    """

    DEFAULT_CONSULTATION_MINUTES: int = 15
    MINIMUM_OPERATIONAL_WAIT_MINUTES: int = 5

    def get_estimated_wait_minutes(
        self, db: Session, doctor_id: str, target_date: Optional[date] = None
    ) -> int:
        query_date = target_date or datetime.now(timezone.utc).date()
        active_entries = queue_repo.get_active_queue_for_doctor(db, doctor_id, query_date)
        patients_ahead = len(active_entries)

        return max(
            self.MINIMUM_OPERATIONAL_WAIT_MINUTES,
            patients_ahead * self.DEFAULT_CONSULTATION_MINUTES,
        )


baseline_wait_provider = BaselineWaitEstimationProvider()
