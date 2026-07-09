import hashlib
import logging

from sqlalchemy.orm import Session
from fitnova.storage.models import Call

logger = logging.getLogger(__name__)


def compute_audio_hash(audio_bytes: bytes) -> str:
    return hashlib.sha256(audio_bytes).hexdigest()


def is_already_processed(session: Session, audio_hash: str) -> bool:
    return session.query(Call).filter(Call.audio_hash == audio_hash).first() is not None
