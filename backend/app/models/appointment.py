import datetime
import enum
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Date, Enum, ForeignKey, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.consultation import Consultation
    from app.models.doctor import Doctor
    from app.models.hospital import Hospital
    from app.models.patient import Patient
    from app.models.queue_entry import QueueEntry


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class Appointment(Base, TimestampMixin):
    """Represents a scheduled outpatient appointment."""

    __tablename__ = "appointments"

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
    appointment_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    scheduled_start: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    scheduled_end: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    appointment_type: Mapped[str] = mapped_column(String(50), default="in_person", nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", native_enum=False),
        default=AppointmentStatus.BOOKED,
        nullable=False,
        index=True,
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient")
    doctor: Mapped["Doctor"] = relationship("Doctor")
    hospital: Mapped["Hospital"] = relationship("Hospital")
    queue_entry: Mapped[Optional["QueueEntry"]] = relationship(
        "QueueEntry", back_populates="appointment", uselist=False, cascade="all, delete-orphan"
    )
    consultation: Mapped[Optional["Consultation"]] = relationship(
        "Consultation", back_populates="appointment", uselist=False
    )

    @property
    def doctor_name(self) -> Optional[str]:
        if self.doctor and self.doctor.profile:
            return self.doctor.profile.full_name
        return None

    @property
    def doctor_specialty(self) -> Optional[str]:
        if self.doctor and self.doctor.specialties:
            primary = next((ds for ds in self.doctor.specialties if ds.is_primary), None)
            if not primary and len(self.doctor.specialties) > 0:
                primary = self.doctor.specialties[0]
            if primary and primary.specialty:
                return primary.specialty.name
        return None

    @property
    def department_name(self) -> Optional[str]:
        if self.doctor and self.doctor.department:
            return self.doctor.department.name
        return None

    @property
    def queue_token(self) -> Optional[str]:
        if self.queue_entry:
            return self.queue_entry.token_number
        return None

    @property
    def patient_name(self) -> Optional[str]:
        if self.patient and self.patient.profile:
            return self.patient.profile.full_name
        return None

    @property
    def queue_entry_id(self) -> Optional[str]:
        if self.queue_entry:
            return self.queue_entry.id
        return None

