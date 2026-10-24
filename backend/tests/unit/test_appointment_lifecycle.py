import datetime
import pytest
from sqlalchemy.orm import Session
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.models.appointment import AppointmentStatus
from app.models.profile import UserRole
from app.models.queue_entry import QueueStatus
from app.schemas.appointment import AppointmentCreate
from app.schemas.doctor import DoctorCreate
from app.schemas.doctor_schedule import DoctorScheduleCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.appointment_service import appointment_service
from app.services.consultation_service import consultation_service
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.queue_service import queue_service


@pytest.fixture
def setup_clinic_data(db_session: Session):
    """Sets up a hospital, doctor with schedule, and two patients."""
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Central Clinic", code="CC-01")
    )

    # Doctor
    doc_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-uuid-1",
            role=UserRole.DOCTOR,
            full_name="Dr. Gregory House",
            email="drhouse@clinic.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-GH-01",
        ),
    )

    # Schedule: every day of the week 09:00 to 12:00, 30 min slots
    for day in range(7):
        doctor_service.add_schedule(
            db_session,
            doctor_id=doc.id,
            obj_in=DoctorScheduleCreate(
                doctor_id=doc.id,
                hospital_id=hosp.id,
                day_of_week=day,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(12, 0),
                slot_duration_minutes=30,
            ),
        )

    # Patient 1
    p1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-auth-1",
            role=UserRole.PATIENT,
            full_name="John Doe",
            email="john@example.com",
        ),
    )
    pat1 = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=p1_prof.id,
            date_of_birth=datetime.date(1990, 1, 1),
        ),
    )

    # Patient 2
    p2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-auth-2",
            role=UserRole.PATIENT,
            full_name="Jane Smith",
            email="jane@example.com",
        ),
    )
    pat2 = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=p2_prof.id,
            date_of_birth=datetime.date(1992, 2, 2),
        ),
    )

    return {
        "hospital": hosp,
        "doctor": doc,
        "patient1": pat1,
        "patient2": pat2,
    }


def test_doctor_availability_slot_generation(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=7)

    avail = appointment_service.get_doctor_availability(
        db_session, doctor_id=doc.id, requested_date=test_date, slot_duration_minutes=30
    )
    assert len(avail.slots) == 6  # 09:00 to 12:00 at 30 min intervals = 6 slots
    assert all(s.is_available for s in avail.slots)

    # Book 09:00 - 09:30
    appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=setup_clinic_data["patient1"].id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(9, 0),
            scheduled_end=datetime.time(9, 30),
        ),
    )

    # Check availability again: 09:00 slot must now be unavailable
    avail_after = appointment_service.get_doctor_availability(
        db_session, doctor_id=doc.id, requested_date=test_date, slot_duration_minutes=30
    )
    assert avail_after.slots[0].is_available is False
    assert avail_after.slots[1].is_available is True


def test_overlapping_booking_conflict_rejected(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    p2 = setup_clinic_data["patient2"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=8)

    # Book 10:00 - 10:30
    appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(10, 0),
            scheduled_end=datetime.time(10, 30),
        ),
    )

    # Overlapping 10:15 - 10:45 must be rejected with ConflictError
    with pytest.raises(ConflictError) as exc_info:
        appointment_service.book_appointment(
            db_session,
            AppointmentCreate(
                patient_id=p2.id,
                doctor_id=doc.id,
                hospital_id=doc.hospital_id,
                appointment_date=test_date,
                scheduled_start=datetime.time(10, 15),
                scheduled_end=datetime.time(10, 45),
            ),
        )
    assert exc_info.value.code == "APPOINTMENT_CONFLICT"


def test_back_to_back_booking_permitted(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    p2 = setup_clinic_data["patient2"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=9)

    # 10:00 - 10:30
    appt1 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(10, 0),
            scheduled_end=datetime.time(10, 30),
        ),
    )
    # 10:30 - 11:00 (back-to-back: starts exactly when appt1 ends)
    appt2 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(10, 30),
            scheduled_end=datetime.time(11, 0),
        ),
    )
    assert appt1.id is not None
    assert appt2.id is not None


