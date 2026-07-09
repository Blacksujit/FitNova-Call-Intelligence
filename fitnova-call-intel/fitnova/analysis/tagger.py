import os
import json
import logging
from typing import Any

from dotenv import load_dotenv

from .rubric import DIMENSIONS, ALLOWED_TAGS, SEVERITY_LEVELS

load_dotenv()
logger = logging.getLogger(__name__)

# ── System prompt for Claude ───────────────────────────────────────────

SYSTEM_PROMPT = """You are a quality analyst for a fitness coaching sales team.
Analyze the sales call transcript below and produce a structured evaluation.

## Scoring rubric (score each dimension 1-5)
- needs_discovery: Did the advisor proactively ask about the customer's goals, budget, constraints, and timeline before pitching?
- product_knowledge: Did the advisor demonstrate accurate, specific knowledge of programs, pricing, and policies?
- objection_handling: Did the advisor address concerns without overpromising or dismissing the customer?
- compliance: Did the advisor avoid false claims, pressure tactics, and handle sensitive information properly?
- next_step_booking: Did the advisor secure a specific trial/next-step with clear time and logistics?

## Issue tags (use ONLY from this closed set)
- no_needs_discovery: Advisor pitched before understanding goals/budget
- over_promising: "Guaranteed results", "100% success", unrealistic claims
- pressure_tactics: Limited-time offers, "act now", high-pressure closing
- price_before_value: Pricing or discounts mentioned before value established
- undisclosed_costs: Hidden fees revealed late in call
- weak_trial_booking: No specific trial session booked, vague follow-up
- talking_over_customer: Advisor interrupted or dominated the conversation

## Language notes
Transcripts may contain Hinglish (Hindi-English code-switching), e.g.
"aap ka fitness goal kya hai?" or "yeh plan ₹12,000 ka hai."
Analyze the substance regardless of language — the scoring criteria
are the same.

## Output format
Return a JSON object with:
1. "is_sales_call": true/false (with a short reason)
2. "scores": array of {"dimension": <name>, "value": <1-5>, "justification": "<one sentence>"}
3. "tags": array of {"category": <tag_name>, "severity": "low"/"medium"/"high", "timestamp_ms": <int>, "quoted_line": "<verbatim quote from transcript>", "reason": "<short reason>"}

CRITICAL: Every tag's quoted_line must appear EXACTLY (character-for-character) in the transcript. Do NOT paraphrase. If you cannot find a verbatim match, do NOT include that tag."""


def _build_tool_def() -> list[dict]:
    """Claude tool-use definition for structured JSON output."""
    return [
        {
            "name": "submit_call_analysis",
            "description": "Submit the structured analysis of a sales call transcript.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "is_sales_call": {
                        "type": "boolean",
                        "description": "Whether this is a genuine sales call (vs wrong number, internal, etc.)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief reason for the is_sales_call classification.",
                    },
                    "scores": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dimension": {
                                    "type": "string",
                                    "enum": DIMENSIONS,
                                },
                                "value": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 5,
                                },
                                "justification": {
                                    "type": "string",
                                    "description": "One-sentence justification for this score.",
                                },
                            },
                            "required": ["dimension", "value", "justification"],
                        },
                    },
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": ALLOWED_TAGS,
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": SEVERITY_LEVELS,
                                },
                                "timestamp_ms": {
                                    "type": "integer",
                                    "description": "Approximate timestamp in milliseconds of the tagged utterance.",
                                },
                                "quoted_line": {
                                    "type": "string",
                                    "description": "VERBATIM quote from the transcript that triggered this tag.",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Short reason for this tag.",
                                },
                            },
                            "required": ["category", "severity", "timestamp_ms", "quoted_line", "reason"],
                        },
                    },
                },
                "required": ["is_sales_call", "reason", "scores", "tags"],
            },
        }
    ]


def _build_transcript_text(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "unknown")
        text = seg.get("text", "")
        ts = seg.get("start_ms", 0)
        lines.append(f"[{ts}ms] {speaker}: {text}")
    return "\n".join(lines)


def _verify_quotes_in_transcript(transcript_text: str, tags: list[dict]) -> list[dict]:
    """Drop any tag whose quoted_line doesn't appear in the transcript."""
    verified = []
    for tag in tags:
        ql = tag.get("quoted_line", "")
        if ql and ql.strip() in transcript_text:
            verified.append(tag)
        else:
            logger.warning(
                "Caught hallucinated tag '%s': quoted_line '%s' not found in transcript.",
                tag.get("category"), ql,
            )
    return verified


