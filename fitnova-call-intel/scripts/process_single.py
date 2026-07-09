"""Process a single incoming call through the real pipeline.

Usage:
    python scripts/process_single.py REAL-001

This reads data/incoming/call_REAL-001.mp3 + call_REAL-001.json,
runs real AssemblyAI + Anthropic, and stores results in the DB.

Set ASSEMBLYAI_API_KEY and ANTHROPIC_API_KEY in .env first.
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fitnova.storage.db import init_db, get_session
from fitnova.storage.models import Advisor
from fitnova.pipeline.orchestrator import process_call

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

INCOMING = Path("fitnova/data/incoming")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/process_single.py CALL_ID")
        print("Example: python scripts/process_single.py REAL-001")
        sys.exit(1)

    call_id = sys.argv[1]
    call_id = Path(call_id).stem.replace("call_", "")

    meta_file = INCOMING / f"call_{call_id}.json"
    audio_file = None
    for ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]:
        candidate = INCOMING / f"call_{call_id}{ext}"
        if candidate.exists():
            audio_file = candidate
            break

    if not meta_file.exists():
        print(f"Metadata file not found: {meta_file}")
        sys.exit(1)
    if not audio_file:
        print(f"No audio file found for call_{call_id} (tried .mp3, .wav, .m4a, .ogg, .flac)")
        sys.exit(1)

    with open(meta_file) as f:
        meta = json.load(f)

    audio_bytes = audio_file.read_bytes()
    print(f"Processing {call_id} ({audio_file.stat().st_size / 1024:.1f} KB, advisor={meta['advisor_email']})...")
    print("This will call AssemblyAI + Anthropic. May take 10-30s.")

    init_db()
    db = get_session()
    advisor = db.query(Advisor).filter(Advisor.email == meta["advisor_email"]).first()
    if not advisor:
        print(f"Advisor {meta['advisor_email']} not found in DB. Seed first: python scripts/run_demo.py")
        db.close()
        sys.exit(1)

    try:
        start = time.time()
        result = process_call(
            external_call_id=call_id,
            advisor_id=advisor.id,
            source_type="api",
            audio_bytes=audio_bytes,
            db=db,
        )
        elapsed = time.time() - start
        print(f"\nDone in {elapsed:.1f}s: {result}")
    except Exception as e:
        print(f"FAILED: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