def test_appointment_cancellation_and_invalid_cancellation(
    db_session: Session, setup_clinic_data: dict
):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=10)

    appt = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(11, 0),
            scheduled_end=datetime.time(11, 30),
        ),
    )

    # Cancel successfully
    cancelled = appointment_service.cancel_appointment(
        db_session, appt.id, actor_auth_user_id="pat-auth-1"
    )
    assert cancelled.status == AppointmentStatus.CANCELLED

    # Re-cancelling raises InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        appointment_service.cancel_appointment(
            db_session, appt.id, actor_auth_user_id="pat-auth-1"
        )
    assert exc_info.value.code == "ALREADY_CANCELLED"


def test_check_in_rules_and_token_generation(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    p2 = setup_clinic_data["patient2"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1)

    # Appointment 1 for patient 1
    appt1 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(9, 0),
            scheduled_end=datetime.time(9, 30),
        ),
    )
    # Appointment 2 for patient 2
    appt2 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(9, 30),
            scheduled_end=datetime.time(10, 0),
        ),
    )

    # Check in patient 1
    q1 = queue_service.check_in(db_session, appt1.id, actor_auth_user_id="pat-auth-1")
    assert q1.token_number == "A01"
    assert q1.status == QueueStatus.WAITING

    # Check in patient 2
    q2 = queue_service.check_in(db_session, appt2.id, actor_auth_user_id="pat-auth-2")
    assert q2.token_number == "A02"
    assert q2.status == QueueStatus.WAITING

    # Duplicate check in raises ConflictError
    with pytest.raises(ConflictError) as exc_info:
        queue_service.check_in(db_session, appt1.id, actor_auth_user_id="pat-auth-1")
    assert exc_info.value.code == "ALREADY_CHECKED_IN"


def test_queue_and_consultation_state_machine_enforcement(
    db_session: Session, setup_clinic_data: dict
):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1)

    appt = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(10, 0),
            scheduled_end=datetime.time(10, 30),
        ),
    )
    q_entry = queue_service.check_in(db_session, appt.id, actor_auth_user_id="pat-auth-1")

    # 1. Invalid start: cannot complete before starting
    with pytest.raises(InvalidStateTransitionError):
        consultation_service.complete_consultation(
            db_session, q_entry.id, doctor_id=doc.id
        )

    # 2. Call patient: WAITING -> CALLED
    called_entry = queue_service.call_patient(db_session, q_entry.id, doctor_id=doc.id)
    assert called_entry.status == QueueStatus.CALLED
    assert called_entry.called_at is not None

    # 3. Start consultation: CALLED -> IN_CONSULTATION
    consultation = consultation_service.start_consultation(
        db_session, q_entry.id, doctor_id=doc.id
    )
    assert consultation.status.value == "IN_PROGRESS"
    assert q_entry.status == QueueStatus.IN_CONSULTATION

    # 4. Complete consultation: IN_CONSULTATION -> COMPLETED
    completed = consultation_service.complete_consultation(
        db_session, q_entry.id, doctor_id=doc.id
    )
    assert completed.status.value == "COMPLETED"
    assert completed.duration_seconds is not None
    assert q_entry.status == QueueStatus.COMPLETED
    assert appt.status == AppointmentStatus.COMPLETED

    # 5. Cannot complete again
    with pytest.raises(InvalidStateTransitionError):
        consultation_service.complete_consultation(
            db_session, q_entry.id, doctor_id=doc.id
        )


def test_queue_ordering_and_patients_ahead_calculation(
    db_session: Session, setup_clinic_data: dict
):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    p2 = setup_clinic_data["patient2"]
    test_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1)

    # Create and check in p1, then p2
    appt1 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(9, 0),
            scheduled_end=datetime.time(9, 30),
        ),
    )
    appt2 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=test_date,
            scheduled_start=datetime.time(9, 30),
            scheduled_end=datetime.time(10, 0),
        ),
    )

    queue_service.check_in(db_session, appt1.id, actor_auth_user_id="pat-auth-1")
    queue_service.check_in(db_session, appt2.id, actor_auth_user_id="pat-auth-2")

    # Patient 1 has 0 patients ahead
    status_p1 = queue_service.get_patient_queue_status(db_session, p1.id)
    assert status_p1.patients_ahead == 0
    assert status_p1.token_number == "A01"

    # Patient 2 has 1 patient ahead (Patient 1)
    status_p2 = queue_service.get_patient_queue_status(db_session, p2.id)
    assert status_p2.patients_ahead == 1
    assert status_p2.token_number == "A02"
    assert status_p2.wait_estimate.expected_minutes >= 15


