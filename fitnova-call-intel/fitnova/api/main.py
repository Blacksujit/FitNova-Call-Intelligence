"""Minimal FastAPI surface for the call intelligence pipeline."""

import json
import logging
import time
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from fitnova.storage.db import get_session, get_advisor_average, get_team_average, get_org_average
from fitnova.storage.models import (
    Org, Team, Advisor, Call, Segment, Score, Tag, Contest, TagStatus,
)
from fitnova.pipeline.orchestrator import process_call as run_pipeline
from fitnova.ingestion.folder_source import FolderSource

from .ratelimit import RateLimitMiddleware
from . import queue as task_queue
from . import cache as response_cache
from .auth import router as auth_router
from .dependencies import get_current_user, can_access_org, can_access_team, can_access_advisor, can_access_call

logger = logging.getLogger(__name__)

app = FastAPI(title="FitNova Call Intelligence", version="1.2.0")
app.add_middleware(RateLimitMiddleware)
app.include_router(auth_router)


# ── Schemas ────────────────────────────────────────────────────────────

class ProcessResponse(BaseModel):
    status: str
    external_call_id: str
    scores: int = 0
    tags: int = 0


class ContestRequest(BaseModel):
    advisor_comment: str


class CallDetail(BaseModel):
    id: int
    external_call_id: str
    advisor_name: str
    status: str
    diarization_quality: str | None
    source_type: str
    segments: list[dict]
    scores: list[dict]
    tags: list[dict]

    class Config:
        from_attributes = True


# ── Endpoints ──────────────────────────────────────────────────────────

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


@app.get("/health")
def health():
    response_cache.cache_invalidate("org_summary")
    return {"status": "ok"}


@app.post("/startup/seed")
def startup_seed():
    """Seed the database with demo data and process sample calls."""
    from scripts.seed_data import seed as _seed_db
    _seed_db()

    incoming = Path("fitnova/data/incoming")
    incoming.mkdir(parents=True, exist_ok=True)

    for call in SAMPLE_CALLS:
        audio_path = incoming / f"call_{call['id']}.mp3"
        if not audio_path.exists():
            audio_path.write_bytes(call["script"].encode("utf-8"))
            meta = {
                "external_call_id": call["id"],
                "advisor_email": call["advisor_email"],
                "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                "audio_file": f"call_{call['id']}.mp3",
            }
            meta_path = incoming / f"call_{call['id']}.json"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    db = get_session()
    results = []
    try:
        source = FolderSource("fitnova/data/incoming")
        for call in SAMPLE_CALLS:
            existing = db.query(Call).filter(Call.external_call_id == call["id"]).first()
            if existing:
                results.append({"id": call["id"], "status": "already_processed"})
                continue
            advisor = db.query(Advisor).filter(Advisor.email == call["advisor_email"]).first()
            if not advisor:
                results.append({"id": call["id"], "status": "advisor_not_found"})
                continue
            try:
                match = source.fetch_new_calls()
                match_obj = next((m for m in match if m.external_call_id == call["id"]), None)
                audio_bytes = source.get_audio_bytes(match_obj) if match_obj else call["script"].encode("utf-8")
                result = run_pipeline(
                    external_call_id=call["id"],
                    advisor_id=advisor.id,
                    source_type="folder",
                    audio_bytes=audio_bytes,
                    db=db,
                )
                results.append({"id": call["id"], "status": result.get("status", "done")})
            except Exception as e:
                results.append({"id": call["id"], "status": f"failed: {e}"})
    finally:
        db.close()

    response_cache.cache_invalidate("call_detail")
    response_cache.cache_invalidate("org_summary")
    response_cache.cache_invalidate("team_summary")
    response_cache.cache_invalidate("advisor_summary")

    return {"status": "ok", "results": results}


