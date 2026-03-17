import pytest
from app.services.ai import parse_tags_from_response


VALID_TAG_LINE = "[TAGS: ttc=ttc_1-2yr | diagnosis=diagnosis_confirmed | urgency=urgency_high | readiness=readiness_ready | fit=fit_high]"

VALID_RESPONSE = f"Great to hear from you!\n{VALID_TAG_LINE}"


def test_valid_tags_parsed():
    clean, tags = parse_tags_from_response(VALID_RESPONSE)
    assert tags == {
        "ttc": "ttc_1-2yr",
        "diagnosis": "diagnosis_confirmed",
        "urgency": "urgency_high",
        "readiness": "readiness_ready",
        "fit": "fit_high",
    }


def test_marker_stripped_from_clean_text():
    clean, tags = parse_tags_from_response(VALID_RESPONSE)
    assert clean == "Great to hear from you!"
    assert "[TAGS:" not in clean


def test_missing_marker_returns_empty_dict():
    clean, tags = parse_tags_from_response("Just a normal reply with no tags.")
    assert tags == {}
    assert clean == "Just a normal reply with no tags."


def test_malformed_marker_returns_empty_dict():
    text = "Reply.\n[TAGS: ttc=ttc_1-2yr]"  # incomplete, missing other dims
    _, tags = parse_tags_from_response(text)
    assert tags == {}


def test_marker_not_on_last_line_returns_empty_dict():
    text = f"{VALID_TAG_LINE}\nThis line comes after the tag line."
    _, tags = parse_tags_from_response(text)
    assert tags == {}


def test_marker_not_on_last_line_stripped_from_clean():
    text = f"{VALID_TAG_LINE}\nThis line comes after."
    clean, _ = parse_tags_from_response(text)
    assert "[TAGS:" not in clean


def test_empty_string_returns_empty_dict():
    clean, tags = parse_tags_from_response("")
    assert tags == {}
    assert clean == ""


def test_multiline_reply_with_marker():
    text = f"Line one.\nLine two.\nLine three.\n{VALID_TAG_LINE}"
    clean, tags = parse_tags_from_response(text)
    assert "Line one." in clean
    assert "Line three." in clean
    assert "[TAGS:" not in clean
    assert tags["readiness"] == "readiness_ready"


def test_conservative_tags_parsed():
    tag_line = "[TAGS: ttc=ttc_0-6mo | diagnosis=diagnosis_none | urgency=urgency_low | readiness=readiness_exploring | fit=fit_low]"
    _, tags = parse_tags_from_response(f"Just browsing.\n{tag_line}")
    assert tags == {
        "ttc": "ttc_0-6mo",
        "diagnosis": "diagnosis_none",
        "urgency": "urgency_low",
        "readiness": "readiness_exploring",
        "fit": "fit_low",
    }


def test_extra_whitespace_around_marker():
    text = f"Reply text.\n{VALID_TAG_LINE}  "
    clean, tags = parse_tags_from_response(text)
    assert tags["ttc"] == "ttc_1-2yr"
