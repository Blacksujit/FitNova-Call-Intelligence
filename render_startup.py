import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

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
Advisor: Our premium plan is Rs.15,000 for three months. But honestly, with our program you'll see guaranteed results. Many of our clients lose 10-15 kg in the first two months.
Customer: Guaranteed results? I've heard that before and it didn't work out.
Advisor: I assure you, our program is different. This offer won't be available for long though. Let me book you a free trial session for this Saturday at 10 AM.
Customer: Okay, let's try the trial session first.
Advisor: Perfect! I'll send you the details. Also, there are some additional charges for the diet plan that I should mention — Rs.2,000 per month, optional.
Customer: Alright, that seems fair. Let's proceed.
Advisor: Excellent! You'll receive a confirmation via WhatsApp. Have a great day!
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
Advisor: That's exactly where we add value. I'd recommend our premium coaching plan at Rs.12,000 per quarter. It includes personalized workouts, nutrition guidance, and weekly check-ins.
Customer: That sounds reasonable.
Advisor: Would you like to book a free trial session? We have slots available tomorrow at 6 PM or Wednesday at 7 AM.
Customer: Tomorrow at 6 PM works.
Advisor: Perfect. You'll get a confirmation message shortly. Looking forward to seeing you!
""",
    },
    {
        "id": "DEMO-BAD-003",
        "advisor_email": "priya@fitnova.in",
        "script": """
Advisor: Hello, is this Mr. Gupta? I'm calling from FitNova.
Customer: Yes, speaking.
Advisor: Great, I'm calling about our premium fitness program. It's the best in Bangalore and we're running a limited-time offer.
Customer: What does it include?
Advisor: Everything — personalized training, diet plans, yoga, you name it. If you join today, I can give you a special rate of just Rs.10,000. This price won't be available tomorrow.
Customer: That seems like a lot. How is this different from a regular gym?
Advisor: Our results speak for themselves. We guarantee you'll lose at least 5 kg in the first month or your money back. We've never had a client who didn't achieve their goals. I have two other people interested in this same slot, so I'd recommend deciding now.
Customer: Can I think about it and call you back?
Advisor: The offer expires today. I can hold the slot for the next 2 hours if you're serious.
Customer: Let me discuss with my spouse and get back to you.
Advisor: Okay, but I can't guarantee the price after today. I'll send you the details on WhatsApp.
""",
    },
    {
        "id": "DEMO-HING-004",
        "advisor_email": "rahul@fitnova.in",
        "script": """
Advisor: Namaste, main Rahul FitNova se bol raha hoon. Kya main Vikram ji se baat kar raha hoon?
Customer: Haan, Vikram bol raha hoon.
Advisor: Aapne fitness inquiry kiya tha na? Aap ke goals kya hain?
Customer: Ha ji, main weight loss karna chahta hoon. Past 6 months se koshish kar raha hoon par koi result nahi.
Advisor: Main samajh gaya. Aap roz kitna time de sakte hain?
Customer: I can do 30-40 minutes, 4 days a week maximum.
Advisor: Perfect! We have a great plan for you. It's Rs.12,000 for three months, includes personalized coaching, diet plan, everything.
Customer: Aur kya kya milega ismein?
Advisor: Weekly check-in, habit coaching, aur free trial — you can try first class free.
Customer: Achha, trial free hai? Let's try that first.
Advisor: Bilkul. I can book you for Saturday at 10 AM. Shall I send details on WhatsApp?
Customer: Haan, bhej do. Thank you!
Advisor: Welcome ji! Confirmation aapke WhatsApp par aayegi.
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
    init_db()
    seed_db()

    incoming = Path("fitnova/data/incoming")
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
                print(f"  Skipping {call['id']} — advisor {call['advisor_email']} not found.")
                continue
            try:
                result = run_pipeline(
                    external_call_id=call["id"],
                    advisor_id=advisor.id,
                    source_type="folder",
                    audio_bytes=call["script"].encode("utf-8"),
                    db=db,
                )
                print(f"  {call['id']}: {result['status']} — scores={result.get('scores', 0)} tags={result.get('tags', 0)}")
            except Exception as e:
                print(f"  {call['id']}: FAILED — {e}")
    finally:
        db.close()
    print("Startup seeding complete.")


if __name__ == "__main__":
    seed_and_process()

    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("fitnova.api.main:app", host="0.0.0.0", port=port, log_level="info")
