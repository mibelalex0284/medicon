import datetime
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.profile import Profile


class Patient(Base, TimestampMixin):
    """Represents an outpatient profile within CareRoute-X."""

    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    date_of_birth: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    emergency_contact: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    accessibility_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="patient_profile")
