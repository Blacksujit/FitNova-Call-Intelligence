"""
NER-based PII redactor for call transcripts.

Uses spaCy en_core_web_sm for named entity recognition (PERSON, GPE, ORG,
EMAIL, PHONE, MONEY, DATE) plus regex patterns for Indian-specific identifiers
(Aadhaar, PAN, phone numbers, email addresses).

Graceful degradation: if spaCy model is unavailable, falls back to regex-only.

Usage:
    redactor = PIIRedactor()
    safe_text = redactor.redact("My Aadhaar is 1234-5678-9012 and I live in Mumbai.")
    # "My Aadhaar is [REDACTED_AADHAAR] and I live in [REDACTED_LOCATION]."
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Regex patterns for Indian-specific PII ──────────────────────────────

INDIAN_PHONE = re.compile(r"\b(?:\+?91[-.\s]?)?[6-9]\d{9}\b")
AADHAAR = re.compile(r"\b[2-9]\d{3}[-\s]?\d{4}[-\s]?\d{4}\b")
PAN_CARD = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PIN_CODE = re.compile(r"\b[1-9]\d{5}\b")
BANK_ACCOUNT = re.compile(r"\b\d{9,18}\b")

# Labels from spaCy that we want to redact
NER_LABELS = {
    "PERSON",
    "GPE",
    "ORG",
    "EMAIL",
    "PHONE",
    "MONEY",
    "DATE",
    "TIME",
    "LOC",
    "FAC",
    "PRODUCT",
}

# Words that spaCy frequently mislabels as entities (false positives)
EXCLUDED_WORDS = {
    "aadhaar", "aadhar", "pan", "gst", "rs", "inr", "mrp",
}


class PIIRedactor:
    """Redact personally identifiable information from text.

    Uses spaCy NER as primary detector, with regex patterns for Indian
    identifiers as secondary coverage. If spaCy is unavailable, runs
    regex-only with reduced accuracy.
    """

    _nlp = None

    def __init__(self):
        self._load_nlp()

    def _load_nlp(self):
        if PIIRedactor._nlp is not None:
            return
        try:
            import spacy
            PIIRedactor._nlp = spacy.load("en_core_web_sm")
            logger.info("PIIRedactor loaded spaCy model en_core_web_sm")
        except Exception as e:
            logger.warning(
                "spaCy model unavailable (%s), falling back to regex-only PII detection. "
                "Install with: python -m spacy download en_core_web_sm",
                e,
            )
            PIIRedactor._nlp = None

    def redact(self, text: str) -> str:
        """Redact PII from text, replacing with [REDACTED_TYPE] tokens."""
        if not text or not text.strip():
            return text

        # Collect spans to redact as (start, end, label) tuples
        spans = []

        # ── SpaCy NER pass ──────────────────────────────────────────────
        if self._nlp is not None:
            doc = self._nlp(text)
            for ent in doc.ents:
                if ent.label_ in NER_LABELS and ent.text.lower() not in EXCLUDED_WORDS:
                    spans.append((ent.start_char, ent.end_char, ent.label_))

        # ── Regex pass (catches what NER misses) ────────────────────────
        for pattern, label in [
            (AADHAAR, "AADHAAR"),
            (PAN_CARD, "PAN"),
            (INDIAN_PHONE, "PHONE"),
            (EMAIL, "EMAIL"),
            (PIN_CODE, "PIN_CODE"),
        ]:
            for match in pattern.finditer(text):
                spans.append((match.start(), match.end(), label))

        # ── Sort and deduplicate by position ───────────────────────────
        # Sort by start ascending, then by end descending.
        # When two spans share identical (start, end), the later one wins
        # (regex passes are appended after NER and have more specific labels).
        spans.sort(key=lambda x: (x[0], -x[1]))
        merged = []
        for span in spans:
            if merged and span[0] == merged[-1][0] and span[1] == merged[-1][1]:
                # Same exact range — last one wins (regex > NER)
                merged[-1] = span
                continue
            if merged and span[0] >= merged[-1][0] and span[1] <= merged[-1][1]:
                # Fully enclosed by existing span — skip
                continue
            if merged and span[0] < merged[-1][1]:
                # Partial overlap — extend existing span
                if span[1] > merged[-1][1]:
                    merged[-1] = (merged[-1][0], span[1], merged[-1][2])
            else:
                merged.append(span)

        # ── Apply redactions from right to left to preserve positions ───
        result = list(text)
        for start, end, label in reversed(merged):
            replacement = f"[REDACTED_{label}]"
            result[start:end] = replacement
        result_str = "".join(result)

        return result_str

    def redact_segments(self, segments: list[dict]) -> list[dict]:
        """Redact PII from all segments in a transcript segment list.

        Each segment dict must have a 'text' key. The text is redacted
        in-place. Returns the same list with redacted texts.
        """
        for seg in segments:
            seg["text"] = self.redact(seg["text"])
        return segments

    def redact_analysis(self, analysis: dict) -> dict:
        """Redact PII from analysis results (scores and tags)."""
        for tag in analysis.get("tags", []):
            if "quoted_line" in tag:
                tag["quoted_line"] = self.redact(tag["quoted_line"])
            if "reason" in tag:
                tag["reason"] = self.redact(tag["reason"])
        for score in analysis.get("scores", []):
            if "justification" in score:
                score["justification"] = self.redact(score["justification"])
        return analysis


# ── Module-level singleton ──────────────────────────────────────────────

_redactor: PIIRedactor | None = None


def get_redactor() -> PIIRedactor:
    global _redactor
    if _redactor is None:
        _redactor = PIIRedactor()
    return _redactor


def redact_text(text: str) -> str:
    return get_redactor().redact(text)


def redact_segments(segments: list[dict]) -> list[dict]:
    return get_redactor().redact_segments(segments)


def redact_analysis(analysis: dict) -> dict:
    return get_redactor().redact_analysis(analysis)
