"""
Main agent reasoning loop. Only reached for BOOKING intent (or UNCLEAR that
warrants a real attempt) — FAQ goes through the cheaper RAG-only path,
EMERGENCY never gets here at all (caught by emergency_filter earlier).

The system prompt encodes the safety layers designed earlier:
identity/boundaries, RAG grounding, tool-use discipline. Keep these as
separate composable blocks rather than one giant prompt string, so each
can be reviewed/tested independently.
"""

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.tools import booking, escalation
from app.tools.schemas import BOOKING_TOOLS

_client = Anthropic(api_key=settings.anthropic_api_key)

IDENTITY_AND_BOUNDARIES = """You are the WhatsApp receptionist for {clinic_name}, a {specialty} clinic.

You MUST NOT:
- Provide medical advice, diagnosis, or treatment recommendations of any kind
- Interpret symptoms, test results, or medication questions
- Make promises about pricing, insurance, or outcomes not in your knowledge base
- Claim a booking is confirmed unless the create_appointment tool call succeeded

You MUST:
- Only answer factual questions using the retrieved clinic information provided to you
- Use tools for anything that changes state (booking, rescheduling, cancelling)
- Escalate via escalate_to_human when uncertain, asked something outside your scope,
  or when the patient seems distressed
- Respond in the language the patient uses (Hindi, Punjabi, or English)
- Always confirm patient-provided details back to them before calling create_appointment
"""

RAG_GROUNDING = """When answering factual questions, use ONLY the information in the
retrieved context below. If it doesn't contain the answer, say you'll check
with staff and call escalate_to_human — do not guess or use outside knowledge.

Retrieved context:
{rag_context}
"""

TOOL_IMPLEMENTATIONS = {
    "get_available_slots": booking.get_available_slots,
    "create_appointment": booking.create_appointment,
    "reschedule_appointment": booking.reschedule_appointment,
    "cancel_appointment": booking.cancel_appointment,
    "lookup_patient_history": booking.lookup_patient_history,
    "escalate_to_human": escalation.escalate_to_human,
}


def build_system_prompt(clinic_name: str, specialty: str, rag_context: str) -> str:
    return (
        IDENTITY_AND_BOUNDARIES.format(clinic_name=clinic_name, specialty=specialty)
        + "\n"
        + RAG_GROUNDING.format(rag_context=rag_context or "(no relevant context retrieved)")
    )


def run_agent_turn(
    db: Session,
    clinic_id: str,
    clinic_name: str,
    specialty: str,
    patient_message: str,
    rag_context: str = "",
    max_tool_iterations: int = 4,
) -> str:
    """Runs one reasoning turn, executing tool calls as needed, and returns
    the final text response to send back to the patient."""

    system_prompt = build_system_prompt(clinic_name, specialty, rag_context)
    messages = [{"role": "user", "content": patient_message}]

    for _ in range(max_tool_iterations):
        response = _client.messages.create(
            model=settings.agent_model,
            max_tokens=1024,
            system=system_prompt,
            tools=BOOKING_TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            # Model produced a final text answer — done reasoning.
            return "".join(block.text for block in response.content if block.type == "text")

        # Execute each requested tool call against the real DB, then feed
        # results back so the model can continue reasoning (e.g. present
        # slot options, or confirm a completed booking).
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            impl = TOOL_IMPLEMENTATIONS.get(block.name)
            result = impl(db=db, **block.input) if impl else {"error": "unknown_tool"}
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    # Safety valve: if the loop somehow doesn't converge, escalate rather
    # than leave the patient without a response.
    escalation.escalate_to_human(
        db=db,
        clinic_id=clinic_id,
        patient_phone="",  # caller should fill in from conversation context
        context_summary="Agent reasoning did not converge within iteration limit.",
        urgency="medium",
    )
    return "Let me get our staff to help you with this — connecting you now."