# ---------------------------------------------------------------------------
# REGRESSION TESTS: Issue 2 (Past Slots & Timezone Boundaries)
# ---------------------------------------------------------------------------

def test_past_appointment_date_rejected(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    past_date = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1)

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        appointment_service.book_appointment(
            db_session,
            AppointmentCreate(
                patient_id=p1.id,
                doctor_id=doc.id,
                hospital_id=doc.hospital_id,
                appointment_date=past_date,
                scheduled_start=datetime.time(9, 0),
                scheduled_end=datetime.time(9, 30),
            ),
        )
    assert exc_info.value.code == "PAST_APPOINTMENT_NOT_ALLOWED"


def test_today_past_time_appointment_rejected(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    today = datetime.datetime.now(datetime.timezone.utc).date()

    # Slot from 00:00 to 00:30 UTC on today is definitely in the past if now > 00:30
    now_time = datetime.datetime.now(datetime.timezone.utc).time()
    if now_time.hour > 0:
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            appointment_service.book_appointment(
                db_session,
                AppointmentCreate(
                    patient_id=p1.id,
                    doctor_id=doc.id,
                    hospital_id=doc.hospital_id,
                    appointment_date=today,
                    scheduled_start=datetime.time(0, 0),
                    scheduled_end=datetime.time(0, 30),
                ),
            )
        assert exc_info.value.code == "PAST_APPOINTMENT_NOT_ALLOWED"


def test_past_slots_excluded_from_doctor_availability(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    past_date = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=2)

    avail = appointment_service.get_doctor_availability(
        db_session, doctor_id=doc.id, requested_date=past_date
    )
    # Exclude past slots: requesting a past date must yield zero available slots
    assert len(avail.slots) == 0


def test_doctor_availability_timezone_boundary(db_session: Session, setup_clinic_data: dict):
    doc = setup_clinic_data["doctor"]
    hospital = setup_clinic_data["hospital"]
    # Change hospital timezone to Asia/Kolkata (+5:30)
    hospital.timezone = "Asia/Kolkata"
    db_session.add(hospital)
    db_session.commit()

    # A date strictly in the future for Kolkata
    future_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=5)
    avail = appointment_service.get_doctor_availability(
        db_session, doctor_id=doc.id, requested_date=future_date, slot_duration_minutes=30
    )
    assert len(avail.slots) == 6
    assert all(s.is_available for s in avail.slots)
    assert avail.has_schedule is True
    assert avail.schedule_configured is True
    assert avail.is_fully_booked is False


def test_doctor_with_no_configured_schedule(db_session: Session, setup_clinic_data: dict):
    hosp = setup_clinic_data["hospital"]
    doc_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-unscheduled-uuid",
            role=UserRole.DOCTOR,
            full_name="Dr. Unscheduled",
            email="drunscheduled@clinic.org",
            hospital_id=hosp.id,
        ),
    )
    unscheduled_doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-UNSCHED-01",
        ),
    )

    future_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=3)
    avail = appointment_service.get_doctor_availability(
        db_session, doctor_id=unscheduled_doc.id, requested_date=future_date
    )
    assert avail.slots == []
    assert avail.has_schedule is False
    assert avail.schedule_configured is False
    assert avail.is_fully_booked is False

    p1 = setup_clinic_data["patient1"]
    with pytest.raises(ConflictError) as exc_info:
        appointment_service.book_appointment(
            db_session,
            AppointmentCreate(
                patient_id=p1.id,
                doctor_id=unscheduled_doc.id,
                hospital_id=hosp.id,
                appointment_date=future_date,
                scheduled_start=datetime.time(9, 0),
                scheduled_end=datetime.time(9, 30),
            ),
        )
    assert exc_info.value.code == "DOCTOR_UNAVAILABLE"


