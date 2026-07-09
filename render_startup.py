"""Render web service entry point - seeds DB, processes demo calls, starts uvicorn."""

import json
import logging
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent / "fitnova-call-intel"
sys.path.insert(0, str(BASE))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

from scripts.seed_data import seed as seed_db
from fitnova.storage.db import init_db, get_session
from fitnova.storage.models import Advisor, Call
from fitnova.pipeline.orchestrator import process_call as run_pipeline

SAMPLE_CALLS = [
    {
        "id": "DEMO-001",
        "advisor_email": "priya@fitnova.in",
        "script": """
Advisor: Hello, this is Priya from FitNova. Am I speaking with Mr. Sharma?
Customer: Yes, this is Amit Sharma speaking.
Advisor: Great, thanks for taking my call! I understand you're interested in our fitness coaching programs. Let me start by understanding your fitness goals better.
Customer: Well, I've been trying to lose weight for about six months. I tried going to the gym but I just don't have the motivation to go regularly.
Advisor: I completely understand. Many of our clients face the same challenge. At FitNova, we design personalized programs that fit your schedule. How much time can you commit to exercise each week?
Customer: Maybe three to four days a week, about 45 minutes each.
Advisor: That's perfect for our program. And just so you know, if you sign up today there's a 20% discount available.
Customer: That sounds interesting. How much does it cost?
Advisor: Our premium plan is Rs.15,000 for three months.
Customer: Guaranteed results? I've heard that before and it didn't work out.
Advisor: I assure you, our program is different. Let me book you a free trial session for this Saturday at 10 AM.
Customer: Okay, let's try the trial session first.
Advisor: Perfect! I'll send you the details.
""",
    },
    {
        "id": "DEMO-002",
        "advisor_email": "rahul@fitnova.in",
        "script": """
Advisor: Hi, this is Rahul from FitNova. I'm calling about the inquiry you submitted.
Customer: Oh, yes. I was looking at your website. Can you tell me more about the programs?
Advisor: Sure, we have multiple plans. But first, tell me a bit about yourself. What's your fitness goal?
Customer: I want to build muscle and get stronger.
Advisor: Great goal. Do you have any experience with strength training?
Customer: Some, but I've never worked with a coach.
Advisor: That's exactly where we add value. I'd recommend our premium coaching plan at Rs.12,000 per quarter.
Customer: That sounds reasonable.
Advisor: Would you like to book a free trial session? Tomorrow at 6 PM works?
Customer: Yes.
Advisor: Perfect. You'll get a confirmation message shortly.
""",
    },
    {
        "id": "DEMO-BAD-003",
        "advisor_email": "priya@fitnova.in",
        "script": """
Advisor: Hello, is this Mr. Gupta? I'm calling from FitNova.
Customer: Yes, speaking.
Advisor: Great, I'm calling about our premium fitness program.
Customer: What does it include?
Advisor: Everything - personalized training, diet plans, yoga. If you join today, I can give you a special rate of just Rs.10,000.
Customer: That seems like a lot. How is this different from a regular gym?
Advisor: Our results speak for themselves. We guarantee you'll lose at least 5 kg in the first month.
Customer: Can I think about it and call you back?
Advisor: The offer expires today. I can hold the slot for the next 2 hours.
Customer: Let me discuss with my spouse.
Advisor: Okay, but I can't guarantee the price after today.
""",
    },
    {
        "id": "DEMO-HING-004",
        "advisor_email": "rahul@fitnova.in",
        "script": """
Advisor: Namaste, main Rahul FitNova se bol raha hoon.
Customer: Haan, Vikram bol raha hoon.
Advisor: Aapne fitness inquiry kiya tha na? Aap ke goals kya hain?
Customer: Ha ji, main weight loss karna chahta hoon.
Advisor: Main samajh gaya. Aap roz kitna time de sakte hain?
Customer: 30-40 minutes, 4 days a week.
Advisor: Perfect! We have a great plan for you at Rs.12,000 for three months.
Customer: Achha, trial free hai?
Advisor: Bilkul. I can book you for Saturday at 10 AM.
Customer: Haan, bhej do. Thank you!
""",
    },
]


def create_sample_audio(script_text: str, output_path: Path):
    with open(output_path, "wb") as f:
        f.write(script_text.encode("utf-8"))


def create_metadata_json(call_id: str, advisor_email: str, audio_filename: str):
    return {
        "external_call_id": call_id,
        "advisor_email": advisor_email,
        "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "audio_file": audio_filename,
    }


def seed_and_process():
    os.chdir(BASE)
    init_db()
    seed_db()

    incoming = BASE / "fitnova" / "data" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    for call in SAMPLE_CALLS:
        audio_path = incoming / f"call_{call['id']}.mp3"
        if not audio_path.exists():
            create_sample_audio(call["script"], audio_path)
            meta_path = incoming / f"call_{call['id']}.json"
            meta = create_metadata_json(call["id"], call["advisor_email"], f"call_{call['id']}.mp3")
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    db = get_session()
    try:
        for call in SAMPLE_CALLS:
            existing = db.query(Call).filter(Call.external_call_id == call["id"]).first()
            if existing:
                print(f"  {call['id']} already processed, skipping.")
                continue
            advisor = db.query(Advisor).filter(Advisor.email == call["advisor_email"]).first()
            if not advisor:
                print(f"  Skipping {call['id']} - advisor not found.")
                continue
            try:
                result = run_pipeline(
                    external_call_id=call["id"],
                    advisor_id=advisor.id,
                    source_type="folder",
                    audio_bytes=call["script"].encode("utf-8"),
                    db=db,
                )
                print(f"  {call['id']}: {result['status']}")
            except Exception as e:
                print(f"  {call['id']}: FAILED - {e}")
    finally:
        db.close()
    print("Startup seeding complete.")


if __name__ == "__main__":
    seed_and_process()

    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("fitnova.api.main:app", host="0.0.0.0", port=port, log_level="info")
