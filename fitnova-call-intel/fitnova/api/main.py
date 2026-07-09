"""Minimal FastAPI surface for the call intelligence pipeline."""

import json
import logging
from fastapi import FastAPI, HTTPException
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

logger = logging.getLogger(__name__)

app = FastAPI(title="FitNova Call Intelligence", version="1.1.0")
app.add_middleware(RateLimitMiddleware)


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

@app.get("/health")
def health():
    response_cache.cache_invalidate("org_summary")
    return {"status": "ok"}


@app.get("/incoming/list")
def list_incoming():
    source = FolderSource("fitnova/data/incoming")
    calls = source.fetch_new_calls()
    return {"incoming_ids": [c.external_call_id for c in calls]}


@app.post("/calls/process", response_model=ProcessResponse)
def process_call_endpoint(external_call_id: str):
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
def get_task_status(task_id: str):
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
def get_call_detail(call_id: int):
    cache_key = f"call_detail:{call_id}"
    cached = response_cache.cache_get(cache_key)
    if cached:
        return CallDetail(**cached)

    db = get_session()
    try:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
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
def org_summary(org_id: int):
    cache_key = f"org_summary:{org_id}"
    cached = response_cache.cache_get(cache_key)
    if cached:
        return cached

    db = get_session()
    try:
        org = db.query(Org).filter(Org.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404)
        averages = get_org_average(org_id)
        teams = []
        for t in org.teams:
            teams.append({"id": t.id, "name": t.name, "averages": get_team_average(t.id)})
        result = {"org": org.name, "averages": averages, "teams": teams}
        response_cache.cache_set(cache_key, result, ttl=30)
        return result
    finally:
        db.close()


@app.get("/teams/{team_id}/summary")
def team_summary(team_id: int):
    cache_key = f"team_summary:{team_id}"
    cached = response_cache.cache_get(cache_key)
    if cached:
        return cached

    db = get_session()
    try:
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404)
        averages = get_team_average(team_id)
        advisors = []
        for a in team.advisors:
            advisors.append({"id": a.id, "name": a.name, "averages": get_advisor_average(a.id)})
        result = {"team": team.name, "averages": averages, "advisors": advisors}
        response_cache.cache_set(cache_key, result, ttl=30)
        return result
    finally:
        db.close()


@app.get("/advisors/{advisor_id}/summary")
def advisor_summary(advisor_id: int):
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
def contest_tag(tag_id: int, body: ContestRequest):
    db = get_session()
    try:
        tag = db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
        tag.status = TagStatus.contested.value
        db.add(Contest(tag_id=tag.id, advisor_comment=body.advisor_comment))
        db.commit()
        # Invalidate caches that may include this tag
        response_cache.cache_invalidate("call_detail")
        response_cache.cache_invalidate("org_summary")
        return {"status": "contested", "tag_id": tag_id}
    finally:
        db.close()
