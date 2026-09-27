"""
Structured booking flow state. Deliberately NOT free-text chat history —
each turn extracts one slot value and advances a fixed step, so the agent
never has to "remember" details by re-reading a growing transcript. This
keeps per-turn token cost flat and avoids the model drifting on details
like which time was actually agreed.
"""

from sqlalchemy.orm import Session

from app.models.db import BookingFlowState

STEPS = [
    "collecting_specialty",
    "collecting_date",
    "collecting_time",
    "collecting_name",
    "confirming",
    "done",
]


def get_flow(db: Session, conversation_id: str) -> BookingFlowState | None:
    return db.get(BookingFlowState, conversation_id)


def start_flow(db: Session, conversation_id: str) -> BookingFlowState:
    flow = BookingFlowState(
        conversation_id=conversation_id,
        step=STEPS[0],
        slots={},
    )
    db.merge(flow)
    db.commit()
    return flow


def advance_flow(db: Session, conversation_id: str, updated_slots: dict) -> BookingFlowState:
    flow = db.get(BookingFlowState, conversation_id)
    flow.slots = {**flow.slots, **updated_slots}

    current_index = STEPS.index(flow.step)
    flow.step = STEPS[min(current_index + 1, len(STEPS) - 1)]

    db.commit()
    return flow


def clear_flow(db: Session, conversation_id: str) -> None:
    """Called on booking completion, explicit cancellation, or escalation —
    never leave a stale flow that a future message could accidentally
    resume into."""
    flow = db.get(BookingFlowState, conversation_id)
    if flow:
        db.delete(flow)
        db.commit()
