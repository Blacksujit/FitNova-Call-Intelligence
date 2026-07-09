from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CallMetadata:
    external_call_id: str
    advisor_email: str
    audio_path_or_url: str
    source_type: str
    occurred_at: datetime


class CallSource(ABC):
    @abstractmethod
    def fetch_new_calls(self) -> list[CallMetadata]:
        ...

    @abstractmethod
    def get_audio_bytes(self, call: CallMetadata) -> bytes:
        ...
