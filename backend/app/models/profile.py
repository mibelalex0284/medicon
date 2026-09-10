import enum
import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.doctor import Doctor
    from app.models.hospital import Hospital
    from app.models.patient import Patient


class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"


class Profile(Base, TimestampMixin):
    """Represents the application profile linked to a Supabase auth identity."""

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    auth_user_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.PATIENT,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hospital_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("hospitals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    hospital: Mapped[Optional["Hospital"]] = relationship(
        "Hospital", back_populates="profiles"
    )
    patient_profile: Mapped[Optional["Patient"]] = relationship(
        "Patient", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    doctor_profile: Mapped[Optional["Doctor"]] = relationship(
        "Doctor", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
