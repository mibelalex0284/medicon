from datetime import date, time
from typing import List, Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from app.models.appointment import Appointment, AppointmentStatus
from app.repositories.base import BaseRepository
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate


class AppointmentRepository(
    BaseRepository[Appointment, AppointmentCreate, AppointmentUpdate]
):
    def __init__(self):
        super().__init__(Appointment)

    def find_conflicting_appointments(
        self,
        db: Session,
        *,
        doctor_id: str,
        appointment_date: date,
        start_time: time,
        end_time: time,
        exclude_id: Optional[str] = None,
    ) -> List[Appointment]:
        """Detects overlapping active appointments for the same doctor on the given date.
        
        Overlapping rule: (existing.start < new.end) AND (existing.end > new.start).
        Back-to-back appointments (existing.end == new.start) are permitted.
        """
        query = db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == appointment_date,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED]),
            Appointment.scheduled_start < end_time,
            Appointment.scheduled_end > start_time,
        )
        if exclude_id:
            query = query.filter(Appointment.id != exclude_id)
        return query.all()

    def get_by_doctor_and_date(
        self, db: Session, doctor_id: str, appointment_date: date
    ) -> List[Appointment]:
        return (
            db.query(Appointment)
            .filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == appointment_date,
                Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED]),
            )
            .order_by(Appointment.scheduled_start)
            .all()
        )

    def filter_appointments(
        self,
        db: Session,
        *,
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        hospital_id: Optional[str] = None,
        appointment_date: Optional[date] = None,
        status: Optional[AppointmentStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        from sqlalchemy.orm import joinedload
        from app.models.patient import Patient
        from app.models.doctor import Doctor
        query = (
            db.query(Appointment)
            .options(
                joinedload(Appointment.doctor).joinedload(Doctor.profile),
                joinedload(Appointment.patient).joinedload(Patient.profile),
                joinedload(Appointment.queue_entry),
            )
        )
        if patient_id:
            query = query.filter(Appointment.patient_id == patient_id)
        if doctor_id:
            query = query.filter(Appointment.doctor_id == doctor_id)
        if hospital_id:
            query = query.filter(Appointment.hospital_id == hospital_id)
        if appointment_date:
            query = query.filter(Appointment.appointment_date == appointment_date)
        if status:
            query = query.filter(Appointment.status == status)

        return (
            query.order_by(Appointment.appointment_date.desc(), Appointment.scheduled_start.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )


appointment_repo = AppointmentRepository()
