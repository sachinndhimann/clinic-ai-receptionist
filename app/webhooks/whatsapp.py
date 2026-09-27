"""
Inbound WhatsApp webhook. This is the entry point that wires together every
layer designed earlier, in the correct order:

  1. Load conversation (create if new)
  2. If already escalated -> log message, do NOT call the agent at all
  3. Emergency keyword pre-filter (deterministic, no LLM call)
  4. If in an active booking flow -> narrow slot-filling handler
  5. Otherwise -> intent router -> FAQ (RAG-only) or BOOKING (starts flow)
  6. Send reply back via WhatsApp API

Note on BOOKING: it does NOT go through the general tool-calling agent
(core/agent.py). It starts the structured flow_state slot-filling machine
instead — cheaper per turn and immune to the model losing track of
booking details across a long conversation. core/agent.py's tool-calling
loop remains available for FAQ answering and any ad-hoc tool use it needs
(e.g. lookup_patient_history), just not as the multi-turn booking driver.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.agent import run_agent_turn
from app.core.booking_flow_handler import handle_booking_flow_step, start_booking_flow
from app.core.emergency_filter import emergency_response_text, is_emergency
from app.core.intent_router import classify_intent
from app.models.db import Clinic
from app.models.session import SessionLocal
from app.rag.retrieve import retrieve_context
from app.state.conversation import get_or_create_conversation, is_escalated, log_message
from app.state.flow_state import get_flow
from app.tools.escalation import escalate_to_human

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def send_whatsapp_message(to_phone: str, body: str) -> None:
    """DEMO MODE: prints to console instead of calling a real WhatsApp API,
    so you can run the whole pipeline locally with curl before wiring up
    Gupshup/Twilio/Meta Cloud API. Swap this out for a real HTTP call when
    you're ready to go live — the rest of the pipeline doesn't change."""
    print(f"\n[WhatsApp -> {to_phone}]\n{body}\n")


@router.post("/webhooks/whatsapp/{clinic_slug}")
def handle_inbound_message(
    clinic_slug: str,
    from_phone: str,
    message_text: str,
    db: Session = Depends(get_db),
):
    clinic = db.query(Clinic).filter_by(slug=clinic_slug).first()
    if clinic is None:
        return {"error": "unknown_clinic"}

    conversation = get_or_create_conversation(db, clinic.id, from_phone)
    log_message(db, conversation.id, sender="patient", body=message_text)

    # Step 2: if a human has already taken over, the bot stays silent.
    # Staff sees this message in the dashboard; no LLM call happens.
    if is_escalated(conversation):
        return {"status": "queued_for_staff", "reply": None}

    # Step 3: deterministic emergency check, before any LLM call.
    if is_emergency(message_text):
        reply = emergency_response_text(clinic.config.get("emergency_contact", ""))
        escalate_to_human(
            db,
            clinic_id=clinic.id,
            patient_phone=from_phone,
            context_summary=f"Emergency keyword match: {message_text[:200]}",
            urgency="high",
        )
        send_whatsapp_message(from_phone, reply)
        log_message(db, conversation.id, sender="bot", body=reply)
        return {"status": "escalated_emergency", "reply": reply}

    # Step 4: if mid-booking-flow, skip general routing and go straight to
    # the narrow slot-filling handler — one extraction call for whichever
    # single slot the current step needs, not a full agent invocation.
    flow = get_flow(db, conversation.id)
    if flow and flow.step != "done":
        reply = handle_booking_flow_step(db, clinic, conversation, message_text)
    else:
        # Step 5: general routing.
        intent = classify_intent(message_text)

        if intent == "FAQ":
            context_chunks = retrieve_context(db, clinic.id, message_text)
            reply = run_agent_turn(
                db=db,
                clinic_id=clinic.id,
                clinic_name=clinic.name,
                specialty=clinic.specialty,
                patient_message=message_text,
                rag_context="\n---\n".join(context_chunks),
            )
        elif intent == "BOOKING":
            # Kicks off the structured flow (see core/booking_flow_handler.py).
            # Subsequent messages will hit the `flow.step != "done"` branch
            # above on their next turn through this handler.
            reply = start_booking_flow(db, clinic, conversation, message_text)
        else:  # COMPLAINT or UNCLEAR -> escalate by default, don't guess
            escalate_to_human(
                db,
                clinic_id=clinic.id,
                patient_phone=from_phone,
                context_summary=f"{intent}: {message_text[:200]}",
                urgency="medium",
            )
            reply = "Let me connect you with our staff for this — one moment."

    send_whatsapp_message(from_phone, reply)
    log_message(db, conversation.id, sender="bot", body=reply)
    return {"status": "handled", "reply": reply}
