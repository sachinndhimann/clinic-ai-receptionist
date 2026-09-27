"""
Seeds one demo clinic end to end, so you can run a full demo without
building the onboarding CLI first (see README TODO for the real
scripts/onboard_clinic.py).

What this creates:
  - One Clinic row, from app/config/clinics/demo_dental_clinic.json
  - Doctor rows for each doctor in that config
  - Slot rows: next 5 weekdays, 9am-5pm, in each doctor's slot duration
  - A handful of KnowledgeChunk rows (embedded) for FAQ/RAG testing

Safe to re-run: looks up existing rows by slug/id before creating new
ones, and skips slot/knowledge-chunk generation if they already exist
for this clinic, so running it twice doesn't duplicate data or fail.

Run: python -m scripts.seed_demo
Requires OPENAI_API_KEY set (for embeddings) — see .env.example.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from app.models.db import Clinic, Doctor, KnowledgeChunk, Slot
from app.models.session import get_session
from app.rag.embed import embed_text

CONFIG_PATH = Path(__file__).parent.parent / "app/config/clinics/demo_dental_clinic.json"

FAQ_CONTENT = [
    ("policy", "Cancellations must be made at least 4 hours before the appointment time to avoid a cancellation fee."),
    ("policy", "We accept cash, UPI, and all major debit/credit cards. We do not currently process insurance claims directly."),
    ("faq", "The clinic is open Monday to Friday 9am-7pm, and Saturday 9am-2pm. Closed on Sundays."),
    ("faq", "Parking is available in the basement of the building, free for patients with a validated ticket from reception."),
    ("doctor_bio", "Dr. Anjali Mehta specializes in general dentistry and root canal treatments, with over 10 years of experience."),
    ("doctor_bio", "Dr. Rajveer Singh specializes in orthodontics, including braces and aligners for both teenagers and adults."),
]


def seed():
    config = json.loads(CONFIG_PATH.read_text())
    db = get_session()

    # --- Clinic: get-or-create, keyed by slug ---
    clinic = db.query(Clinic).filter_by(slug=config["clinic_id"]).first()
    if clinic is None:
        clinic = Clinic(
            slug=config["clinic_id"],
            name=config["name"],
            specialty=config["specialty"],
            whatsapp_number=config["whatsapp_number"],
            timezone=config["timezone"],
            config=config,
        )
        db.add(clinic)
        db.commit()  # populates clinic.id via the ORM default, on THIS object
        print(f"Created clinic '{clinic.name}'")
    else:
        print(f"Clinic '{clinic.name}' already exists, reusing it")

    # --- Doctors: get-or-create, keyed by the explicit doctor_id from config ---
    doctors = []
    for d in config["doctors"]:
        doctor = db.get(Doctor, d["doctor_id"])
        if doctor is None:
            doctor = Doctor(
                id=d["doctor_id"],
                clinic_id=clinic.id,
                name=d["name"],
                specialty=d["specialty"],
                slot_duration_minutes=d["slot_duration_minutes"],
            )
            db.add(doctor)
        doctors.append(doctor)
    db.commit()

    # --- Slots: only generate if none exist yet for this clinic ---
    existing_slot = db.query(Slot).filter_by(clinic_id=clinic.id).first()
    if existing_slot is None:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_added = 0
        day_offset = 1
        while days_added < 5:
            day = today + timedelta(days=day_offset)
            day_offset += 1
            if day.weekday() >= 5:  # skip weekends for this demo
                continue
            days_added += 1

            for doctor in doctors:
                slot_start = day.replace(hour=9)
                day_end = day.replace(hour=17)
                while slot_start < day_end:
                    slot_end = slot_start + timedelta(minutes=doctor.slot_duration_minutes)
                    db.add(
                        Slot(
                            clinic_id=clinic.id,
                            doctor_id=doctor.id,
                            start_time=slot_start,
                            end_time=slot_end,
                            is_booked=False,
                        )
                    )
                    slot_start = slot_end
        db.commit()
        print("Slots created for next 5 weekdays")
    else:
        print("Slots already exist for this clinic, skipping generation")

    # --- Knowledge chunks: only embed/insert if none exist yet ---
    existing_chunk = db.query(KnowledgeChunk).filter_by(clinic_id=clinic.id).first()
    if existing_chunk is None:
        for source, content in FAQ_CONTENT:
            db.add(
                KnowledgeChunk(
                    clinic_id=clinic.id,
                    source=source,
                    content=content,
                    embedding=embed_text(content),
                )
            )
        db.commit()
        print(f"Knowledge chunks created: {len(FAQ_CONTENT)}")
    else:
        print("Knowledge chunks already exist for this clinic, skipping")

    print(f"\nDone. Clinic slug: {clinic.slug}")
    print(f"Doctors: {[doc.name for doc in doctors]}")
    db.close()


if __name__ == "__main__":
    seed()
