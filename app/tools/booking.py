"""
Implementations behind the booking tool schemas. These are the ONLY code
paths that write to slots/appointments — the LLM never touches the DB
directly, it only calls these functions via tool-use.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db import Appointment, Doctor, Slot


def get_available_slots(
    db: Session,
    clinic_id: str,
    date_from: str,
    date_to: str,
    doctor_id: str | None = None,
    specialty: str | None = None,
) -> list[dict]:
    # date_from/date_to arrive as "YYYY-MM-DD" strings. Slot.start_time is a
    # real TIMESTAMP column, so comparing it to a plain string fails at the
    # SQL level (Postgres won't implicitly cast varchar to timestamp for
    # >=/<=). Parse into actual datetimes before building the query.
    range_start = datetime.fromisoformat(date_from)
    range_end = datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59)

    query = select(Slot).where(
        Slot.clinic_id == clinic_id,
        Slot.is_booked.is_(False),
        Slot.start_time >= range_start,
        Slot.start_time <= range_end,
    )
    if doctor_id:
        query = query.where(Slot.doctor_id == doctor_id)
    elif specialty:
        query = query.join(Doctor, Doctor.id == Slot.doctor_id).where(
            Doctor.specialty.ilike(f"%{specialty}%")
        )

    slots = db.execute(query).scalars().all()
    return [
        {
            "slot_id": s.id,
            "doctor_id": s.doctor_id,
            "start_time": s.start_time.isoformat(),
            "label": s.start_time.strftime("%a %d %b, %I:%M %p"),
        }
        for s in slots
    ]


def create_appointment(
    db: Session,
    clinic_id: str,
    slot_id: str,
    patient_name: str,
    patient_phone: str,
    reason_for_visit: str = "",
) -> dict:
    slot = db.get(Slot, slot_id)

    # Server-side re-check — critical for race conditions when two patients
    # try to book the same slot near-simultaneously. Never trust that a
    # slot offered a few messages ago is still free.
    if slot is None or slot.clinic_id != clinic_id:
        return {"success": False, "error": "slot_not_found"}
    if slot.is_booked:
        return {"success": False, "error": "slot_already_booked"}

    slot.is_booked = True
    appointment = Appointment(
        clinic_id=clinic_id,
        doctor_id=slot.doctor_id,
        slot_id=slot.id,
        patient_name=patient_name,
        patient_phone=patient_phone,
        reason_for_visit=reason_for_visit,
        status="confirmed",
    )
    db.add(appointment)
    db.commit()

    return {
        "success": True,
        "appointment_id": appointment.id,
        "start_time": slot.start_time.isoformat(),
    }


def reschedule_appointment(db: Session, appointment_id: str, new_slot_id: str) -> dict:
    appointment = db.get(Appointment, appointment_id)
    new_slot = db.get(Slot, new_slot_id)

    if appointment is None:
        return {"success": False, "error": "appointment_not_found"}
    if new_slot is None or new_slot.is_booked:
        return {"success": False, "error": "new_slot_unavailable"}

    old_slot = db.get(Slot, appointment.slot_id)
    if old_slot:
        old_slot.is_booked = False

    new_slot.is_booked = True
    appointment.slot_id = new_slot.id
    db.commit()

    return {"success": True, "appointment_id": appointment.id}


def cancel_appointment(db: Session, appointment_id: str, reason: str = "") -> dict:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        return {"success": False, "error": "appointment_not_found"}

    appointment.status = "cancelled"
    slot = db.get(Slot, appointment.slot_id)
    if slot:
        slot.is_booked = False
    db.commit()

    return {"success": True}


def lookup_patient_history(db: Session, clinic_id: str, patient_phone: str) -> dict:
    appointments = (
        db.execute(
            select(Appointment)
            .where(
                Appointment.clinic_id == clinic_id,
                Appointment.patient_phone == patient_phone,
            )
            .order_by(Appointment.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {
        "is_returning_patient": len(appointments) > 0,
        "appointment_count": len(appointments),
        "most_recent": appointments[0].created_at.isoformat() if appointments else None,
    }