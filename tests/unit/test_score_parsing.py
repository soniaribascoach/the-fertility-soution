import pytest
from app.services.ai import parse_score_from_response


def test_missing_marker_defaults_to_zero():
    _, delta = parse_score_from_response("Just a normal reply with no score.")
    assert delta == 0


def test_valid_positive_marker():
    clean, delta = parse_score_from_response("Great news!\n[SCORE:15]")
    assert delta == 15
    assert clean == "Great news!"


def test_valid_negative_marker():
    clean, delta = parse_score_from_response("I understand.\n[SCORE:-10]")
    assert delta == -10
    assert clean == "I understand."


def test_zero_delta():
    clean, delta = parse_score_from_response("Neutral response.\n[SCORE:0]")
    assert delta == 0
    assert clean == "Neutral response."


def test_marker_in_middle_not_parsed():
    text = "Before [SCORE:20] middle text.\nLast line."
    _, delta = parse_score_from_response(text)
    assert delta == 0


def test_marker_always_stripped_even_when_in_middle():
    text = "Before [SCORE:20] middle.\nLast line."
    clean, _ = parse_score_from_response(text)
    assert "[SCORE:20]" not in clean


def test_malformed_number_defaults_zero():
    clean, delta = parse_score_from_response("Reply.\n[SCORE:abc]")
    assert delta == 0


def test_malformed_marker_not_stripped_from_last_line():
    # malformed marker on last line — not recognized, treated as normal text
    text = "Reply.\n[SCORE:]"
    clean, delta = parse_score_from_response(text)
    assert delta == 0


def test_empty_string():
    clean, delta = parse_score_from_response("")
    assert delta == 0
    assert clean == ""


def test_multiline_reply_with_marker():
    text = "Line one.\nLine two.\nLine three.\n[SCORE:5]"
    clean, delta = parse_score_from_response(text)
    assert delta == 5
    assert "Line one." in clean
    assert "Line three." in clean
    assert "[SCORE:5]" not in clean


def test_extra_whitespace_around_marker():
    text = "Reply text.\n[SCORE:7]  "
    clean, delta = parse_score_from_response(text)
    assert delta == 7
