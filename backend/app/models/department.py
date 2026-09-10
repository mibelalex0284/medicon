import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.doctor import Doctor
    from app.models.hospital import Hospital


class Department(Base, TimestampMixin):
    """Represents an organizational department within a hospital."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("hospital_id", "code", name="uq_department_hospital_code"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    hospital_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="departments")
    doctors: Mapped[List["Doctor"]] = relationship("Doctor", back_populates="department")
