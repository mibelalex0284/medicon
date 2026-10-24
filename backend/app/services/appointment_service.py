import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.queue_entry import QueueStatus
from app.repositories.appointment_repository import appointment_repo
from app.repositories.doctor_repository import doctor_repo
from app.repositories.doctor_schedule_repository import doctor_schedule_repo
from app.repositories.hospital_repository import hospital_repo
from app.repositories.patient_repository import patient_repo
from app.repositories.queue_repository import queue_repo
from app.schemas.appointment import (
    AppointmentCreate,
    AvailableSlot,
    DoctorAvailabilityResponse,
)


def get_hospital_timezone(hospital: Optional[object]) -> ZoneInfo:
    if hospital and getattr(hospital, "timezone", None):
        try:
            return ZoneInfo(hospital.timezone)
        except Exception:
            pass
    return ZoneInfo("UTC")


class AppointmentService:
    @staticmethod
    def get_appointment(db: Session, appointment_id: str) -> Appointment:
        appt = appointment_repo.get(db, appointment_id)
        if not appt:
            raise NotFoundError(
                message=f"Appointment with id '{appointment_id}' not found",
                code="APPOINTMENT_NOT_FOUND",
            )
        return appt

    @staticmethod
    def list_appointments(
        db: Session,
        *,
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        hospital_id: Optional[str] = None,
        appointment_date: Optional[datetime.date] = None,
        status: Optional[AppointmentStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        return appointment_repo.filter_appointments(
            db,
            patient_id=patient_id,
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            appointment_date=appointment_date,
            status=status,
            skip=skip,
            limit=limit,
        )

    @staticmethod
    def get_doctor_availability(
        db: Session,
        doctor_id: str,
        requested_date: datetime.date,
        slot_duration_minutes: Optional[int] = None,
    ) -> DoctorAvailabilityResponse:
        doctor = doctor_repo.get(db, doctor_id)
        if not doctor:
            raise NotFoundError(
                message=f"Doctor with id '{doctor_id}' not found",
                code="DOCTOR_NOT_FOUND",
            )
        if not doctor.is_active:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                hospital_id=doctor.hospital_id,
                appointment_date=requested_date,
                slot_duration_minutes=slot_duration_minutes or 15,
                has_schedule=False,
                schedule_configured=False,
                is_fully_booked=False,
                slots=[],
            )

        # 1. Check whether doctor has ANY active weekly schedule configured in the system
        all_schedules = doctor_schedule_repo.get_by_doctor(db, doctor_id=doctor_id, is_active=True)
        if not all_schedules:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                hospital_id=doctor.hospital_id,
                appointment_date=requested_date,
                slot_duration_minutes=slot_duration_minutes or 15,
                has_schedule=False,
                schedule_configured=False,
                is_fully_booked=False,
                slots=[],
            )

        hospital = hospital_repo.get(db, doctor.hospital_id) if doctor.hospital_id else None
        hospital_tz = get_hospital_timezone(hospital)
        now_dt = datetime.datetime.now(hospital_tz)
        today_in_hospital = now_dt.date()

        # If requested date is in the past, return empty slots
        if requested_date < today_in_hospital:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                hospital_id=doctor.hospital_id,
                appointment_date=requested_date,
                slot_duration_minutes=slot_duration_minutes or 15,
                has_schedule=False,
                schedule_configured=True,
                is_fully_booked=False,
                slots=[],
            )

        # 0 = Monday ... 6 = Sunday
        weekday = requested_date.weekday()
        schedules = [s for s in all_schedules if s.day_of_week == weekday]

        if not schedules:
            return DoctorAvailabilityResponse(
                doctor_id=doctor_id,
                hospital_id=doctor.hospital_id,
                appointment_date=requested_date,
                slot_duration_minutes=slot_duration_minutes or 15,
                has_schedule=False,
                schedule_configured=True,
                is_fully_booked=False,
                slots=[],
            )

        # Query existing appointments on that date
        existing_appts = appointment_repo.get_by_doctor_and_date(
            db, doctor_id=doctor_id, appointment_date=requested_date
        )

        available_slots: List[AvailableSlot] = []

        duration = slot_duration_minutes or schedules[0].slot_duration_minutes
        for sched in schedules:
            duration = slot_duration_minutes or sched.slot_duration_minutes
            # Generate discrete slots
            current_start = sched.start_time
            while True:
                # Calculate slot end time
                dummy_dt = datetime.datetime.combine(requested_date, current_start)
                slot_end_dt = dummy_dt + datetime.timedelta(minutes=duration)
                slot_end = slot_end_dt.time()

                if slot_end_dt.date() > requested_date or slot_end > sched.end_time:
                    break

                # Exclude past slots if the requested date is today and slot has already started
                slot_start_dt = datetime.datetime.combine(requested_date, current_start, tzinfo=hospital_tz)
                if requested_date == today_in_hospital and slot_start_dt <= now_dt:
                    current_start = slot_end
                    continue

                # Check conflict with existing appointments:
                # appt.scheduled_start < slot_end AND appt.scheduled_end > current_start
                is_booked = any(
                    appt.scheduled_start < slot_end and appt.scheduled_end > current_start
                    for appt in existing_appts
                )

                available_slots.append(
                    AvailableSlot(
                        start_time=current_start,
                        end_time=slot_end,
                        is_available=not is_booked,
                    )
                )

                # Move to next slot
                current_start = slot_end

        is_fully_booked = len(available_slots) > 0 and not any(s.is_available for s in available_slots)
        if len(available_slots) == 0 and requested_date == today_in_hospital:
            is_fully_booked = True

        return DoctorAvailabilityResponse(
            doctor_id=doctor_id,
            hospital_id=doctor.hospital_id,
            appointment_date=requested_date,
            slot_duration_minutes=duration,
            has_schedule=True,
            schedule_configured=True,
            is_fully_booked=is_fully_booked,
            slots=available_slots,
        )

    @staticmethod
    def book_appointment(db: Session, obj_in: AppointmentCreate) -> Appointment:
        # 1. Validate patient exists
        patient = patient_repo.get(db, obj_in.patient_id)
        if not patient:
            raise NotFoundError(
                message=f"Patient with id '{obj_in.patient_id}' not found",
                code="PATIENT_NOT_FOUND",
            )

        # 2. Validate doctor exists (lock doctor row to serialize concurrent booking attempts)
        doctor = (
            db.query(Doctor)
            .filter(Doctor.id == obj_in.doctor_id)
            .with_for_update()
            .first()
        )
        if not doctor:
            raise NotFoundError(
                message=f"Doctor with id '{obj_in.doctor_id}' not found",
                code="DOCTOR_NOT_FOUND",
            )
        if not doctor.is_active:
            raise ConflictError(
                message="Cannot book an appointment with an inactive or deactivated physician.",
                code="DOCTOR_INACTIVE",
            )

        # 3. Validate hospital
        if obj_in.hospital_id != doctor.hospital_id:
            raise ConflictError(
                message="Appointment hospital does not match doctor's registered hospital",
                code="HOSPITAL_MISMATCH",
            )

        # 4. Check time logic
        if obj_in.scheduled_end <= obj_in.scheduled_start:
            raise InvalidStateTransitionError(
                message="scheduled_end must be strictly later than scheduled_start",
                code="INVALID_TIME_RANGE",
            )

        # Timezone-aware validation: cannot book appointments in the past
        hospital = hospital_repo.get(db, obj_in.hospital_id)
        hospital_tz = get_hospital_timezone(hospital)
        now_dt = datetime.datetime.now(hospital_tz)
        appointment_start_dt = datetime.datetime.combine(
            obj_in.appointment_date, obj_in.scheduled_start, tzinfo=hospital_tz
        )
        if appointment_start_dt <= now_dt:
            raise InvalidStateTransitionError(
                message="Cannot book an appointment for a past date or time.",
                code="PAST_APPOINTMENT_NOT_ALLOWED",
            )


        # 5. Validate doctor is scheduled on that day of week
        weekday = obj_in.appointment_date.weekday()
        schedules = doctor_schedule_repo.get_by_doctor_and_day(
            db, doctor_id=obj_in.doctor_id, day_of_week=weekday, is_active=True
        )
        if not schedules:
            raise ConflictError(
                message="Doctor has no active schedule for the requested date",
                code="DOCTOR_UNAVAILABLE",
            )

        # Check if requested slot falls within at least one scheduled window
        slot_covered = any(
            sched.start_time <= obj_in.scheduled_start and sched.end_time >= obj_in.scheduled_end
            for sched in schedules
        )
        if not slot_covered:
            raise ConflictError(
                message="Requested appointment time falls outside doctor's scheduled hours",
                code="OUTSIDE_SCHEDULED_HOURS",
            )

        # 6. Check conflicts with existing appointments
        conflicts = appointment_repo.find_conflicting_appointments(
            db,
            doctor_id=obj_in.doctor_id,
            appointment_date=obj_in.appointment_date,
            start_time=obj_in.scheduled_start,
            end_time=obj_in.scheduled_end,
        )
        if conflicts:
            raise ConflictError(
                message="The requested appointment slot overlaps with an existing booking",
                code="APPOINTMENT_CONFLICT",
            )

        # 7. Create appointment
        return appointment_repo.create(db, obj_in=obj_in)

    @staticmethod
    def cancel_appointment(
        db: Session,
        appointment_id: str,
        *,
        actor_auth_user_id: str,
        is_doctor: bool = False,
        is_admin: bool = False,
    ) -> Appointment:
        appt = AppointmentService.get_appointment(db, appointment_id)

        # Check current status
        if appt.status == AppointmentStatus.CANCELLED:
            raise InvalidStateTransitionError(
                message="Appointment is already cancelled",
                code="ALREADY_CANCELLED",
            )
        if appt.status == AppointmentStatus.COMPLETED:
            raise InvalidStateTransitionError(
                message="Completed appointments cannot be cancelled",
                code="CANNOT_CANCEL_COMPLETED",
            )
        if appt.status == AppointmentStatus.NO_SHOW:
            raise InvalidStateTransitionError(
                message="Appointments marked as no-show cannot be cancelled",
                code="CANNOT_CANCEL_NO_SHOW",
            )

        # Active consultation check
        if appt.queue_entry and appt.queue_entry.status in [
            QueueStatus.IN_CONSULTATION,
            QueueStatus.COMPLETED,
        ]:
            raise InvalidStateTransitionError(
                message="Cannot cancel an appointment that is currently in consultation or completed",
                code="CANNOT_CANCEL_ACTIVE_CONSULTATION",
            )

        # Authorization check: patient can only cancel their own appointment
        if not is_admin and not is_doctor:
            patient = patient_repo.get(db, appt.patient_id)
            if not patient or patient.profile.auth_user_id != actor_auth_user_id:
                raise ForbiddenError(
                    message="Access forbidden: you can only cancel your own appointments",
                    code="FORBIDDEN_CANCELLATION",
                )

        # Update appointment status
        appt.status = AppointmentStatus.CANCELLED

        # If a queue entry exists, mark it cancelled as well
        if appt.queue_entry:
            appt.queue_entry.status = QueueStatus.CANCELLED

        db.add(appt)
        db.commit()
        db.refresh(appt)
        return appt


appointment_service = AppointmentService()