@app.post("/calls/upload")
async def upload_call(
    file: UploadFile = File(...),
    advisor_email: str = Form(...),
    external_call_id: str = Form(""),
    current_user: dict = Depends(get_current_user),
):
    import uuid, shutil
    cid = external_call_id.strip() or f"UPLOAD-{uuid.uuid4().hex[:8].upper()}"
    incoming = Path("fitnova/data/incoming")
    incoming.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix if file.filename else ".wav"
    audio_name = f"call_{cid}{ext}"
    audio_path = incoming / audio_name
    with audio_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    meta = {
        "external_call_id": cid,
        "advisor_email": advisor_email,
        "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "audio_file": audio_name,
    }
    (incoming / f"call_{cid}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"status": "ok", "external_call_id": cid}


@app.get("/incoming/list")
def list_incoming(current_user: dict = Depends(get_current_user)):
    source = FolderSource("fitnova/data/incoming")
    calls = source.fetch_new_calls()
    return {"incoming_ids": [c.external_call_id for c in calls]}


@app.post("/calls/process", response_model=ProcessResponse)
def process_call_endpoint(external_call_id: str, current_user: dict = Depends(get_current_user)):
    """
    Process a call synchronously (fast path — used when rate limit allows).
    When rate-limited, the middleware intercepts and returns 202 queued instead.
    """
    db = get_session()
    try:
        source = FolderSource("fitnova/data/incoming")
        calls = source.fetch_new_calls()
        match = None
        for c in calls:
            if c.external_call_id == external_call_id:
                match = c
                break

        if not match:
            raise HTTPException(status_code=404, detail=f"Call {external_call_id} not found in incoming/")

        advisor = db.query(Advisor).filter(Advisor.email == match.advisor_email).first()
        if not advisor:
            raise HTTPException(status_code=400, detail=f"Advisor with email {match.advisor_email} not found in DB")

        audio_bytes = source.get_audio_bytes(match)
        result = run_pipeline(
            external_call_id=external_call_id,
            advisor_id=advisor.id,
            source_type=match.source_type,
            audio_bytes=audio_bytes,
            db=db,
        )
        response_cache.cache_invalidate(f"call_detail")
        response_cache.cache_invalidate("org_summary")
        response_cache.cache_invalidate("team_summary")
        response_cache.cache_invalidate("advisor_summary")
        return ProcessResponse(**result)
    finally:
        db.close()


@app.get("/tasks/{task_id}")
def get_task_status(task_id: str, current_user: dict = Depends(get_current_user)):
    """Poll the status of an async queued task."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task.id,
        "status": task.status,
        "error": task.error,
        "result": json.loads(task.result) if task.result else None,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }


@app.get("/calls/{call_id}", response_model=CallDetail)
def get_call_detail(call_id: int, current_user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        if not can_access_call(current_user, call_id):
            raise HTTPException(status_code=403, detail="Not authorized to view this call")

        cache_key = f"call_detail:{call_id}"
        cached = response_cache.cache_get(cache_key)
        if cached:
            return CallDetail(**cached)

        result = CallDetail(
            id=call.id,
            external_call_id=call.external_call_id,
            advisor_name=call.advisor.name,
            status=call.status,
            diarization_quality=call.diarization_quality,
            source_type=call.source_type,
            segments=[{"speaker": s.speaker, "start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text} for s in call.segments],
            scores=[{"dimension": sc.dimension, "value": sc.value} for sc in call.scores],
            tags=[{"id": t.id, "category": t.category, "severity": t.severity, "quoted_line": t.quoted_line, "reason": t.reason, "status": t.status} for t in call.tags],
        )
        response_cache.cache_set(cache_key, result.model_dump(), ttl=60)
        return result
    finally:
        db.close()


@app.get("/orgs/{org_id}/summary")
def org_summary(org_id: int, current_user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        org = db.query(Org).filter(Org.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404)
        if not can_access_org(current_user, org_id):
            raise HTTPException(status_code=403, detail="Not authorized to view this org")

        cache_key = f"org_summary:{org_id}"
        cached = response_cache.cache_get(cache_key)
        if cached:
            return cached

        averages = get_org_average(org_id)
        teams = []
        for t in org.teams:
            if current_user["role"] == "team_leader" and t.id != current_user.get("team_id"):
                continue
            teams.append({"id": t.id, "name": t.name, "averages": get_team_average(t.id)})
        result = {"org": org.name, "averages": averages, "teams": teams}
        response_cache.cache_set(cache_key, result, ttl=30)
        return result
    finally:
        db.close()


@app.get("/teams/{team_id}/summary")
def team_summary(team_id: int, current_user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404)
        if not can_access_team(current_user, team_id):
            raise HTTPException(status_code=403, detail="Not authorized to view this team")

        cache_key = f"team_summary:{team_id}"
        cached = response_cache.cache_get(cache_key)
        if cached:
            return cached
        averages = get_team_average(team_id)
        advisors = []
        for a in team.advisors:
            if current_user["role"] == "advisor" and a.id != current_user.get("advisor_id"):
                continue
            advisors.append({"id": a.id, "name": a.name, "averages": get_advisor_average(a.id)})
        result = {"team": team.name, "averages": averages, "advisors": advisors}
        response_cache.cache_set(cache_key, result, ttl=30)
        return result
    finally:
        db.close()


@app.get("/advisors/{advisor_id}/summary")
def advisor_summary(advisor_id: int, current_user: dict = Depends(get_current_user)):
    if not can_access_advisor(current_user, advisor_id):
        raise HTTPException(status_code=403, detail="Not authorized to view this advisor")

    cache_key = f"advisor_summary:{advisor_id}"
    cached = response_cache.cache_get(cache_key)
    if cached:
        return cached

    db = get_session()
    try:
        advisor = db.query(Advisor).filter(Advisor.id == advisor_id).first()
        if not advisor:
            raise HTTPException(status_code=404)
        averages = get_advisor_average(advisor_id)
        calls = db.query(Call).filter(Call.advisor_id == advisor_id).order_by(Call.created_at.desc()).all()
        result = {
            "advisor": advisor.name,
            "team": advisor.team.name,
            "averages": averages,
            "calls": [{"id": c.id, "external_call_id": c.external_call_id, "status": c.status, "diarization_quality": c.diarization_quality} for c in calls],
        }
        response_cache.cache_set(cache_key, result, ttl=30)
        return result
    finally:
        db.close()


@app.post("/tags/{tag_id}/contest")
def contest_tag(tag_id: int, body: ContestRequest, current_user: dict = Depends(get_current_user)):
    db = get_session()
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
        if current_user["role"] not in ("advisor", "team_leader"):
            raise HTTPException(status_code=403, detail="Only advisors and team leaders can contest tags")

        if current_user["role"] == "advisor" and tag.call.advisor_id != current_user.get("advisor_id"):
            raise HTTPException(status_code=403, detail="Can only contest tags on your own calls")

        if current_user["role"] == "team_leader":
            call_advisor = db.query(Advisor).filter(Advisor.id == tag.call.advisor_id).first()
            if not call_advisor or call_advisor.team_id != current_user.get("team_id"):
                raise HTTPException(status_code=403, detail="Can only contest tags in your team")

        tag.status = TagStatus.contested.value
        db.add(Contest(tag_id=tag.id, advisor_comment=body.advisor_comment))
        db.commit()
        response_cache.cache_invalidate("call_detail")
        response_cache.cache_invalidate("org_summary")
        return {"status": "contested", "tag_id": tag_id}
    finally:
        db.close()
