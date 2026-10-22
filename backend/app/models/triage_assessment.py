import datetime
import enum
import json
import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.specialty import Specialty
    from app.models.triage_session import TriageSession


class TriageUrgency(str, enum.Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class TriageAssessment(Base):
    """Represents the explainable triage output and navigation guidance."""

    __tablename__ = "triage_assessments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    triage_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("triage_sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    urgency: Mapped[TriageUrgency] = mapped_column(
        Enum(TriageUrgency, name="triage_urgency", native_enum=False),
        nullable=False,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    needs_escalation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    red_flag_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    _red_flag_codes: Mapped[str] = mapped_column("red_flag_codes", Text, default="[]", nullable=False)
    recommended_specialty_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("specialties.id", ondelete="SET NULL"),
        nullable=True,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    assessed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    @property
    def red_flag_codes(self) -> List[str]:
        try:
            return json.loads(self._red_flag_codes)
        except Exception:
            return []

    @red_flag_codes.setter
    def red_flag_codes(self, codes: List[str]) -> None:
        self._red_flag_codes = json.dumps(codes)

    @property
    def guidance(self) -> str:
        """Dynamic care navigation guidance string consistent with clinical assessment."""
        dynamic = getattr(self, "_dynamic_guidance", None)
        if dynamic:
            return dynamic
        if self.red_flag_detected:
            return (
                "Emergency warning signs were detected. Seek urgent medical attention "
                "or proceed to the nearest emergency department immediately."
            )
        if self.urgency == TriageUrgency.HIGH:
            return (
                "Based on your responses, prompt outpatient clinical evaluation is recommended. "
                "Please schedule an urgent appointment with the appropriate clinical specialty. "
                "Absence of red-flag symptoms does not guarantee safety; if your condition worsens, seek immediate emergency care."
            )
        if self.needs_escalation or self.confidence < 0.60:
            return (
                "Some clinical presentation factors remain uncertain. "
                "In-person medical evaluation is advised to ensure safe care navigation."
            )
        if self.urgency == TriageUrgency.MODERATE:
            return (
                "Based on your responses, timely outpatient clinical evaluation is recommended. "
                "Please schedule an appointment with the appropriate clinical specialty."
            )
        return (
            "Based on your responses, routine care navigation is recommended. "
            "Please schedule an appointment with the appropriate clinical specialty."
        )

    @guidance.setter
    def guidance(self, value: str) -> None:
        self._dynamic_guidance = value

    @property
    def recommended_specialty_name(self) -> Optional[str]:
        """Name of the recommended clinical specialty, or fallback."""
        dynamic = getattr(self, "_dynamic_specialty_name", None)
        if dynamic:
            return dynamic
        if self.recommended_specialty:
            return self.recommended_specialty.name
        return "General Medicine" if not self.red_flag_detected else None

    @recommended_specialty_name.setter
    def recommended_specialty_name(self, value: Optional[str]) -> None:
        self._dynamic_specialty_name = value

    # Relationships
    triage_session: Mapped["TriageSession"] = relationship(
        "TriageSession", back_populates="assessment"
    )
    recommended_specialty: Mapped[Optional["Specialty"]] = relationship("Specialty")
