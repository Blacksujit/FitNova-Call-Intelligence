---
title: FitNova Call Intelligence
emoji: 📞
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.37.0
app_file: fitnova/dashboard/app.py
pinned: false
---

# FitNova Call Intelligence System

AI system that automatically transcribes, scores, and flags issues in sales calls for FitNova's fitness coaching tele-advisors. Built from scratch — ingestion → transcription → PII redaction → AI analysis → storage → dashboard → feedback loop.

## Quick Start

```bash
pip install -r requirements.txt

# Download spaCy model for PII redaction
python -m spacy download en_core_web_sm

# One-command demo (seeds DB + processes 3 sample calls)
python scripts/run_demo.py
```

Then start the dashboard:

```bash
streamlit run fitnova/dashboard/app.py
```

**Demo logins** (all passwords in `scripts/seed_data.py`):

| Role | Email | Password |
|------|-------|----------|
| Sales Director | `director@fitnova.in` | `admin123` |
| Team Leader (Alpha) | `alpha_lead@fitnova.in` | `lead123` |
| Team Leader (Beta) | `beta_lead@fitnova.in` | `lead123` |
| Advisor | `priya@fitnova.in` | `advisor123` |

## API Keys (Optional)

The system works end-to-end **without any API key** — both transcription and analysis have free stub fallbacks. To use real AI:

| Service | Env Var | Why | Cost |
|---------|---------|-----|------|
| AssemblyAI | `ASSEMBLYAI_API_KEY` | Best diarization (separates speakers) | Paid, free trial |
| Anthropic | `ANTHROPIC_API_KEY` | Best analysis quality | Paid |
| OpenAI | `OPENAI_API_KEY` | Analysis fallback (GPT-4o-mini) | ~$0.15/1K calls |
| Google Gemini | `GEMINI_API_KEY` | Free analysis fallback | Free tier |

Create `.env` (copy from template below):

```
ASSEMBLYAI_API_KEY=your_key
ANTHROPIC_API_KEY=sk-ant-...
```

## Architecture

```
Incoming Call (MP3/WAV + JSON metadata)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  1. Ingestion  (folder_source.py / adapter ABC)  │
│     Reads data/incoming/ — source-agnostic       │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  2. Transcription  (transcribe.py)               │
│     AssemblyAI  →  faster-whisper  →  stub       │
│     PII redaction (regex + spaCy NER)            │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  3. Analysis  (tagger.py)                        │
│     Anthropic  →  OpenAI  →  Gemini  →  stub     │
│     5 scoring dimensions + 7 tag types           │
│     Hallucination guardrail (verbatim quotes)    │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  4. Storage  (SQLite + SQLAlchemy ORM)           │
│     Org → Team → Advisor → Call → Segments       │
│                                → Scores          │
│                                → Tags → Contests │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  5. Surfacing  (FastAPI + Streamlit)              │
│     REST API (12 endpoints, JWT auth)            │
│     Dashboard (Sales Director / TL / Advisor)    │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  6. Feedback  (contest workflow)                  │
│     Advisor contests → TL reviews → dismisses    │
└─────────────────────────────────────────────────┘
```

## What's Real vs Simulated

### Real (working with API keys or locally)
| Component | Implementation | With API Key | Without |
|-----------|---------------|-------------|---------|
| Transcription | AssemblyAI (API) / faster-whisper (local) | Speaker-diaried segments | Rule-based stub |
| Analysis | Claude / GPT-4o-mini / Gemini | AI scores + tags | Keyword scanner |
| PII Redaction | spaCy NER + regex | Names, phones, emails redacted | Same (no API needed) |
| Everything else | FastAPI + SQLite + Streamlit | Full system | Full system |

### Simulation / Stub

| Stub | What It Does |
|------|-------------|
| `transcribe.py` stub | Parses `Advisor:/Customer:` script text into segments with timestamps |
| `tagger.py` stub | Scans transcript for keywords (e.g., "goal", "guaranteed", "trial session") |
| `CRMSource` | `NotImplementedError` — docstring for HubSpot/Salesforce integration |
| `TelephonySource` | `NotImplementedError` — docstring for Twilio/Exotel webhook setup |

**Result**: `python scripts/run_demo.py` works immediately — no API keys, no external services, no GPU.

## Usage

```bash
# Process a specific call
python scripts/process_single.py MAIN-001

# Start API server
uvicorn fitnova.api.main:app --reload --port 8000

# Start dashboard (separate terminal)
streamlit run fitnova/dashboard/app.py

# Run all 76 tests
python -m pytest tests/ -v
```

## Scoring Rubric

| Dimension | 1-2 (Poor) | 3 (OK) | 4-5 (Good) |
|-----------|-----------|--------|-----------|
| needs_discovery | Pitched immediately | Asked some questions | Full goals/budget/timeline discovery |
| product_knowledge | Vague or wrong info | Basic program knowledge | Specific, accurate details |
| objection_handling | Dismissed concerns | Addressed reasonably | Turned objections into value |
| compliance | False claims, pressure | Minor issues | Clean, ethical sell |
| next_step_booking | No follow-up | Vague "call you later" | Specific trial date/time booked |

## Issue Tags

| Tag | Severity | What It Catches |
|-----|----------|----------------|
| no_needs_discovery | high | Pitched before understanding goals |
| over_promising | high | "Guaranteed results", "100% success" |
| pressure_tactics | high | "Expires today", limited-time offers |
| price_before_value | medium | Discounts mentioned before value |
| undisclosed_costs | high | Hidden fees revealed late |
| weak_trial_booking | medium | No specific trial booked |
| talking_over_customer | low | Interrupting or dominating conversation |

## Project Structure

```
fitnova/
  ingestion/         # CallSource ABC + Folder/CRM/Telephony adapters
  pipeline/          # orchestrator, transcribe, idempotency
  analysis/          # tagger (Claude/GPT/Gemini/stub), redactor, rubric
  storage/           # SQLAlchemy models, SQLite DB, aggregation helpers
  api/               # FastAPI (12 endpoints), auth, ratelimit, queue, cache
  dashboard/         # Streamlit (3 role views + JWT login)
  data/incoming/     # Call recordings + metadata JSON
scripts/             # seed_data, run_demo, process_single, test_api
tests/               # 76 tests across 14 files
docs/                # PRD + Architecture Writeup
```

## Where the System Would Fail

1. **High volume** (>50 calls/hour) — SQLite + in-process queue hit concurrency limits.
2. **Inbound calls** — First-speaker heuristic mislabels advisor on inbound calls.
3. **Non-English calls** — Prompts assume English; Hinglish needs few-shot examples.
4. **Memory** — In-memory TTL cache grows unbounded (fine for demo, needs Redis at scale).
5. **Token expiry** — JWT expires with no refresh endpoint (re-login required).
