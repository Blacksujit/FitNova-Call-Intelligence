# FitNova Call Intelligence System — PRD & Architecture Writeup

> **Role**: AI Engineer Intern (Take-Home Case Study)
> **Author**: Built from scratch — full pipeline: ingestion → transcription → analysis → storage → surfacing → feedback
> **Status**: MVP Complete (65/65 tests passing) — this document maps what's real vs what needs production hardening

---

## 1. System Architecture — End to End

```
Call Source           Ingestion           Pipeline              Storage          Surfacing           Feedback
Folder/CRM/Telephony → CallSource (ABC)  → Transcribe+Analyze  → SQLite/SQLAlchemy → FastAPI + Streamlit → Contest Workflow
                     (Adapter pattern)     (AssemblyAI/Claude)                       (3 role views)
```

### 1.1 Ingestion Layer — `fitnova/ingestion/`

| Component | Status | What It Does |
|-----------|--------|-------------|
| `CallSource` (ABC) | **Done** | Abstract base: `fetch_new_calls()` + `get_audio_bytes()`. Any new source implements 2 methods. |
| `FolderSource` | **Done** | Reads `fitnova/data/incoming/` as `.mp3/.wav` + `.json` metadata pairs. Caches processed IDs in memory. |
| `CRMSource` | **Stub** | Raises `NotImplementedError` with a docstring describing HubSpot/Salesforce OAuth2 + cursor pagination. |
| `TelephonySource` | **Stub** | Raises `NotImplementedError` with a docstring for Twilio/Exotel webhook setup. |

**Design decision**: Adapter pattern. Switching telephony vendors = write a new class with 2 methods. Zero pipeline changes.

### 1.2 Transcription — `fitnova/pipeline/transcribe.py`

| Mode | Status | Integration |
|------|--------|-------------|
| AssemblyAI (real) | **Done** | `speaker_labels=True`, first-speaker heuristic for advisor/customer mapping |
| Poor diarisation fallback | **Done** | Mono audio → all segments tagged `"unknown"`, `diarization_quality="failed"` on Call row |
| Stub (no API key) | **Done** | Parses `Advisor: ...\nCustomer: ...` script format into segments with approximate timestamps |

**Trade-off**: First-speaker heuristic assumes outbound calls. Wrong for inbound. Production fix: voice-print matching or CRM caller-field lookup.

### 1.3 Analysis Engine — `fitnova/analysis/tagger.py`

| Mode | Status | Details |
|------|--------|---------|
| Claude (real) | **Done** | Tool-use structured output with closed-set 7 tags + 5 scoring dimensions. Anti-hallucination guardrail. |
| Stub (no API key) | **Done** | Rule-based keyword scanner. Same verbatim-quote verification. |

**Anti-hallucination guardrail**: Every tag must carry a `quoted_line`. After Claude (or the stub) returns, a verification pass drops any tag whose quoted text is not found verbatim in the transcript. Logged as warnings.

**Scoring rubric** (5 dimensions, 1-5):

| Dimension | What It Measures |
|-----------|-----------------|
| `needs_discovery` | Did advisor ask about goals/budget/timeline before pitching? |
| `product_knowledge` | Accurate, specific program/pricing knowledge? |
| `objection_handling` | Addressed concerns without overpromising? |
| `compliance` | False claims, pressure tactics, consent? |
| `next_step_booking` | Specific trial booked with time/logistics? |

**Issue tags** (closed set, 7 types):

| Tag | Default Severity | What It Catches |
|-----|-----------------|-----------------|
| `no_needs_discovery` | high | Pitched without understanding goals |
| `over_promising` | high | "Guaranteed results", "100% success" |
| `pressure_tactics` | high | "Won't be available", "expires today" |
| `price_before_value` | medium | Discount/pricing before value established |
| `undisclosed_costs` | high | Hidden fees revealed late |
| `weak_trial_booking` | medium | No specific trial booked |
| `talking_over_customer` | low | Interrupting or dominating |

### 1.4 Pipeline Orchestrator — `fitnova/pipeline/orchestrator.py`

```
process_call() →
  1. compute_audio_hash() → SHA-256 of audio bytes
  2. is_already_processed() → idempotency check (unique constraint on audio_hash)
  3. Create Call row (status=ingested)
  4. transcribe_and_diarize() → segments
  5. analyze_call() → scores + tags (with hallucination guardrail)
     - is_sales_call=false → status=non_sales_call, skip scoring
     - Otherwise → store Scores + Tags, status=analyzed
  6. Exception → status=failed, logged
```

