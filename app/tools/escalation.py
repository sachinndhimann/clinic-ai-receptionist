"""
Escalation handoff. Firing this tool must be a hard stop for the agent:
once a conversation is escalated, the webhook handler checks
conversation.status BEFORE invoking the agent again, so the bot and a
human staff member can never reply to the same patient in parallel.
"""

import httpx
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.db import BookingFlowState, Conversation


def escalate_to_human(
    db: Session,
    clinic_id: str,
    patient_phone: str,
    context_summary: str,
    urgency: str,
) -> dict:
    conversation = (
        db.query(Conversation)
        .filter_by(clinic_id=clinic_id, patient_phone=patient_phone)
        .first()
    )
    if conversation is None:
        return {"success": False, "error": "conversation_not_found"}

    conversation.status = "escalated"
    conversation.escalation_reason = context_summary
    conversation.escalation_urgency = urgency

    # Clear any in-progress booking flow — staff will handle it manually
    # from here; the bot should not attempt to resume a stale flow later.
    flow_state = db.get(BookingFlowState, conversation.id)
    if flow_state:
        db.delete(flow_state)

    db.commit()

    if urgency == "high" and settings.staff_alert_webhook:
        _send_urgent_alert(clinic_id, patient_phone, context_summary)

    return {"success": True, "conversation_id": conversation.id}


def _send_urgent_alert(clinic_id: str, patient_phone: str, context_summary: str) -> None:
    """Push/SMS alert for high-urgency escalations — staff shouldn't have
    to be staring at the dashboard to catch an emergency."""
    try:
        httpx.post(
            settings.staff_alert_webhook,
            json={
                "clinic_id": clinic_id,
                "patient_phone": patient_phone,
                "summary": context_summary,
                "urgency": "high",
            },
            timeout=5.0,
        )
    except httpx.HTTPError:
        # Alerting must never crash the request handler. Log and move on;
        # the escalation is already recorded in the DB regardless.
        pass
