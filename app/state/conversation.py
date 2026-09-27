from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db import Conversation, Message


def get_or_create_conversation(db: Session, clinic_id: str, patient_phone: str) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter_by(clinic_id=clinic_id, patient_phone=patient_phone)
        .first()
    )
    if conversation is None:
        conversation = Conversation(
            clinic_id=clinic_id,
            patient_phone=patient_phone,
            status="active",
        )
        db.add(conversation)
        db.commit()
    return conversation


def is_escalated(conversation: Conversation) -> bool:
    """Webhook handler MUST check this before invoking the agent at all —
    once escalated, only a staff 'resolve' action can return control to
    the bot. This prevents the bot and a human replying in parallel."""
    return conversation.status == "escalated"


def log_message(db: Session, conversation_id: str, sender: str, body: str) -> None:
    db.add(Message(conversation_id=conversation_id, sender=sender, body=body))
    conv = db.get(Conversation, conversation_id)
    conv.last_message_at = datetime.utcnow()
    db.commit()


def resolve_escalation(db: Session, conversation_id: str) -> None:
    """Staff-triggered action from the dashboard. Explicit only — never
    auto-timeout back to bot control, since that risks the bot picking up
    mid-sentence in a conversation a human just handled."""
    conv = db.get(Conversation, conversation_id)
    conv.status = "active"
    conv.escalation_reason = None
    conv.escalation_urgency = None
    db.commit()
