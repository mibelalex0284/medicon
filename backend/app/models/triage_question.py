import enum
import uuid
from sqlalchemy import Boolean, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class QuestionResponseType(str, enum.Enum):
    YES_NO = "YES_NO"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    NUMBER = "NUMBER"
    TEXT = "TEXT"
    DURATION = "DURATION"


class TriageQuestion(Base, TimestampMixin):
    """Represents an approved, controlled question from the clinical question bank."""

    __tablename__ = "triage_questions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[QuestionResponseType] = mapped_column(
        Enum(QuestionResponseType, name="question_response_type", native_enum=False),
        default=QuestionResponseType.YES_NO,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), default="GENERAL", index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
