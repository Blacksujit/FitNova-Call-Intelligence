"""
Stub implementations of CallSource for CRM and telephony integrations.
These exist to prove the adapter interface is source-agnostic.
Each raises NotImplementedError with a docstring describing what a real
integration would need.
"""

from .base import CallSource, CallMetadata


class CRMSource(CallSource):
    """
    Real implementation would poll the CRM's API (e.g. HubSpot, Salesforce)
    for calls logged against contacts/deals. The CRM usually exposes a
    REST endpoint like /calls with pagination (cursor or offset/limit) and
    a 'since' timestamp filter. Calls arrive with a recording URL and
    metadata (owner email, contact phone, call duration). Auth is OAuth2
    client-credentials or API key. The source would poll on a cron schedule
    (every 5 min) and fetch new recordings since last poll. Requires a
    state store (cursor or timestamp) to avoid re-fetching.
    """

    def fetch_new_calls(self) -> list[CallMetadata]:
        raise NotImplementedError(
            "CRMSource: wire up HubSpot/Salesforce API with OAuth2 + "
            "cursor-based pagination. See class docstring."
        )

    def get_audio_bytes(self, call: CallMetadata) -> bytes:
        raise NotImplementedError(
            "CRMSource: download the recording from the signed URL returned "
            "by the CRM's /calls/{id}/recording endpoint."
        )


class TelephonySource(CallSource):
    """
    Real implementation would subscribe to webhooks from the telephony
    provider (Twilio, Exotel, Knowlarity) for call-completed events.
    The provider sends a POST to a configured endpoint with CallSid,
    RecordingUrl, caller/callee numbers, and duration. The source handler
    fetches the recording from RecordingUrl and creates a CallMetadata.
    Requires a public HTTPS endpoint (or polling fallback). Diarization
    quality depends on whether the provider delivers stereo or mono — if
    mono, the transcription step handles fallback.
    """

    def fetch_new_calls(self) -> list[CallMetadata]:
        raise NotImplementedError(
            "TelephonySource: set up a webhook endpoint (FastAPI route) "
            "registered with Twilio/Exotel for voice webhooks. See docstring."
        )

    def get_audio_bytes(self, call: CallMetadata) -> bytes:
        raise NotImplementedError(
            "TelephonySource: HTTP GET the RecordingUrl from the provider's "
            "event payload. May need basic auth or signed URL."
        )
