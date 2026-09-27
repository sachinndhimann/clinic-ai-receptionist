# Clinic AI Receptionist

WhatsApp-based AI receptionist for clinics: FAQ answering (RAG), appointment
booking (agentic tool-calling), and safe escalation to human staff.

## Architecture

```
WhatsApp --> webhooks/whatsapp.py
               |
               |-- conversation lookup (state/conversation.py)
               |-- escalated? --> stop, staff handles it
               |-- emergency keyword filter (core/emergency_filter.py) --> escalate immediately
               |-- mid-booking-flow? --> state/flow_state.py narrow handler
               |-- else: intent_router.py --> FAQ | BOOKING | COMPLAINT | UNCLEAR
               |
               |-- FAQ --> rag/retrieve.py (pgvector) --> core/agent.py (grounded answer)
               |-- BOOKING --> core/agent.py (tool-calling loop) --> tools/booking.py
               |-- COMPLAINT/UNCLEAR --> tools/escalation.py
```

## Key design decisions

- **pgvector, not a standalone vector DB** — one Postgres instance serves
  both structured data (appointments, conversations) and RAG embeddings.
  Simpler ops for a multi-tenant SaaS at this scale.
- **Tools, never freehand writes** — the LLM can only change state (book,
  cancel, escalate) through typed functions in `tools/`, each of which
  re-validates against the DB before committing.
- **Structured flow state, not chat-history replay** — multi-turn booking
  uses `booking_flow_state` (slot-filling) instead of re-feeding growing
  transcripts to the LLM. Flat token cost, no drift on remembered details.
- **Two-layer emergency detection** — a deterministic keyword filter runs
  before any LLM call; the system prompt carries a backstop instruction
  for phrasing the filter misses. Life-safety checks should not depend
  solely on probabilistic model behavior.
- **Escalation is a hard stop** — once `conversation.status == "escalated"`,
  the webhook handler skips the agent entirely until a staff member
  explicitly resolves it. No parallel bot/human replies.
- **Multi-tenant via `clinic_id`, not separate infra** — one deployment
  serves every clinic; all tables and RAG queries are scoped by clinic_id.
- **Booking is a slot-filling state machine, not agent tool-calling** —
  `core/booking_flow_handler.py` drives `state/flow_state.py` step by
  step, each step using one narrow extraction call
  (`core/slot_extraction.py`) rather than the general agent re-reasoning
  over full chat history every turn. `core/agent.py`'s tool-calling loop
  is reserved for FAQ answering and ad-hoc tool use, not multi-turn
  booking.

## Local setup

```bash
cp .env.example .env   # fill in API keys
docker compose up -d postgres redis
pip install -r requirements.txt
alembic upgrade head    # once migrations are written
uvicorn app.main:app --reload
```

## What's stubbed / TODO

- `webhooks/whatsapp.py`: `get_db()` session factory and
  `send_whatsapp_message()` (wire up Gupshup/Twilio/Meta Cloud API)
- `core/booking_flow_handler.py`'s specialty/date extraction assumes
  `clinic.config["doctors"]` is populated per the example in
  `config/clinics/demo_dental_clinic.json` — adjust if you model doctor
  data differently
- `rag/retrieve.py`: cosine-distance cutoff filtering (currently a
  placeholder — needs the actual distance value from the query)
- `scripts/onboard_clinic.py`: CLI to create a new clinic tenant, ingest
  its FAQ docs into `knowledge_chunks`, and generate its slot calendar
- `dashboard/`: staff-facing escalation queue (React/Next.js)
- Alembic migrations for the models in `models/db.py`
- Test suite, especially `tests/test_emergency_filter.py` — this is the
  safety-critical path and needs its own reviewed test cases
