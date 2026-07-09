"""
Transcription with automatic fallback:
  1. ASSEMBLYAI_API_KEY set  → AssemblyAI (paid, diarization)
  2. ASSEMBLYAI_API_KEY not set → faster-whisper (local, free, no diarization)
  3. Neither available → stub (demo scripts / hardcoded text)

Swap back to paid: just set the env var. No code changes needed.
"""

import os
import logging
import tempfile
import shutil

import numpy as np
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── public entry point ──────────────────────────────────────────────────


def _is_audio_bytes(raw: bytes) -> bool:
    """Detect whether bytes look like audio (WAV/MP3/FLAC/etc) vs text stub data."""
    if len(raw) < 16:
        return False
    magic = raw[:4]
    if magic in (b"RIFF", b"ID3\x03", b"ID3\x04", b"fLaC", b"OggS", b"\xff\xfb", b"\xff\xf3", b"\xff\xe3"):
        return True
    if raw[:2] == b"\xff\xfb" or raw[:2] == b"\xff\xf3" or raw[:2] == b"\xff\xe3":
        return True
    return False


def transcribe_and_diarize(audio_bytes: bytes, call_id: str) -> list[dict]:
    """
    Transcribe audio. Returns list of {speaker, start_ms, end_ms, text}.

    Resolution order:
      1. AssemblyAI  (if ASSEMBLYAI_API_KEY is set + real audio)
      2. faster-whisper  (local, free, pip install faster-whisper, real audio only)
      3. Stub  (script-text mode or hardcoded demo)
    """
    if not _is_audio_bytes(audio_bytes):
        return _stub_transcript(audio_bytes)

    api_key = os.getenv("ASSEMBLYAI_API_KEY", "")
    if api_key:
        try:
            segments = _transcribe_assemblyai(audio_bytes, call_id, api_key)
            if segments:
                return segments
            logger.warning("AssemblyAI returned poor diarization (0 utterances), falling back to whisper.")
        except Exception as exc:
            logger.warning("AssemblyAI failed (%s), falling back to whisper.", exc)

    if _whisper_available():
        return _transcribe_whisper(audio_bytes, call_id)

    return _stub_transcript(audio_bytes)


# ── option 1: AssemblyAI (paid, full diarization) ───────────────────────


def _transcribe_assemblyai(audio_bytes: bytes, call_id: str, api_key: str) -> list[dict]:
    import httpx
    import assemblyai as aai

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

    # Manual upload with long timeout for large WAVs
    with httpx.Client(timeout=httpx.Timeout(300.0, write=300.0, connect=60.0)) as client:
        resp = client.post(
            "https://api.assemblyai.com/v2/upload",
            headers={"authorization": api_key},
            content=audio_bytes,
        )
        resp.raise_for_status()
        audio_url = resp.json()["upload_url"]

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_url, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

    segments: list[dict] = []

    if not transcript.utterances or len(transcript.utterances) < 2:
        logger.warning("Call %s: poor diarization (%d speakers), tagging as unknown.", call_id, len(transcript.utterances or []))
        for utt in transcript.utterances or []:
            segments.append({
                "speaker": "unknown",
                "start_ms": utt.start,
                "end_ms": utt.end,
                "text": utt.text,
            })
        return segments

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


# ── option 2: faster-whisper (local, free) ──────────────────────────────


