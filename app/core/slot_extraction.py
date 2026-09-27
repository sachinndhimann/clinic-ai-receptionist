"""
Narrow, single-purpose LLM calls used by the booking flow step handler.

Each function extracts exactly ONE piece of structured data from a single
message. These are deliberately NOT the full tool-calling agent — they're
cheap, fast, small-model calls with a tight JSON-only output contract,
because the flow handler runs one of these per patient message during an
active booking, and that happens far more often than a full agent
invocation would need to.

If extraction fails (patient said something unparseable), every function
returns None so the flow handler can re-ask instead of advancing on bad
data.
"""

import json
import re

from anthropic import Anthropic

from app.config.settings import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(prompt: str) -> dict | None:
    response = _client.messages.create(
        model=settings.router_model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Models frequently wrap JSON in markdown code fences even when told
    # not to — strip those before parsing rather than treating it as a
    # genuine extraction failure.
    cleaned = _FENCE_RE.sub("", raw).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        print(f"[slot_extraction] Could not parse JSON from model output: {raw!r}")
        return None


def extract_specialty(message_text: str, available_specialties: list[str]) -> str | None:
    prompt = f"""The clinic offers these specialties/doctor types: {available_specialties}

Patient message: "{message_text}"

Which specialty is the patient asking for? Respond with ONLY a JSON object:
{{"specialty": "<one of the listed specialties>"}} or {{"specialty": null}} if unclear."""
    result = _extract_json(prompt)
    return result.get("specialty") if result else None


def extract_date(message_text: str, today_iso: str) -> str | None:
    prompt = f"""Today's date is {today_iso}. Patient message: "{message_text}"

Extract the date the patient wants to visit. Respond with ONLY a JSON object:
{{"date": "YYYY-MM-DD"}} or {{"date": null}} if no date is mentioned or it's unclear.
Resolve relative dates ("tomorrow", "next Monday") against today's date."""
    result = _extract_json(prompt)
    return result.get("date") if result else None


def match_selected_slot(message_text: str, candidate_slots: list[dict]) -> str | None:
    """candidate_slots: [{"slot_id": ..., "label": "Tue 29 Sep, 2:00 PM"}, ...]"""
    options = "\n".join(f"- {s['slot_id']}: {s['label']}" for s in candidate_slots)
    prompt = f"""Available slots:
{options}

Patient message: "{message_text}"

Which slot_id is the patient choosing? Respond with ONLY a JSON object:
{{"slot_id": "<matching slot_id>"}} or {{"slot_id": null}} if it doesn't clearly match one."""
    result = _extract_json(prompt)
    return result.get("slot_id") if result else None


def extract_confirmation(message_text: str) -> bool | None:
    prompt = f"""Patient message: "{message_text}"

Is the patient confirming (yes) or declining/cancelling (no)? Respond with
ONLY a JSON object: {{"confirmed": true}}, {{"confirmed": false}}, or
{{"confirmed": null}} if genuinely unclear."""
    result = _extract_json(prompt)
    return result.get("confirmed") if result else None