### 1.5 Storage — `fitnova/storage/`

**Data model** (SQLite via SQLAlchemy ORM):

```
Org (1) ──→ Team (N) ──→ Advisor (N) ──→ Call (N) ──→ Segment (N)
                                                ├── Score (N)
                                                └── Tag (N) ──→ Contest (N)

User (separate, maps to Org/Team/Advisor for auth)
```

Key design choices:
- `audio_hash` (SHA-256) has a UNIQUE constraint → idempotency at DB level
- Cascade deletes: removing an Org removes all Teams → Advisors → Calls → Segments/Scores/Tags
- Tag status is an enum: `active` → `contested` → `dismissed`

### 1.6 API Surface — `fitnova/api/`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check + cache flush |
| `/auth/login` | POST | No | JWT login (bcrypt verify) |
| `/auth/register` | POST | No | Create new user |
| `/auth/me` | GET | Bearer | Current user info from token |
| `/incoming/list` | GET | Bearer | List unprocessed calls in folder |
| `/calls/process` | POST | Bearer | Process a call (sync, or 202 queued) |
| `/tasks/{id}` | GET | Bearer | Poll async task status |
| `/calls/{id}` | GET | Bearer | Call detail (segments, scores, tags) |
| `/orgs/{id}/summary` | GET | Bearer | Org averages + teams (role-scoped) |
| `/teams/{id}/summary` | GET | Bearer | Team averages + advisors (role-scoped) |
| `/advisors/{id}/summary` | GET | Bearer | Advisor averages + calls (role-scoped) |
| `/tags/{id}/contest` | POST | Bearer | Contest a tag (advisor/team-leader only) |

### 1.7 Auth & Authorization — `fitnova/api/`

**JWT-based** with HS256. Token expiry configurable via `JWT_EXPIRE_HOURS` env var.

**Role hierarchy**:
- `sales_director` → sees all orgs/teams/advisors/calls. Cannot contest tags.
- `team_leader` → sees own team's advisors/calls. Can contest tags in own team.
- `advisor` → sees own calls and scores. Can contest own tags.

**Scope helpers**:
- `can_access_org(user, org_id)` — checks org membership
- `can_access_team(user, team_id)` — SD sees all, TL sees own
- `can_access_advisor(user, advisor_id)` — SD sees all, TL sees own team, advisor sees self
- `can_access_call(user, call_id)` — SD sees all, TL sees own team's calls, advisor sees own

**Design principle**: All endpoints check 404 (resource not found) BEFORE 403 (not authorized). A nonexistent resource should never leak existence info.

### 1.6 Infrastructure Concerns

| Concern | Implementation | Status |
|---------|---------------|--------|
| Rate limiting | Sliding-window counter per IP. Process limit → 202 queued instead of 429. Others → 429 with Retry-After. | **Done** |
| Async queue | In-process thread pool (max 2 concurrent). Task status persisted in SQLite. | **Done** |
| Response caching | In-memory TTL cache per endpoint. Invalidated on write operations. `Cache-Control: no-cache` bypass. | **Done** |
| Auth/JWT | `passlib[bcrypt]` + `python-jose[cryptography]`. Sub claim is string. | **Done** |

---

## 2. What We Built — MVP Scope (65 tests, all passing)

### 2.1 Core Pipeline (end-to-end)
- [x] Source-agnostic ingestion via ABC adapter pattern
- [x] Folder source reads `.mp3`/`.wav` + JSON metadata pairs
- [x] AssemblyAI transcription + diarisation with speaker mapping
- [x] Stub transcription fallback (parses `Advisor:/Customer:` script format)
- [x] Claude analysis engine with tool-use structured output (7 tags, 5 scores)
- [x] Stub analysis fallback (rule-based keyword scanner)
- [x] Anti-hallucination verbatim quote verification guardrail
- [x] Non-sales call detection → skip scoring, `non_sales_call` status
- [x] Poor diarisation → `diarization_quality="failed"` with unknown speakers
- [x] Pipeline failure → status `failed`, error logged, exception re-raised
- [x] Audio SHA-256 idempotency → never double-process same audio