def test_fully_booked_date_availability_and_release_on_cancellation(
    db_session: Session, setup_clinic_data: dict
):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    p2 = setup_clinic_data["patient2"]
    future_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=4)

    # Doctor schedule has 6 half-hour slots: 09:00 to 12:00
    # Book all 6 slots
    booked_appts = []
    for hour in (9, 10, 11):
        for minute in (0, 30):
            start_t = datetime.time(hour, minute)
            end_t = (
                datetime.time(hour, 30) if minute == 0 else datetime.time(hour + 1, 0)
            )
            appt = appointment_service.book_appointment(
                db_session,
                AppointmentCreate(
                    patient_id=p1.id,
                    doctor_id=doc.id,
                    hospital_id=doc.hospital_id,
                    appointment_date=future_date,
                    scheduled_start=start_t,
                    scheduled_end=end_t,
                ),
            )
            booked_appts.append(appt)

    # Availability must show is_fully_booked = True
    avail = appointment_service.get_doctor_availability(
        db_session, doctor_id=doc.id, requested_date=future_date, slot_duration_minutes=30
    )
    assert avail.has_schedule is True
    assert avail.schedule_configured is True
    assert avail.is_fully_booked is True
    assert len(avail.slots) == 6
    assert all(not s.is_available for s in avail.slots)

    # Attempting to book any slot on the fully booked date must fail
    with pytest.raises(ConflictError) as exc_info:
        appointment_service.book_appointment(
            db_session,
            AppointmentCreate(
                patient_id=p2.id,
                doctor_id=doc.id,
                hospital_id=doc.hospital_id,
                appointment_date=future_date,
                scheduled_start=datetime.time(9, 0),
                scheduled_end=datetime.time(9, 30),
            ),
        )
    assert exc_info.value.code == "APPOINTMENT_CONFLICT"

    # Cancel the first appointment (09:00 - 09:30)
    cancelled = appointment_service.cancel_appointment(
        db_session,
        booked_appts[0].id,
        actor_auth_user_id=p1.profile.auth_user_id,
    )
    assert cancelled.status == AppointmentStatus.CANCELLED

    # Check that the 09:00 - 09:30 slot is released immediately
    avail_after = appointment_service.get_doctor_availability(
        db_session, doctor_id=doc.id, requested_date=future_date, slot_duration_minutes=30
    )
    assert avail_after.is_fully_booked is False
    slot_900 = next(s for s in avail_after.slots if s.start_time == datetime.time(9, 0))
    assert slot_900.is_available is True

    # Patient 2 can now book the released slot
    p2_appt = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=future_date,
            scheduled_start=datetime.time(9, 0),
            scheduled_end=datetime.time(9, 30),
        ),
    )
    assert p2_appt.id is not None
    assert p2_appt.patient_id == p2.id


def test_overlapping_and_concurrency_conflict_rejection(
    db_session: Session, setup_clinic_data: dict
):
    doc = setup_clinic_data["doctor"]
    p1 = setup_clinic_data["patient1"]
    p2 = setup_clinic_data["patient2"]
    future_date = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=6)

    # Book 09:00 - 09:30
    appt1 = appointment_service.book_appointment(
        db_session,
        AppointmentCreate(
            patient_id=p1.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=future_date,
            scheduled_start=datetime.time(9, 0),
            scheduled_end=datetime.time(9, 30),
        ),
    )
    assert appt1.id is not None

    # Overlapping slot attempt: 09:15 - 09:45
    with pytest.raises(ConflictError) as exc_overlap:
        appointment_service.book_appointment(
            db_session,
            AppointmentCreate(
                patient_id=p2.id,
                doctor_id=doc.id,
                hospital_id=doc.hospital_id,
                appointment_date=future_date,
                scheduled_start=datetime.time(9, 15),
                scheduled_end=datetime.time(9, 45),
            ),
        )
    assert exc_overlap.value.code == "APPOINTMENT_CONFLICT"

    # Exact duplicate slot attempt: 09:00 - 09:30
    with pytest.raises(ConflictError) as exc_dup:
        appointment_service.book_appointment(
            db_session,
            AppointmentCreate(
                patient_id=p2.id,
                doctor_id=doc.id,
                hospital_id=doc.hospital_id,
                appointment_date=future_date,
                scheduled_start=datetime.time(9, 0),
                scheduled_end=datetime.time(9, 30),
            ),
        )
    assert exc_dup.value.code == "APPOINTMENT_CONFLICT"

