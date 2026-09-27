"""
Minimal staff-facing endpoints. Stands in for the real dashboard (see
README "What's stubbed") — enough to demo the escalation handoff loop:
see what's waiting, read the transcript, reply, resolve.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.db import Conversation, Message
from app.models.session import SessionLocal
from app.state.conversation import log_message, resolve_escalation
from app.webhooks.whatsapp import send_whatsapp_message

router = APIRouter(prefix="/staff")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/escalations")
def list_escalations(db: Session = Depends(get_db)):
    escalated = db.query(Conversation).filter_by(status="escalated").all()
    return [
        {
            "conversation_id": c.id,
            "patient_phone": c.patient_phone,
            "urgency": c.escalation_urgency,
            "reason": c.escalation_reason,
        }
        for c in escalated
    ]


@router.get("/conversations/{conversation_id}/messages")
def get_transcript(conversation_id: str, db: Session = Depends(get_db)):
    messages = (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return [{"sender": m.sender, "body": m.body, "at": m.created_at.isoformat()} for m in messages]


@router.post("/conversations/{conversation_id}/reply")
def staff_reply(conversation_id: str, body: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        return {"error": "not_found"}
    send_whatsapp_message(conversation.patient_phone, body)
    log_message(db, conversation_id, sender="staff", body=body)
    return {"status": "sent"}


@router.post("/conversations/{conversation_id}/resolve")
def resolve(conversation_id: str, db: Session = Depends(get_db)):
    resolve_escalation(db, conversation_id)
    return {"status": "resolved"}
