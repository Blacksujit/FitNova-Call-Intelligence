import logging
from datetime import datetime

from sqlalchemy.orm import Session

from fitnova.storage.models import Call, Segment, Score, Tag, CallStatus
from fitnova.pipeline.idempotency import compute_audio_hash, is_already_processed
from fitnova.pipeline.transcribe import transcribe_and_diarize
from fitnova.analysis.tagger import analyze_call

logger = logging.getLogger(__name__)


def process_call(
    external_call_id: str,
    advisor_id: int,
    source_type: str,
    audio_bytes: bytes,
    db: Session,
) -> dict:
    audio_hash = compute_audio_hash(audio_bytes)

    if is_already_processed(db, audio_hash):
        logger.info("Call %s already processed (hash %s), skipping.", external_call_id, audio_hash[:12])
        return {"status": "skipped", "external_call_id": external_call_id}

    call = Call(
        advisor_id=advisor_id,
        source_type=source_type,
        external_call_id=external_call_id,
        audio_hash=audio_hash,
        status=CallStatus.ingested.value,
    )
    db.add(call)
    db.commit()

    try:
        # ── Step 1: Transcribe ──────────────────────────────────────────
        segments = transcribe_and_diarize(audio_bytes, external_call_id)
        call.status = CallStatus.transcribed.value

        all_known = True
        for seg in segments:
            if seg["speaker"] == "unknown":
                all_known = False
            db.add(Segment(
                call_id=call.id,
                speaker=seg["speaker"],
                start_ms=seg["start_ms"],
                end_ms=seg["end_ms"],
                text=seg["text"],
            ))
        call.diarization_quality = "ok" if all_known else "failed"
        db.commit()

        # ── Step 2: Analyze ─────────────────────────────────────────────
        analysis = analyze_call(segments, external_call_id)

        if not analysis.get("is_sales_call", True):
            call.status = CallStatus.non_sales_call.value
            db.commit()
            logger.info("Call %s classified as non-sales, skipping scoring.", external_call_id)
            return {"status": "non_sales_call", "external_call_id": external_call_id}

        for sc in analysis["scores"]:
            db.add(Score(call_id=call.id, dimension=sc["dimension"], value=sc["value"]))

        for tg in analysis["tags"]:
            db.add(Tag(
                call_id=call.id,
                category=tg["category"],
                severity=tg["severity"],
                timestamp_ms=tg.get("timestamp_ms"),
                quoted_line=tg.get("quoted_line"),
                reason=tg.get("reason"),
            ))

        call.status = CallStatus.analyzed.value
        call.processed_at = datetime.utcnow()
        db.commit()

        return {
            "status": "analyzed",
            "external_call_id": external_call_id,
            "scores": len(analysis["scores"]),
            "tags": len(analysis["tags"]),
        }

    except Exception:
        call.status = CallStatus.failed.value
        db.commit()
        logger.exception("Call %s failed at stage %s", external_call_id, call.status)
        raise
