"""
Intent router. Runs AFTER the emergency_filter (which is a separate,
non-LLM keyword check) and BEFORE the full agent loop.

Uses a small/cheap model — this call happens on every single inbound
message, so cost and latency matter here more than anywhere else in
the pipeline. Most WhatsApp traffic to a clinic is simple FAQs; don't
pay for a full tool-calling agent invocation to answer "what are your
hours."
"""

from anthropic import Anthropic

from app.config.settings import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

INTENTS = ["FAQ", "BOOKING", "COMPLAINT", "UNCLEAR"]
# EMERGENCY is deliberately not classified here — it's caught earlier by
# emergency_filter.is_emergency() before this router ever runs.

ROUTER_PROMPT = """Classify the patient's WhatsApp message into exactly one category:

FAQ — a factual question about the clinic (hours, location, doctors, services, pricing, policies)
BOOKING — wants to book, reschedule, or cancel an appointment
COMPLAINT — expressing dissatisfaction, frustration, or a service issue
UNCLEAR — anything else, or ambiguous

Respond with only the single category word, nothing else.

Message: {message}"""


def classify_intent(message_text: str) -> str:
    response = _client.messages.create(
        model=settings.router_model,
        max_tokens=10,
        messages=[{"role": "user", "content": ROUTER_PROMPT.format(message=message_text)}],
    )
    label = response.content[0].text.strip().upper()
    return label if label in INTENTS else "UNCLEAR"
