"""
Booking flow step handler. This is what replaces a full agent invocation
once a patient is mid-booking — cheaper, and immune to the model losing
track of details across a long conversation, because state lives in
BookingFlowState.slots, not in replayed chat history.

Entry points:
  - start_booking_flow(): called once, when intent_router first classifies
    a message as BOOKING and no flow is currently active.
  - handle_booking_flow_step(): called for every subsequent message while
    flow.step != "done" (checked by the webhook handler before routing
    to intent_router at all).

Every step either advances on successful extraction or re-asks the same
question — it never advances on a None extraction result. Bad silent
advancement is worse than asking the patient to repeat themselves once.
"""

from datetime import date as date_cls

from sqlalchemy.orm import Session

from app.core.slot_extraction import (
    extract_confirmation,
    extract_date,
    extract_specialty,
    match_selected_slot,
)
from app.models.db import Clinic, Conversation
from app.state import flow_state
from app.tools.booking import create_appointment, get_available_slots

REASK = {
    "collecting_specialty": "Sorry, which type of doctor would you like to see?",
    "collecting_date": "Sorry, what date works for you? (e.g. 'tomorrow', 'next Monday')",
    "collecting_time": "Sorry, which of those time options would you like?",
    "collecting_name": "Could you tell me the patient's name for the booking?",
    "confirming": "Should I go ahead and confirm this booking — yes or no?",
}


def start_booking_flow(
    db: Session, clinic: Clinic, conversation: Conversation, message_text: str
) -> str:
    specialties = [d["specialty"] for d in clinic.config.get("doctors", [])] or [clinic.specialty]
    flow_state.start_flow(db, conversation.id)

    # Try to pull specialty from the very first message (patients often say
    # "I want to see a dentist tomorrow" up front) — if it's not there,
    # fall through to asking explicitly rather than guessing.
    specialty = extract_specialty(message_text, specialties)
    if specialty:
        flow_state.advance_flow(db, conversation.id, {"specialty": specialty})
        return "Great — what date would you like to come in?"

    return f"Sure, I can help you book. {REASK['collecting_specialty']}"


def handle_booking_flow_step(
    db: Session, clinic: Clinic, conversation: Conversation, message_text: str
) -> str:
    flow = flow_state.get_flow(db, conversation.id)
    step = flow.step

    if step == "collecting_specialty":
        specialties = [d["specialty"] for d in clinic.config.get("doctors", [])] or [
            clinic.specialty
        ]
        specialty = extract_specialty(message_text, specialties)
        if not specialty:
            return REASK["collecting_specialty"]
        flow_state.advance_flow(db, conversation.id, {"specialty": specialty})
        return "Got it. What date would you like to come in?"

    if step == "collecting_date":
        visit_date = extract_date(message_text, today_iso=date_cls.today().isoformat())
        if not visit_date:
            return REASK["collecting_date"]

        slots = get_available_slots(
            db,
            clinic_id=clinic.id,
            date_from=visit_date,
            date_to=visit_date,
            specialty=flow.slots.get("specialty"),
        )
        if not slots:
            # Stay on the same step — don't advance past a date with no
            # availability, ask for an alternative instead.
            return (
                f"We don't have openings on {visit_date} for that specialty. "
                "Could you try another date?"
            )

        flow_state.advance_flow(
            db, conversation.id, {"date": visit_date, "candidate_slots": slots}
        )
        options_text = "\n".join(f"- {s['label']}" for s in slots[:5])
        return f"Here's what's available:\n{options_text}\n\nWhich time works for you?"

    if step == "collecting_time":
        candidate_slots = flow.slots.get("candidate_slots", [])
        slot_id = match_selected_slot(message_text, candidate_slots)
        if not slot_id:
            return REASK["collecting_time"]
        flow_state.advance_flow(db, conversation.id, {"selected_slot_id": slot_id})
        return "And what name should I book this under?"

    if step == "collecting_name":
        patient_name = message_text.strip()
        if len(patient_name) < 2:
            return REASK["collecting_name"]
        flow_state.advance_flow(db, conversation.id, {"patient_name": patient_name})

        chosen = next(
            (s for s in flow.slots.get("candidate_slots", []) if s["slot_id"] == flow.slots.get("selected_slot_id")),
            None,
        )
        time_label = chosen["label"] if chosen else "the selected time"
        return (
            f"Confirming: book {patient_name} for {flow.slots.get('specialty')} "
            f"on {time_label}. Shall I go ahead? (yes/no)"
        )

    if step == "confirming":
        confirmed = extract_confirmation(message_text)
        if confirmed is None:
            return REASK["confirming"]

        if not confirmed:
            flow_state.clear_flow(db, conversation.id)
            return "No problem, I've cancelled that. Let me know if you'd like to book again."

        result = create_appointment(
            db,
            clinic_id=clinic.id,
            slot_id=flow.slots["selected_slot_id"],
            patient_name=flow.slots["patient_name"],
            patient_phone=conversation.patient_phone,
        )
        flow_state.clear_flow(db, conversation.id)

        if not result.get("success"):
            # Most likely someone else booked the same slot in the meantime.
            return (
                "Sorry, that slot was just taken by another patient. "
                "Would you like to try booking again?"
            )
        return "You're all booked in! We'll send a reminder closer to the date."

    # Shouldn't happen (step == "done" is filtered out before this is called),
    # but fail safe rather than throw.
    flow_state.clear_flow(db, conversation.id)
    return "Let me start that booking over — what type of doctor would you like to see?"