### 2.2 Storage & Data Model
- [x] SQLite + SQLAlchemy ORM (8 tables)
- [x] Org → Team → Advisor → Call hierarchy with cascade deletes
- [x] Aggregation helpers for org/team/advisor average scores

### 2.3 REST API
- [x] 12 endpoints covering auth, process, summary, contest
- [x] JWT login/register/me with bcrypt password hashing
- [x] Role-based authorization at endpoint + data-scope level
- [x] Rate limiting with 202 queue fallback for process endpoint
- [x] In-process async task queue with status polling
- [x] Response caching with prefix-based invalidation
- [x] Cache-Control: no-cache bypass support
- [x] 404-before-403 resource existence policy

### 2.4 Dashboard
- [x] Streamlit with 3 role views
- [x] JWT login flow replacing role selector
- [x] Sales Director: org-wide bar chart + active tags table
- [x] Team Leader: advisor averages + call list with contest capability
- [x] Advisor: own calls, transcript viewer, tag contest form
- [x] Async task queue polling in sidebar
- [x] Cache bypass toggle + manual cache clear
- [x] Process new calls from incoming folder

### 2.5 Demo/Seed
- [x] `scripts/seed_data.py` — seeds 2 teams, 6 advisors, 9 users (1 SD, 2 TL, 6 advisors)
- [x] `scripts/run_demo.py` — seeds DB, writes 3 sample calls to incoming/, processes them, prints results
- [x] 3 demo calls: good call, neutral call, compliance-violation call

### 2.6 Tests
- [x] 65 tests across 14 files
- [x] Auth tests: login, 401, 403, role scoping, register
- [x] Pipeline tests: 404 flows, incoming list
- [x] Contest tests: full cycle, empty comment, multi-contest, nonexistent tag
- [x] Call detail tests: existing call, nonexistent call, tag uniqueness
- [x] Summary tests: org/team/advisor, nonexistent, empty team edge case
- [x] Cache tests: TTL, invalidation, bypass, contest invalidation
- [x] Queue tests: enqueue, get, status, uniqueness
- [x] Rate limit tests: sliding window, 429, headers, process queue fallback
- [x] Auth error path tests: unauthenticated 404, method not allowed, invalid IDs

---

## 3. What's Next — Production Hardening (The "Real Engineer" Layer)

### 3.1 Must-Have for Production

| # | Item | Why | Effort |
|---|------|-----|--------|
| 1 | **Celery + Redis for async pipeline** | Current in-process queue dies on process restart. No persistence for queued tasks. Celery gives durability, concurrency, retry. | 2-3 days |
| 2 | **PostgreSQL migration** | SQLite doesn't handle concurrent writes. At FitNova scale (hundreds of calls/hour), you'll get `database is locked` errors. | 1 day |
| 3 | **PII redaction (NER, not regex)** | The regex placeholder catches `[A-Z]\w+@`, but not names, phone numbers, addresses. SpaCy NER or Presidio needed for real PII. | 2 days |
| 4 | **Customer <> CRM linking** | Current system has no customer record. Who was called? What deal is this linked to? Need to join against CRM for conversion analytics. | 2-3 days |
| 5 | **Rate limit bypass via auth** | Current rate limiter runs before auth (by design for queue), but this means an unauthenticated attacker can exhaust the queue. Fix: move auth check into rate limiter for non-process endpoints. | 0.5 day |
| 6 | **Logging + structured logging** | Current is plain `logger.info/warning`. No correlation IDs, no JSON format, no log aggregation. At production, you cannot debug without this. | 0.5 day |

### 3.2 High-Value Improvements

| # | Item | Why | Effort |
|---|------|-----|--------|
| 7 | **Voice-print speaker ID** | First-speaker heuristic fails for inbound calls. Voice-print profiles would map speakers to advisor/customer by voice, not position. | 3-5 days |
| 8 | **Code-switching (Hinglish)** | FitNova is Bangalore-based. Real calls mix Hindi and English. Whisper handles it; scoring prompts need Hinglish examples in few-shot. | 2 days |
| 9 | **Team Leader contest review dashboard** | Current TL can only mark as "Reviewed" — no actual approve/dismiss with feedback. Need a real review queue with `dismissed` status and TL notes. | 1 day |
| 10 | **Tag cluster analysis** | "70% of compliance flags are on Priya's calls" — could detect patterns across advisors and teams automatically. | 1-2 days |
| 11 | **Push notifications** | Team Leaders shouldn't poll for new flags. WebSocket or email digest for high-severity uncontested tags. | 1-2 days |
| 12 | **Alerting / monitoring** | Pipeline failure rate, processing latency, API error rate, rate limit hit rate. Prometheus + Grafana or Datadog. | 1-2 days |

