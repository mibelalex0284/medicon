import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.doctor import Doctor
    from app.models.doctor_schedule import DoctorSchedule
    from app.models.profile import Profile


class Hospital(Base, TimestampMixin):
    """Represents a healthcare facility / hospital organization."""

    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    departments: Mapped[List["Department"]] = relationship(
        "Department", back_populates="hospital", cascade="all, delete-orphan"
    )
    doctors: Mapped[List["Doctor"]] = relationship(
        "Doctor", back_populates="hospital"
    )
    doctor_schedules: Mapped[List["DoctorSchedule"]] = relationship(
        "DoctorSchedule", back_populates="hospital"
    )
    profiles: Mapped[List["Profile"]] = relationship(
        "Profile", back_populates="hospital"
    )