# ── Public API ─────────────────────────────────────────────────────────

def analyze_call(segments: list[dict], call_id: str) -> dict:
    """
    Analyze a transcribed call. Resolution order:
      1. Anthropic Claude  (if ANTHROPIC_API_KEY set)
      2. OpenAI            (if OPENAI_API_KEY set, uses gpt-4o-mini)
      3. Ollama local LLM  (if OLLAMA_BASE_URL set, e.g. http://127.0.0.1:11434)
      4. Stub analyzer     (deterministic, no API needed)

    Returns scores, verified tags, and sales-call classification.
    """
    transcript_text = _build_transcript_text(segments)

    # ── Try Anthropic ───────────────────────────────────────────────────
    anthro_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthro_key:
        try:
            return _analyze_with_anthropic(transcript_text)
        except Exception as exc:
            logger.warning("Anthropic failed (%s), trying next option.", exc)

    # ── Try OpenAI ──────────────────────────────────────────────────────
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        try:
            return _analyze_with_openai(transcript_text)
        except Exception as exc:
            logger.warning("OpenAI failed (%s), trying next option.", exc)

    # ── Try Gemini ──────────────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            return _analyze_with_gemini(transcript_text, gemini_key)
        except Exception as exc:
            logger.warning("Gemini failed (%s), trying next option.", exc)

    # ── Try Ollama ──────────────────────────────────────────────────────
    ollama_url = os.getenv("OLLAMA_BASE_URL", "")
    if ollama_url:
        try:
            return _analyze_with_ollama(transcript_text, ollama_url)
        except Exception as exc:
            logger.warning("Ollama failed (%s), falling back to stub.", exc)

    # ── Fallback ────────────────────────────────────────────────────────
    logger.warning("No AI provider available — using stub analysis.")
    return _stub_analysis(segments)


def _analyze_with_anthropic(transcript_text: str) -> dict:
    """Call Claude via API."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript_text}],
        tools=_build_tool_def(),
        tool_choice={"type": "tool", "name": "submit_call_analysis"},
    )

    tool_block = None
    for content in response.content:
        if hasattr(content, "type") and content.type == "tool_use":
            tool_block = content.input
            break

    if not tool_block:
        raise RuntimeError("Claude did not return a tool_use block.")

    return _verify_and_return(transcript_text, tool_block)


def _analyze_with_openai(transcript_text: str) -> dict:
    """Call OpenAI GPT-4o-mini via function-calling API."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
        tools=_build_openai_tools(),
        tool_choice={"type": "function", "function": {"name": "submit_call_analysis"}},
        temperature=0,
    )

    msg = response.choices[0].message
    if not msg.tool_calls:
        raise RuntimeError("OpenAI did not return a tool call.")

    tool_block = json.loads(msg.tool_calls[0].function.arguments)
    return _verify_and_return(transcript_text, tool_block)


def _analyze_with_gemini(transcript_text: str, api_key: str) -> dict:
    """Call Google Gemini via function-calling API (free tier)."""
    from google import genai

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    tools = _build_openai_tools()
    gemini_tools = [{"function_declarations": [t["function"] for t in tools]}]

    response = client.models.generate_content(
        model=model,
        contents=f"{SYSTEM_PROMPT}\n\n{transcript_text}",
        config={"tools": gemini_tools, "temperature": 0},
    )

    if not response.candidates:
        raise RuntimeError("Gemini returned no candidates.")

    part = response.candidates[0].content.parts[0]
    if not part.function_call:
        raise RuntimeError("Gemini did not return a function call.")

    tool_block = {k: v for k, v in part.function_call.args.items()}
    return _verify_and_return(transcript_text, tool_block)


def _analyze_with_ollama(transcript_text: str, base_url: str) -> dict:
    """Call a local LLM via Ollama's OpenAI-compatible endpoint.

    Requires: ollama installed, a model pulled (e.g. 'llama3.2:3b').
    The model must support tool/function calling for structured output.
    """
    from openai import OpenAI

    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    client = OpenAI(base_url=f"{base_url.rstrip('/')}/v1", api_key="ollama")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript_text},
        ],
        tools=_build_openai_tools(),
        tool_choice={"type": "function", "function": {"name": "submit_call_analysis"}},
        temperature=0,
    )

    msg = response.choices[0].message
    if not msg.tool_calls:
        raise RuntimeError(f"Ollama/{model} did not return a tool call.")

    tool_block = json.loads(msg.tool_calls[0].function.arguments)
    return _verify_and_return(transcript_text, tool_block)