### 3.3 Architectural Decisions & Trade-offs

| Decision | Why We Did It | When to Revisit |
|----------|--------------|----------------|
| **SQLite for MVP** | Zero config, fast for demo. All reads/writes on one connection. | When concurrent writes exceed ~10/min → PostgreSQL |
| **In-process async queue** | No infrastructure needed for demo. 2 concurrent workers is enough for 10 calls/min. | When queue depth exceeds 50 → Celery + Redis |
| **First-speaker heuristic** | Simple, no voice data needed. Works for outbound calls. | When inbound calls are common → voice-print or CRM caller-field |
| **Made-up pricing** | No real FitNova pricing. Purely illustrative for the demo. | N/A — demo only |
| **No CI/CD** | Not requested. 65 tests run locally. | For team use → GitHub Actions + lint + test |
| **No Docker** | Not requested. Single `pip install -r requirements.txt`. | For deployment consistency → Dockerfile |
| **Stub analysis vs Claude** | Both work end-to-end. Real mode just needs `ANTHROPIC_API_KEY`. | N/A — both are real paths |

### 3.4 Where the System Would Fail

1. **High-volume concurrent processing** — SQLite + in-process queue would collapse above ~50 calls/hour. Queued tasks lost on restart.
2. **Inbound calls** — First-speaker heuristic mislabels the advisor as the first speaker. Would require voice-print or CRM whitelist.
3. **Non-English calls** — AssemblyAI/Claude prompts assume English. Hinglish would produce poor diarisation and irrelevant scores.
4. **Stereo vs mono** — AssemblyAI handles both, but stub parser assumes text format. Non-text audio files with no API key would fall through to hardcoded demo transcript.
5. **Memory pressure on cache** — In-memory TTL cache grows unbounded. At scale, use Redis or capped-LRU cache.
6. **Token expiry with no refresh** — JWT expires but there's no refresh endpoint. User must re-login. Fine for demo, annoying in production.

---

## 4. Quickstart (for evaluators)

```bash
# One-command demo
pip install -r fitnova-call-intel/requirements.txt
cd fitnova-call-intel
python scripts/run_demo.py

# Start API + Dashboard
uvicorn fitnova.api.main:app --reload    # Terminal 1
streamlit run fitnova/dashboard/app.py    # Terminal 2

# Run tests
python -m pytest tests/ -v
```

**Demo logins**: `director@fitnova.in` / `admin123` — sees org-wide scores and all teams.

---

## 5. File Map

```
fitnova/
  ingestion/
    base.py           # CallSource ABC (2 methods to implement)
    folder_source.py  # Folder adapter — reads data/incoming/
    stub_sources.py   # CRM + Telephony stubs with integration docs
  pipeline/
    orchestrator.py   # process_call() — the main pipeline
    transcribe.py     # AssemblyAI + stub fallback (script parser)
    idempotency.py    # SHA-256 hash + duplicate check
  analysis/
    tagger.py         # Claude tool-use + stub + hallucination guardrail
    rubric.py         # Constants: 5 dimensions, 7 tags, 3 severity levels
  storage/
    models.py         # 8 tables: Org, Team, Advisor, Call, Segment, Score, Tag, Contest, User
    db.py             # SQLite engine + session + aggregation helpers
  api/
    main.py           # 12 FastAPI endpoints
    auth.py           # /auth/login, /auth/register, /auth/me
    dependencies.py   # get_current_user, require_role, scope helpers
    ratelimit.py      # Sliding-window counter + 202 queue fallback
    queue.py          # In-process async task queue with SQLite persistence
    cache.py          # In-memory TTL response cache
  dashboard/
    app.py            # Streamlit dashboard: 3 role views + login
scripts/
  seed_data.py        # DB seeding (9 users, 6 advisors, 2 teams)
  run_demo.py         # End-to-end demo runner
tests/                # 65 tests across 14 files
```