"""Minimal Render startup - adds subdirectory, seeds DB, starts uvicorn."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent / "fitnova-call-intel"
sys.path.insert(0, str(BASE))
os.chdir(str(BASE))

# Seed DB + process demo calls (fast with stub analysis)
from scripts.seed_data import seed as _seed_db
_seed_db()

# Process demo calls via the seed endpoint internally
import json, time
from fitnova.storage.db import get_session
from fitnova.storage.models import Call, Advisor
from fitnova.ingestion.folder_source import FolderSource
from fitnova.pipeline.orchestrator import process_call as run_pipeline

incoming = Path("fitnova/data/incoming")
incoming.mkdir(parents=True, exist_ok=True)

SAMPLE_CALLS = [
    {
        "id": "DEMO-001",
        "advisor_email": "priya@fitnova.in",
        "script": (
            "Advisor: Hello, this is Priya from FitNova. Am I speaking with Mr. Sharma?\n"
            "Customer: Yes, this is Amit Sharma speaking.\n"
            "Advisor: Great, thanks for taking my call! I understand you're interested in our fitness coaching programs. Let me start by understanding your fitness goals better.\n"
            "Customer: Well, I've been trying to lose weight for about six months. I tried going to the gym but I just don't have the motivation to go regularly.\n"
            "Advisor: I completely understand. Many of our clients face the same challenge. At FitNova, we design personalized programs that fit your schedule. How much time can you commit to exercise each week?\n"
            "Customer: Maybe three to four days a week, about 45 minutes each.\n"
            "Advisor: That's perfect for our program. And just so you know, if you sign up today there's a 20% discount available.\n"
            "Customer: That sounds interesting. How much does it cost?\n"
            "Advisor: Our premium plan is Rs.15,000 for three months.\n"
            "Customer: Guaranteed results? I've heard that before and it didn't work out.\n"
            "Advisor: I assure you, our program is different. Let me book you a free trial session for this Saturday at 10 AM.\n"
            "Customer: Okay, let's try the trial session first.\n"
            "Advisor: Perfect! I'll send you the details.\n"
        ),
    },
    {
        "id": "DEMO-002",
        "advisor_email": "rahul@fitnova.in",
        "script": (
            "Advisor: Hi, this is Rahul from FitNova. I'm calling about the inquiry you submitted.\n"
            "Customer: Oh, yes. I was looking at your website. Can you tell me more about the programs?\n"
            "Advisor: Sure, we have multiple plans. But first, tell me a bit about yourself. What's your fitness goal?\n"
            "Customer: I want to build muscle and get stronger.\n"
            "Advisor: Great goal. Do you have any experience with strength training?\n"
            "Customer: Some, but I've never worked with a coach.\n"
            "Advisor: That's exactly where we add value. I'd recommend our premium coaching plan at Rs.12,000 per quarter.\n"
            "Customer: That sounds reasonable.\n"
            "Advisor: Would you like to book a free trial session? Tomorrow at 6 PM works?\n"
            "Customer: Yes.\n"
            "Advisor: Perfect. You'll get a confirmation message shortly.\n"
        ),
    },
    {
        "id": "DEMO-BAD-003",
        "advisor_email": "priya@fitnova.in",
        "script": (
            "Advisor: Hello, is this Mr. Gupta? I'm calling from FitNova.\n"
            "Customer: Yes, speaking.\n"
            "Advisor: Great, I'm calling about our premium fitness program.\n"
            "Customer: What does it include?\n"
            "Advisor: Everything - personalized training, diet plans, yoga. If you join today, I can give you a special rate of just Rs.10,000.\n"
            "Customer: That seems like a lot. How is this different from a regular gym?\n"
            "Advisor: Our results speak for themselves. We guarantee you'll lose at least 5 kg in the first month.\n"
            "Customer: Can I think about it and call you back?\n"
            "Advisor: The offer expires today. I can hold the slot for the next 2 hours.\n"
            "Customer: Let me discuss with my spouse.\n"
            "Advisor: Okay, but I can't guarantee the price after today.\n"
        ),
    },
    {
        "id": "DEMO-HING-004",
        "advisor_email": "rahul@fitnova.in",
        "script": (
            "Advisor: Namaste, main Rahul FitNova se bol raha hoon.\n"
            "Customer: Haan, Vikram bol raha hoon.\n"
            "Advisor: Aapne fitness inquiry kiya tha na? Aap ke goals kya hain?\n"
            "Customer: Ha ji, main weight loss karna chahta hoon.\n"
            "Advisor: Main samajh gaya. Aap roz kitna time de sakte hain?\n"
            "Customer: 30-40 minutes, 4 days a week.\n"
            "Advisor: Perfect! We have a great plan for you at Rs.12,000 for three months.\n"
            "Customer: Achha, trial free hai?\n"
            "Advisor: Bilkul. I can book you for Saturday at 10 AM.\n"
            "Customer: Haan, bhej do. Thank you!\n"
        ),
    },
]

db = get_session()
try:
    for call in SAMPLE_CALLS:
        audio_path = incoming / f"call_{call['id']}.mp3"
        if not audio_path.exists():
            audio_path.write_bytes(call["script"].encode("utf-8"))
            meta_path = incoming / f"call_{call['id']}.json"
            meta_path.write_text(json.dumps({"external_call_id": call["id"], "advisor_email": call["advisor_email"], "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "audio_file": f"call_{call['id']}.mp3"}, indent=2), encoding="utf-8")
        existing = db.query(Call).filter(Call.external_call_id == call["id"]).first()
        if existing:
            continue
        advisor = db.query(Advisor).filter(Advisor.email == call["advisor_email"]).first()
        if not advisor:
            continue
        try:
            source = FolderSource("fitnova/data/incoming")
            match = source.fetch_new_calls()
            match_obj = next((m for m in match if m.external_call_id == call["id"]), None)
            audio_bytes = source.get_audio_bytes(match_obj) if match_obj else call["script"].encode("utf-8")
            run_pipeline(external_call_id=call["id"], advisor_id=advisor.id, source_type="folder", audio_bytes=audio_bytes, db=db)
        except Exception:
            pass
finally:
    db.close()

import uvicorn
port = int(os.getenv("PORT", "8000"))
uvicorn.run("fitnova.api.main:app", host="0.0.0.0", port=port, log_level="info")
