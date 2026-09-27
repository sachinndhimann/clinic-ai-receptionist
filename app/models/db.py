"""
SQLAlchemy models for the clinic AI receptionist.

Two distinct data domains live in the same Postgres instance:
  1. Structured/transactional data (clinics, doctors, slots, appointments,
     conversations, flow state) — the source of truth for anything the
     agent WRITES to. The LLM never freehand-writes here; it only goes
     through tool functions in app/tools/.
  2. Vector data (knowledge_chunks) — RAG source for anything the agent
     RETRIEVES to answer questions. Read-only from the agent's perspective.

Every table is scoped by clinic_id for multi-tenancy — one deployment,
many clinics, isolated by row filtering rather than separate schemas/DBs.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)  # e.g. "demo-dental-001"
    name: Mapped[str] = mapped_column(String)
    specialty: Mapped[str] = mapped_column(String)
    whatsapp_number: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String, default="Asia/Kolkata")
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # working hours, languages, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    doctors: Mapped[list["Doctor"]] = relationship(back_populates="clinic")


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    specialty: Mapped[str] = mapped_column(String)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)

    clinic: Mapped["Clinic"] = relationship(back_populates="doctors")
    slots: Mapped[list["Slot"]] = relationship(back_populates="doctor")


class Slot(Base):
    """A single bookable time slot. Generated ahead of time (e.g. nightly job
    rolls the schedule forward) rather than computed on the fly, so
    get_available_slots() is a simple filtered SELECT, not date-math the LLM
    has to reason about."""

    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("doctor_id", "start_time"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)

    doctor: Mapped["Doctor"] = relationship(back_populates="slots")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.id"))
    slot_id: Mapped[str] = mapped_column(ForeignKey("slots.id"), unique=True)
    patient_name: Mapped[str] = mapped_column(String)
    patient_phone: Mapped[str] = mapped_column(String, index=True)
    reason_for_visit: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="confirmed")  # confirmed|cancelled|completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    """One row per (clinic, patient) conversation thread. This is the
    session-equivalent for a channel (WhatsApp) that has no native concept
    of a session."""

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("clinic_id", "patient_phone"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_phone: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active|idle|escalated|closed
    current_intent: Mapped[str] = mapped_column(String, nullable=True)
    escalation_reason: Mapped[str] = mapped_column(Text, nullable=True)
    escalation_urgency: Mapped[str] = mapped_column(String, nullable=True)  # low|medium|high
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Message(Base):
    """Full transcript, used to render context for staff on escalation and
    for audit/eval purposes. NOT what gets replayed into the LLM each turn —
    the agent uses structured flow_state for that (see state/flow_state.py)."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender: Mapped[str] = mapped_column(String)  # patient|bot|staff
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BookingFlowState(Base):
    """Structured slot-filling state for an in-progress booking. Cleared on
    completion, cancellation, or escalation."""

    __tablename__ = "booking_flow_state"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), primary_key=True
    )
    step: Mapped[str] = mapped_column(String)  # collecting_specialty|collecting_date|...
    slots: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeChunk(Base):
    """RAG source: embedded clinic knowledge (FAQs, policies, doctor bios,
    service descriptions). Read-only from the agent's perspective — never
    written to during a conversation, only during clinic onboarding /
    content updates via scripts/onboard_clinic.py."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    source: Mapped[str] = mapped_column(String)  # e.g. "faq", "policy", "doctor_bio"
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector(1536))  # matches text-embedding-3-small dims
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
