"""Tests for the PII redactor (NER-based + regex)."""

from fitnova.analysis.redactor import PIIRedactor, redact_text, redact_segments, redact_analysis


def _get_redactor():
    r = PIIRedactor()
    r._load_nlp()
    return r


def test_redacts_person_name():
    r = _get_redactor()
    result = r.redact("Mr. Sharma called about the plan.")
    assert "Sharma" not in result or "[REDACTED" in result


def test_redacts_phone_number():
    r = _get_redactor()
    result = r.redact("Call me at 9876543210")
    assert "9876543210" not in result
    assert "[REDACTED" in result


def test_redacts_email():
    r = _get_redactor()
    result = r.redact("Email amit@example.com for details")
    assert "amit@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


def test_redacts_addhaar():
    r = _get_redactor()
    result = r.redact("My Aadhaar is 2345-6789-0123")
    assert "2345-6789-0123" not in result
    assert "[REDACTED_AADHAAR]" in result


def test_redacts_pan():
    r = _get_redactor()
    result = r.redact("My PAN is ABCDE1234F")
    assert "ABCDE1234F" not in result
    assert "[REDACTED_PAN]" in result


def test_leaves_non_pii_unchanged():
    r = _get_redactor()
    result = r.redact("Advisor: Tell me about your fitness goals")
    assert result == "Advisor: Tell me about your fitness goals"


def test_preserves_advisor_customer_labels():
    r = _get_redactor()
    result = r.redact("Advisor: Hello what are your fitness goals\nCustomer: I want to lose weight")
    assert "Advisor:" in result
    assert "Customer:" in result


def test_empty_string_returns_empty():
    r = _get_redactor()
    assert r.redact("") == ""
    assert r.redact(None) is None


def test_redact_segments_in_place():
    r = _get_redactor()
    segments = [
        {"speaker": "advisor", "text": "Mr. Sharma, this is Priya."},
        {"speaker": "customer", "text": "My Aadhaar is 2345-6789-0123."},
    ]
    result = r.redact_segments(segments)
    assert result is segments  # in-place
    assert "2345-6789-0123" not in result[1]["text"]
    assert "[REDACTED_AADHAAR]" in result[1]["text"]


def test_redact_analysis_scores_and_tags():
    r = _get_redactor()
    analysis = {
        "is_sales_call": True,
        "scores": [
            {"dimension": "compliance", "value": 4, "justification": "Referred to Bangalore office."},
        ],
        "tags": [
            {
                "category": "over_promising", "severity": "high",
                "quoted_line": "Mr. Sharma from Bangalore, guaranteed results!",
            },
        ],
    }
    result = r.redact_analysis(analysis)
    assert "Bangalore" not in result["scores"][0]["justification"]
    assert "Bangalore" not in result["tags"][0]["quoted_line"]


def test_module_level_functions():
    result = redact_text("My email is test@example.com")
    assert "[REDACTED_EMAIL]" in result

    segments = [{"speaker": "advisor", "text": "Hi Amit from Bangalore"}]
    redact_segments(segments)
    assert "Bangalore" not in segments[0]["text"]