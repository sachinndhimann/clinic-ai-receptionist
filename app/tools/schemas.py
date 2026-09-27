"""
Tool schemas exposed to the LLM. Passed as `tools=` in the Anthropic/OpenAI
API call. The LLM can only affect state through these — it never writes
directly to the database.
"""

BOOKING_TOOLS = [
    {
        "name": "get_available_slots",
        "description": (
            "Get available appointment slots for a doctor or specialty "
            "within a date range. Returns slot_id values — always refer "
            "to slots by slot_id, never compute times yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_id": {"type": "string"},
                "doctor_id": {"type": "string", "description": "optional"},
                "specialty": {"type": "string", "description": "optional, e.g. 'dental'"},
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
            },
            "required": ["clinic_id", "date_from", "date_to"],
        },
    },
    {
        "name": "create_appointment",
        "description": (
            "Book a confirmed appointment for a specific slot_id. "
            "Server-side re-validates the slot is still free before "
            "committing, to handle race conditions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_id": {"type": "string"},
                "slot_id": {"type": "string"},
                "patient_name": {"type": "string"},
                "patient_phone": {"type": "string"},
                "reason_for_visit": {"type": "string"},
            },
            "required": ["clinic_id", "slot_id", "patient_name", "patient_phone"],
        },
    },
    {
        "name": "reschedule_appointment",
        "description": "Move an existing appointment to a new slot_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "new_slot_id": {"type": "string"},
            },
            "required": ["appointment_id", "new_slot_id"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "reason": {"type": "string", "description": "optional"},
            },
            "required": ["appointment_id"],
        },
    },
    {
        "name": "lookup_patient_history",
        "description": "Check if this phone number has prior appointments at this clinic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_id": {"type": "string"},
                "patient_phone": {"type": "string"},
            },
            "required": ["clinic_id", "patient_phone"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand off this conversation to clinic staff. Use for emergencies, "
            "complaints, medical questions, or anything outside your scope. "
            "When in doubt, escalate rather than guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_id": {"type": "string"},
                "patient_phone": {"type": "string"},
                "context_summary": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["clinic_id", "patient_phone", "context_summary", "urgency"],
        },
    },
]
