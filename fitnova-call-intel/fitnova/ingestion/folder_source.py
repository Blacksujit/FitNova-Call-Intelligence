import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from .base import CallSource, CallMetadata

logger = logging.getLogger(__name__)


class FolderSource(CallSource):
    """Reads calls from a local folder where each call is a pair of files:
    call_<id>.wav/.mp3 and call_<id>.json (metadata).
    """

    def __init__(self, folder: str):
        self.folder = Path(folder)
        if not self.folder.is_dir():
            raise NotADirectoryError(f"data/incoming/ not found at {self.folder}")
        self._processed_ids: set[str] = set()

    def fetch_new_calls(self) -> list[CallMetadata]:
        results: list[CallMetadata] = []
        seen_audio: set[str] = set()

        for f in self.folder.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() in (".wav", ".mp3", ".m4a", ".ogg"):
                stem = f.stem
                seen_audio.add(stem)

        for stem in seen_audio:
            if stem in self._processed_ids:
                continue
            meta_path = self.folder / f"{stem}.json"
            audio_candidates = []
            for ext in (".wav", ".mp3", ".m4a", ".ogg"):
                p = self.folder / f"{stem}{ext}"
                if p.is_file():
                    audio_candidates.append(p)
            if not audio_candidates:
                logger.warning("Skipping %s — no audio file found for metadata", stem)
                continue
            if not meta_path.is_file():
                logger.warning("Skipping %s — no metadata JSON found", stem)
                continue

            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Skipping %s — bad metadata JSON: %s", stem, e)
                continue

            occurred_at = datetime.fromisoformat(meta.get("occurred_at", datetime.utcnow().isoformat()))
            results.append(CallMetadata(
                external_call_id=meta.get("external_call_id", stem),
                advisor_email=meta.get("advisor_email", ""),
                audio_path_or_url=str(audio_candidates[0]),
                source_type="folder",
                occurred_at=occurred_at,
            ))
            self._processed_ids.add(stem)

        return results

    def get_audio_bytes(self, call: CallMetadata) -> bytes:
        path = Path(call.audio_path_or_url)
        return path.read_bytes()
