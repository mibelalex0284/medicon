import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

PATIENT_SELF_REGISTRATION_KEY = "patient_self_registration"


class SystemSettingService:
    """Service for managing persisted system-wide configurations and toggles."""

    def get_setting(
        self,
        db: Session,
        key: str,
        default: Optional[str] = None,
    ) -> Optional[str]:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            return setting.value
        return default

    def set_setting(
        self,
        db: Session,
        key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> SystemSetting:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            setting.value = value
            if description is not None:
                setting.description = description
            if updated_by is not None:
                setting.updated_by = updated_by
        else:
            setting = SystemSetting(
                key=key,
                value=value,
                description=description,
                updated_by=updated_by,
            )
            db.add(setting)

        db.commit()
        db.refresh(setting)
        logger.info(f"System setting '{key}' updated to '{value}' by {updated_by}")
        return setting

    def is_patient_self_registration_enabled(self, db: Session) -> bool:
        """Determines if public patient self-registration is allowed.
        
        Defaults to True if no record is yet persisted in the database.
        """
        val = self.get_setting(db, PATIENT_SELF_REGISTRATION_KEY, default="true")
        if val is None:
            return True
        return val.strip().lower() in ("true", "1", "yes", "enabled")

    def set_patient_self_registration(
        self,
        db: Session,
        enabled: bool,
        updated_by: Optional[str] = None,
    ) -> bool:
        self.set_setting(
            db=db,
            key=PATIENT_SELF_REGISTRATION_KEY,
            value="true" if enabled else "false",
            description="Controls whether new patients can publicly register accounts",
            updated_by=updated_by,
        )
        return enabled


system_setting_service = SystemSettingService()