def _build_openai_tools() -> list[dict]:
    """Convert the Anthropic tool definition to OpenAI function-calling format."""
    anthropic_tools = _build_tool_def()
    openai_tools = []
    for t in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        })
    return openai_tools


def _verify_and_return(transcript_text: str, tool_block: dict) -> dict:
    """Extract scores/tags from a tool block and run the hallucination guardrail."""
    is_sales = tool_block.get("is_sales_call", True)
    raw_tags = tool_block.get("tags", [])
    raw_scores = tool_block.get("scores", [])

    verified_tags = _verify_quotes_in_transcript(transcript_text, raw_tags)

    if raw_tags and not verified_tags:
        logger.warning("All %d tags were hallucinated — dropping all.", len(raw_tags))

    return {
        "is_sales_call": is_sales,
        "scores": raw_scores,
        "tags": verified_tags,
    }


def _stub_analysis(segments: list[dict]) -> dict:
    """Rule-based fallback when no API key is configured. Scans transcript
    text for known trigger phrases and builds scores + tags accordingly."""

    transcript_text = _build_transcript_text(segments)
    text_lower = transcript_text.lower()

    # ── Scoring — simple rules ─────────────────────────────────────────
    has_discovery = any(p in text_lower for p in ["goal", "budget", "timeline", "commit", "experience", "tell me about", "kya", "kaise", "kab"])
    has_compliance_issue = any(p in text_lower for p in ["guaranteed", "100%", "never had a client", "guarantee"])
    has_pressure = any(p in text_lower for p in ["won't be available", "expires today", "act now", "limited time", "last chance"])
    has_price_before_value = any(p in text_lower for p in ["sign up today", "discount", "special rate"])
    has_booking = any(p in text_lower for p in ["trial session", "book", "slot", "confirmation", "free trial", "booking"])

    scores = [
        {"dimension": "needs_discovery", "value": 4 if has_discovery else 2,
         "justification": "Asked about goals" if has_discovery else "Pitched without discovery."},
        {"dimension": "product_knowledge", "value": 4,
         "justification": "Demonstrated program knowledge."},
        {"dimension": "objection_handling", "value": 2 if has_compliance_issue else 4,
         "justification": "Used overpromising language." if has_compliance_issue else "Handled objections reasonably."},
        {"dimension": "compliance", "value": 1 if has_compliance_issue else 4,
         "justification": "Compliance risk detected." if has_compliance_issue else "No compliance issues."},
        {"dimension": "next_step_booking", "value": 4 if has_booking else 1,
         "justification": "Trial booked." if has_booking else "No trial session booked."},
    ]

    # ── Tagging — find first matching segment ──────────────────────────
    tags = []

    for seg in segments:
        seg_text = seg.get("text", "")
        ts = seg.get("start_ms", 0)
        if has_compliance_issue and "guaranteed" in seg_text.lower():
            tags.append({
                "category": "over_promising", "severity": "high",
                "timestamp_ms": ts, "quoted_line": seg_text[:80],
                "reason": "Advisor used guaranteed results language.",
            })
        if has_pressure and ("available" in seg_text.lower() or "expires" in seg_text.lower()):
            tags.append({
                "category": "pressure_tactics", "severity": "high",
                "timestamp_ms": ts, "quoted_line": seg_text[:80],
                "reason": "Created false urgency to push sale.",
            })
        if has_price_before_value and ("discount" in seg_text.lower() or "sign up" in seg_text.lower()):
            tags.append({
                "category": "price_before_value", "severity": "medium",
                "timestamp_ms": ts, "quoted_line": seg_text[:80],
                "reason": "Mentioned pricing/discount before value established.",
            })

    # Deduplicate by category
    seen_cats = set()
    unique_tags = []
    for t in tags:
        if t["category"] not in seen_cats:
            seen_cats.add(t["category"])
            unique_tags.append(t)

    # Run hallucination guardrail
    unique_tags = _verify_quotes_in_transcript(transcript_text, unique_tags)

    return {
        "is_sales_call": True,
        "scores": scores,
        "tags": unique_tags,
    }
