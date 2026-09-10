import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.doctor import Doctor
    from app.models.specialty import Specialty


class DoctorSpecialty(Base):
    """Associates a doctor with a clinical specialty, supporting multiple specialties per doctor."""

    __tablename__ = "doctor_specialties"
    __table_args__ = (
        UniqueConstraint("doctor_id", "specialty_id", name="uq_doctor_specialty"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    doctor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    specialty_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("specialties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="specialties")
    specialty: Mapped["Specialty"] = relationship(
        "Specialty", back_populates="doctor_specialties"
    )
