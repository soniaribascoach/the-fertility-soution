"""
test_format.py — Structural / deterministic checks on AI replies.

One API call per message. All format assertions run on that single reply.
Run with:  pytest tests/test_format.py -s -v

No AI judge — plain Python assertions only.
"""
import re
import pytest

from tests.conftest import run_reply, print_result, VALID_TTC, VALID_DIAGNOSIS, VALID_URGENCY, VALID_READINESS, VALID_FIT

pytestmark = pytest.mark.live

SAMPLE_MESSAGES = [
    "Hi, I'd love to learn more about your programme.",
    "We've been trying to conceive for about a year now with no luck.",
    "I was diagnosed with PCOS last year — can you help?",
    "I'm 38 and starting to feel the pressure of my biological clock.",
    "What does working with Sonia actually involve?",
    "My husband and I have been through two failed IVF cycles.",
    "I'd love to book a call — how do I get started?",
    "I just started trying, I'm not sure if I even need coaching yet.",
    "I've been trying for 3 years and I feel like I've exhausted all options.",
    "Can you tell me more about the natural approach to improving fertility?",
]


@pytest.mark.parametrize("message", SAMPLE_MESSAGES)
async def test_format_constraints(message, openai_client, base_cfg):
    """
    One API call. All structural rules checked on the same reply.
    The AI reply is always printed before any assertion fires.
    """
    result = await run_reply(message, openai_client, base_cfg)

    # ── Always print first so the reply is visible even when a check fails ──
    print_result("FORMAT", 1, 1, message, result)

    reply = result.reply

    # Non-empty
    assert reply.strip() != "", "Reply is empty"

    # No markdown formatting
    assert "**" not in reply, f"Bold markdown (**) found:\n{reply}"
    assert "##" not in reply, f"Markdown header (##) found:\n{reply}"
    assert not re.match(r"^#+\s", reply), f"Reply starts with markdown header:\n{reply[:80]}"

    lines = reply.splitlines()
    for line in lines:
        stripped = line.strip()
        assert not re.match(r"^[-*•]\s", stripped), (
            f"Bullet point found on line {stripped!r}:\n{reply}"
        )

    # No URLs — booking links must never appear in the AI reply text
    assert not re.search(r"https?://", reply), f"URL found in reply:\n{reply}"

    # All 5 tag dimensions present with valid enum values
    assert set(result.tags.keys()) == {"ttc", "diagnosis", "urgency", "readiness", "fit"}, (
        f"Unexpected tag keys: {set(result.tags.keys())}"
    )
    assert result.tags["ttc"]       in VALID_TTC,       f"Invalid ttc tag: {result.tags['ttc']!r}"
    assert result.tags["diagnosis"] in VALID_DIAGNOSIS,  f"Invalid diagnosis tag: {result.tags['diagnosis']!r}"
    assert result.tags["urgency"]   in VALID_URGENCY,    f"Invalid urgency tag: {result.tags['urgency']!r}"
    assert result.tags["readiness"] in VALID_READINESS,  f"Invalid readiness tag: {result.tags['readiness']!r}"
    assert result.tags["fit"]       in VALID_FIT,        f"Invalid fit tag: {result.tags['fit']!r}"

    # Token and cost tracking
    assert result.prompt_tokens > 0,    "prompt_tokens not recorded"
    assert result.completion_tokens > 0, "completion_tokens not recorded"
    assert result.cost > 0.0,           "cost not recorded"
    assert result.model,                "model string is empty"
