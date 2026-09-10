from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.doctor_schedule import DoctorSchedule
from app.repositories.base import BaseRepository
from app.schemas.doctor_schedule import DoctorScheduleCreate, DoctorScheduleUpdate


class DoctorScheduleRepository(
    BaseRepository[DoctorSchedule, DoctorScheduleCreate, DoctorScheduleUpdate]
):
    def __init__(self):
        super().__init__(DoctorSchedule)

    def get_by_doctor(
        self, db: Session, doctor_id: str, is_active: bool = True
    ) -> List[DoctorSchedule]:
        return (
            db.query(DoctorSchedule)
            .filter(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.is_active == is_active,
            )
            .order_by(DoctorSchedule.day_of_week, DoctorSchedule.start_time)
            .all()
        )

    def get_by_doctor_and_day(
        self, db: Session, doctor_id: str, day_of_week: int, is_active: bool = True
    ) -> List[DoctorSchedule]:
        return (
            db.query(DoctorSchedule)
            .filter(
                DoctorSchedule.doctor_id == doctor_id,
                DoctorSchedule.day_of_week == day_of_week,
                DoctorSchedule.is_active == is_active,
            )
            .order_by(DoctorSchedule.start_time)
            .all()
        )


doctor_schedule_repo = DoctorScheduleRepository()
