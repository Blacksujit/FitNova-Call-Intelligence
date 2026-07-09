import os
import logging
import assemblyai as aai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def transcribe_and_diarize(audio_bytes: bytes, call_id: str) -> list[dict]:
    """
    Transcribe audio using AssemblyAI with speaker diarisation.
    Returns a list of segment dicts: {speaker, start_ms, end_ms, text}.

    Speaker mapping heuristic: the speaker who speaks first is assumed to be
    the advisor (advisors initiate outbound calls). This is a simplifying
    assumption — in production, match against known advisor voice profiles
    or use the CRM's caller/callee field.
    """
    api_key = os.getenv("ASSEMBLYAI_API_KEY", "")
    if not api_key:
        logger.warning("ASSEMBLYAI_API_KEY not set — falling back to stub transcription.")
        return _stub_transcript(audio_bytes)

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_detection=True,
        speech_models=["universal-3-5-pro", "universal-2"],
        prompt=(
            "Sales consultation call between a FitNova fitness advisor "
            "and a prospective customer discussing fitness goals, "
            "coaching programs, pricing, and sign-up. "
            "May contain Hinglish (Hindi-English mix) — preserve both languages."
        ),
        keyterms_prompt=[
            "FitNova", "FatCommandos", "Weight Loss Commandos",
            "personal training", "nutrition plan", "coaching program",
            "free trial", "transformation", "body recomposition",
            "macro tracking", "habit coaching", "accountability call",
        ],
        redact_pii=True,
        redact_pii_policies=[
            aai.PIIRedactionPolicy.person_name,
            aai.PIIRedactionPolicy.phone_number,
            aai.PIIRedactionPolicy.email_address,
            aai.PIIRedactionPolicy.location,
            aai.PIIRedactionPolicy.banking_information,
            aai.PIIRedactionPolicy.credit_card_number,
        ],
        redact_pii_sub=aai.PIISubstitutionPolicy.entity_name,
    )

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_bytes, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

    segments: list[dict] = []

    if not transcript.utterances or len(transcript.utterances) < 2:
        # ── Poor diarization fallback ───────────────────────────────────
        logger.warning("Call %s: poor diarization (%d speakers), tagging as unknown.", call_id, len(transcript.utterances or []))
        for utt in transcript.utterances or []:
            segments.append({
                "speaker": "unknown",
                "start_ms": utt.start,
                "end_ms": utt.end,
                "text": utt.text,
            })
        return segments

    # ── Map speaker labels ──────────────────────────────────────────────
    raw_speakers = sorted({utt.speaker for utt in transcript.utterances})
    first_speaker = transcript.utterances[0].speaker
    speaker_map = {first_speaker: "advisor"}
    for spk in raw_speakers:
        if spk not in speaker_map:
            speaker_map[spk] = "customer"

    for utt in transcript.utterances:
        segments.append({
            "speaker": speaker_map.get(utt.speaker, "unknown"),
            "start_ms": utt.start,
            "end_ms": utt.end,
            "text": utt.text,
        })

    return segments


def _stub_transcript(audio_bytes: bytes | None = None) -> list[dict]:
    """
    Fallback stub used when no API key is configured.
    If audio_bytes is UTF-8 text (script format), parse it into segments.
    Otherwise return a hardcoded demo transcript.
    """
    if audio_bytes:
        try:
            text = audio_bytes.decode("utf-8").strip()
            if text:
                return _parse_script_text(text)
        except (UnicodeDecodeError, ValueError):
            pass
    return [
        {"speaker": "advisor", "start_ms": 0, "end_ms": 3000, "text": "Hello, this is Priya from FitNova."},
        {"speaker": "customer", "start_ms": 3500, "end_ms": 6000, "text": "Hi, I'm interested in your coaching program."},
        {"speaker": "advisor", "start_ms": 6500, "end_ms": 12000, "text": "Great, let me ask about your fitness goals first."},
    ]


def _parse_script_text(text: str) -> list[dict]:
    """
    Parse a simple script format:
        Advisor: <text>
        Customer: <text>
    into segments with approximate timestamps.
    """
    lines = text.strip().split("\n")
    segments = []
    ms = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        speaker = "unknown"
        if line.lower().startswith("advisor"):
            speaker = "advisor"
            content = line.split(":", 1)[1].strip() if ":" in line else line
        elif line.lower().startswith("customer"):
            speaker = "customer"
            content = line.split(":", 1)[1].strip() if ":" in line else line
        else:
            content = line

        word_count = len(content.split())
        duration_ms = max(2000, word_count * 200)  # ~200ms per word, min 2s
        segments.append({
            "speaker": speaker,
            "start_ms": ms,
            "end_ms": ms + duration_ms,
            "text": content,
        })
        ms += duration_ms + 500  # 500ms gap between utterances
    return segments
