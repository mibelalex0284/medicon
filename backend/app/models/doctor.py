import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.doctor_schedule import DoctorSchedule
    from app.models.doctor_specialty import DoctorSpecialty
    from app.models.hospital import Hospital
    from app.models.profile import Profile


class Doctor(Base, TimestampMixin):
    """Represents a doctor operating within the CareRoute-X system."""

    __tablename__ = "doctors"
    __table_args__ = (
        CheckConstraint("years_of_experience >= 0", name="ck_doctor_years_experience"),
        CheckConstraint("average_rating >= 0.0 AND average_rating <= 5.0", name="ck_doctor_rating_range"),
        CheckConstraint("rating_count >= 0", name="ck_doctor_rating_count"),
    )

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
    hospital_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    license_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    years_of_experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultation_mode: Mapped[str] = mapped_column(
        String(50),
        default="both",
        nullable=False,
        comment="in_person, teleconsultation, or both",
    )
    average_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    languages: Mapped[str] = mapped_column(
        String(255),
        default="en",
        nullable=False,
        comment="Comma-separated language codes, e.g. 'en,es,hi'",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def supported_languages(self) -> List[str]:
        if not self.languages:
            return ["en"]
        return [l.strip().lower() for l in self.languages.split(",") if l.strip()]

    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="doctor_profile")
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="doctors")
    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="doctors"
    )
    specialties: Mapped[List["DoctorSpecialty"]] = relationship(
        "DoctorSpecialty", back_populates="doctor", cascade="all, delete-orphan"
    )
    schedules: Mapped[List["DoctorSchedule"]] = relationship(
        "DoctorSchedule", back_populates="doctor", cascade="all, delete-orphan"
    )
