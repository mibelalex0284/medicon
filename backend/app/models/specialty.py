import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.doctor_specialty import DoctorSpecialty


class Specialty(Base, TimestampMixin):
    """Represents a clinical specialty (e.g., General Medicine, Cardiology, Dermatology)."""

    __tablename__ = "specialties"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    doctor_specialties: Mapped[List["DoctorSpecialty"]] = relationship(
        "DoctorSpecialty", back_populates="specialty", cascade="all, delete-orphan"
    )
