import datetime
import enum
import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.triage_answer import TriageAnswer
    from app.models.triage_assessment import TriageAssessment
    from app.models.triage_message import TriageMessage



class TriageSessionStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    ABANDONED = "ABANDONED"


class TriageSession(Base, TimestampMixin):
    """Represents a structured patient triage interaction."""

    __tablename__ = "triage_sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    patient_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[TriageSessionStatus] = mapped_column(
        Enum(TriageSessionStatus, name="triage_session_status", native_enum=False),
        default=TriageSessionStatus.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    original_input: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient")
    answers: Mapped[List["TriageAnswer"]] = relationship(
        "TriageAnswer", back_populates="triage_session", cascade="all, delete-orphan"
    )
    messages: Mapped[List["TriageMessage"]] = relationship(
        "TriageMessage", back_populates="session", cascade="all, delete-orphan", order_by="TriageMessage.turn_index"
    )
    assessment: Mapped[Optional["TriageAssessment"]] = relationship(
        "TriageAssessment", back_populates="triage_session", uselist=False, cascade="all, delete-orphan"
    )

