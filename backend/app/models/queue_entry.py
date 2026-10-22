import datetime
import enum
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.consultation import Consultation
    from app.models.doctor import Doctor
    from app.models.hospital import Hospital
    from app.models.patient import Patient


class QueueStatus(str, enum.Enum):
    CHECKED_IN = "CHECKED_IN"
    WAITING = "WAITING"
    CALLED = "CALLED"
    IN_CONSULTATION = "IN_CONSULTATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class QueueEntry(Base, TimestampMixin):
    """Represents a patient's position in the live operational queue."""

    __tablename__ = "queue_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
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
    queue_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    token_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[QueueStatus] = mapped_column(
        Enum(QueueStatus, name="queue_status", native_enum=False),
        default=QueueStatus.WAITING,
        nullable=False,
        index=True,
    )
    checked_in_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    called_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consultation_started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    appointment: Mapped["Appointment"] = relationship(
        "Appointment", back_populates="queue_entry"
    )
    patient: Mapped["Patient"] = relationship("Patient")
    doctor: Mapped["Doctor"] = relationship("Doctor")
    hospital: Mapped["Hospital"] = relationship("Hospital")
    consultation: Mapped[Optional["Consultation"]] = relationship(
        "Consultation", back_populates="queue_entry", uselist=False
    )

    @property
    def patient_name(self) -> Optional[str]:
        if self.patient and self.patient.profile:
            return self.patient.profile.full_name
        return None

    @property
    def patient_gender(self) -> Optional[str]:
        if self.patient:
            return self.patient.gender
        return None

    @property
    def patient_age(self) -> Optional[int]:
        if self.patient and self.patient.date_of_birth:
            today = datetime.date.today()
            dob = self.patient.date_of_birth
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return None

    @property
    def doctor_name(self) -> Optional[str]:
        if self.doctor and self.doctor.profile:
            return self.doctor.profile.full_name
        return None

    @property
    def room_number(self) -> Optional[str]:
        if self.doctor:
            return getattr(self.doctor, "room_number", None)
        return None

    @property
    def department_name(self) -> Optional[str]:
        if self.doctor and self.doctor.department:
            return self.doctor.department.name
        elif self.hospital:
            return self.hospital.name
        return None

    @property
    def chief_complaint(self) -> Optional[str]:
        if self.appointment and self.appointment.reason:
            return self.appointment.reason
        return None
