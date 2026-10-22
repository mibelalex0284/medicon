import datetime
import enum
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.doctor import Doctor
    from app.models.hospital import Hospital
    from app.models.patient import Patient
    from app.models.queue_entry import QueueEntry


class ConsultationStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Consultation(Base, TimestampMixin):
    """Represents an active or completed clinical encounter."""

    __tablename__ = "consultations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    queue_entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("queue_entries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    patient_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hospital_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[ConsultationStatus] = mapped_column(
        Enum(ConsultationStatus, name="consultation_status", native_enum=False),
        default=ConsultationStatus.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    queue_entry: Mapped["QueueEntry"] = relationship(
        "QueueEntry", back_populates="consultation"
    )
    appointment: Mapped["Appointment"] = relationship(
        "Appointment", back_populates="consultation"
    )
    patient: Mapped["Patient"] = relationship("Patient")
    doctor: Mapped["Doctor"] = relationship("Doctor")
    hospital: Mapped["Hospital"] = relationship("Hospital")

    @property
    def patient_name(self) -> Optional[str]:
        if self.patient and self.patient.profile:
            return self.patient.profile.full_name
        return None

    @property
    def doctor_name(self) -> Optional[str]:
        if self.doctor and self.doctor.profile:
            return self.doctor.profile.full_name
        return None

    @property
    def token_number(self) -> Optional[str]:
        if self.queue_entry:
            return self.queue_entry.token_number
        return None

    @property
    def chief_complaint(self) -> Optional[str]:
        if self.appointment and self.appointment.reason:
            return self.appointment.reason
        return None
