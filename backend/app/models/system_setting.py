from typing import Optional
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class SystemSetting(Base, TimestampMixin):
    """Stores system-wide configuration flags and administrative toggles."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        index=True,
        nullable=False,
        comment="Unique identifier for configuration setting",
    )
    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="String-serialized value of the setting",
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable description of this setting",
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
        comment="Profile ID of the administrator who last updated this setting",
    )