def _whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def _ensure_wav(raw: bytes) -> bytes:
    """Convert any audio bytes to mono 16-bit 16 kHz WAV via ffmpeg."""
    if not _is_audio_bytes(raw):
        return raw
    import subprocess, tempfile, os

    tmp_dir = os.environ.get("TEMP", tempfile.gettempdir())
    inp = os.path.join(tmp_dir, "_fitnova_in.wav")
    out = os.path.join(tmp_dir, "_fitnova_out.wav")

    try:
        # Write input to temp file (ffmpeg needs a file, not stdin for format detection)
        with open(inp, "wb") as f:
            f.write(raw)

        # Find ffmpeg
        ffmpeg = shutil.which("ffmpeg") or os.path.join(tmp_dir, "ffmpeg.exe")
        if not os.path.exists(ffmpeg):
            logger.warning("ffmpeg not found, trying wave module directly.")
            return raw

        result = subprocess.run(
            [ffmpeg, "-y", "-i", inp, "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", out],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not os.path.exists(out):
            logger.warning("ffmpeg conversion failed: %s", result.stderr[-200:])
            return raw

        with open(out, "rb") as f:
            wav_bytes = f.read()
        return wav_bytes
    finally:
        for p in (inp, out):
            try:
                os.unlink(p)
            except Exception:
                pass


def _wav_to_mono_16k(raw: bytes) -> tuple[np.ndarray, int]:
    """Convert WAV bytes to mono 16 kHz numpy array, return (samples, sample_rate)."""
    import wave
    import io
    import numpy as np

    with wave.open(io.BytesIO(raw), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    dtype = {1: np.int16, 2: np.int16, 4: np.int32}[sampwidth]
    samples = np.frombuffer(frames, dtype=dtype)

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1).astype(dtype)

    if framerate != 16000:
        from scipy import signal
        new_len = int(len(samples) * 16000 / framerate)
        samples = signal.resample(samples, new_len).astype(dtype)

    return samples, 16000


def _has_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None or os.path.exists(
        os.path.join(os.environ.get("TEMP", ""), "ffmpeg.exe")
    )


def _transcribe_whisper(audio_bytes: bytes, call_id: str) -> list[dict]:
    """Transcribe using openai-whisper or faster-whisper (tries both)."""
    import numpy as np

    # Ensure WAV format (convert MP3 etc via ffmpeg)
    wav_bytes = _ensure_wav(audio_bytes) if not audio_bytes[:4] == b"RIFF" else audio_bytes
    if wav_bytes[:4] != b"RIFF":
        logger.warning("Could not convert audio to WAV, trying raw.")
        wav_bytes = audio_bytes

    samples, sr = _wav_to_mono_16k(wav_bytes)

    # Try standard whisper first
    segs = _try_openai_whisper(samples)
    if segs:
        return segs
    logger.info("openai-whisper returned 0 segments, trying faster-whisper.")

    # Fall back to faster-whisper
    segs = _try_faster_whisper(samples)
    if segs:
        return segs

    logger.warning("All whisper backends returned 0 segments.")
    return []


def _try_openai_whisper(samples: np.ndarray) -> list[dict] | None:
    try:
        import whisper
        model_size = os.getenv("WHISPER_MODEL", "base")
        logger.info("Loading whisper model '%s' (standard)...", model_size)
        model = whisper.load_model(model_size)
        result = model.transcribe(samples.astype(np.float32) / 32768.0, language=None)
        language = result.get("language", "en")
        logger.info("Whisper detected language: %s", language)
        segments_raw = result.get("segments", [])
        if not segments_raw:
            return None
        segments = []
        for seg in segments_raw:
            segments.append({
                "speaker": "unknown",
                "start_ms": int(seg.get("start", 0) * 1000),
                "end_ms": int(seg.get("end", 0) * 1000),
                "text": seg.get("text", "").strip(),
            })
        return segments
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("openai-whisper failed (%s)", exc)
        return None


def _try_faster_whisper(samples: np.ndarray) -> list[dict] | None:
    try:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "base")
        logger.info("Loading faster-whisper model '%s'...", model_size)
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        segments_raw, info = model.transcribe(samples, beam_size=5, language="en")
        logger.info("faster-whisper detected language: %s (prob=%.2f)", info.language, info.language_probability)

        segments = []
        for seg in segments_raw:
            segments.append({
                "speaker": "unknown",
                "start_ms": int(seg.start * 1000),
                "end_ms": int(seg.end * 1000),
                "text": seg.text.strip(),
            })
        return segments
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("faster-whisper failed (%s)", exc)
        return None


# ── option 3: stub (script text / hardcoded demo) ───────────────────────


def _stub_transcript(audio_bytes: bytes | None = None) -> list[dict]:
    """Fallback when neither AssemblyAI nor faster-whisper is available."""
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
    """Parse 'Advisor: ...' / 'Customer: ...' lines into stub segments."""
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
        duration_ms = max(2000, word_count * 200)
        segments.append({
            "speaker": speaker,
            "start_ms": ms,
            "end_ms": ms + duration_ms,
            "text": content,
        })
        ms += duration_ms + 500
    return segments
