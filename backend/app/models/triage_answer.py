import datetime
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.triage_question import TriageQuestion
    from app.models.triage_session import TriageSession


class TriageAnswer(Base):
    """Represents a patient's recorded response to a controlled triage question."""

    __tablename__ = "triage_answers"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    triage_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("triage_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("triage_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_value: Mapped[str] = mapped_column(Text, nullable=False)
    answered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Relationships
    triage_session: Mapped["TriageSession"] = relationship(
        "TriageSession", back_populates="answers"
    )
    question: Mapped["TriageQuestion"] = relationship("TriageQuestion")
