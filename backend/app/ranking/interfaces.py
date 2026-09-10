from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.doctor import Doctor
from app.schemas.doctor_recommendation import (
    DoctorRecommendationItem,
    DoctorRecommendationRequest,
)


class WaitEstimationProvider(ABC):
    """Abstract interface for doctor waiting time estimation.
    
    In Stage 6, implemented by BaselineWaitEstimationProvider (reusing Stage 3 queue counts).
    In Stage 7, can be extended to LearnedWaitEstimationProvider (ML-based duration/wait prediction).
    """

    @abstractmethod
    def get_estimated_wait_minutes(
        self, db: Session, doctor_id: str, target_date: Optional[date] = None
    ) -> int:
        """Returns the estimated waiting time in minutes for a doctor on a given date."""
        pass


class DoctorRankingProvider(ABC):
    """Abstract provider interface for ranking and recommending eligible doctors.
    
    Decouples the recommendation API and service from the underlying ranking implementation.
    Allows substituting deterministic operational ranking with a learned ranking model in the future.
    """

    @abstractmethod
    def rank_doctors(
        self,
        db: Session,
        eligible_doctors: List[Doctor],
        target_specialty_id: str,
        request: DoctorRecommendationRequest,
        wait_provider: WaitEstimationProvider,
    ) -> List[DoctorRecommendationItem]:
        """Ranks eligible doctors, computes normalized factor scores, and generates structured explanations."""
        pass
