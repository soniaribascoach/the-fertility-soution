"""
test_tagging.py — Lead tag accuracy for unambiguous scenarios.

Uses the production prompt. Each scenario has explicit signals that make
the correct tag deterministic. 3 trials per test — all must produce the right tag.

No AI judge — direct enum assertions only.
Run with:  pytest tests/test_tagging.py -s -v
"""
import pytest
from tests.conftest import run_reply, make_turn, print_result

pytestmark = pytest.mark.live

TRIALS = 3


async def _collect(label, message, openai_client, cfg, history=None):
    results = []
    for trial in range(1, TRIALS + 1):
        r = await run_reply(message, openai_client, cfg, history=history)
        print_result(f"TAG:{label}", trial, TRIALS, message, r)
        results.append(r)
    return results


def _check(results, dimension, expected, message):
    for i, r in enumerate(results, 1):
        got = r.tags.get(dimension)
        assert got == expected, (
            f"\nTrial {i}/{TRIALS} — {dimension}: expected {expected!r} but got {got!r}\n"
            f"Message: {message}\nAll tags: {r.tags}\nReply:\n{r.reply}"
        )


# ── TTC ───────────────────────────────────────────────────────────────────────

async def test_ttc_new_starter(openai_client, base_cfg):
    msg = "Hi, we just started trying to conceive last month — totally new to all of this."
    results = await _collect("TTC_NEW", msg, openai_client, base_cfg)
    _check(results, "ttc", "ttc_0-6mo", msg)


async def test_ttc_long_journey(openai_client, base_cfg):
    msg = "We've been trying for over 3 years now with no success despite multiple attempts."
    results = await _collect("TTC_3YR", msg, openai_client, base_cfg)
    _check(results, "ttc", "ttc_2yr+", msg)


async def test_ttc_medium_range(openai_client, base_cfg):
    msg = "We've been trying for about 18 months — it's been a frustrating journey."
    results = await _collect("TTC_18MO", msg, openai_client, base_cfg)
    _check(results, "ttc", "ttc_1-2yr", msg)


# ── Diagnosis ─────────────────────────────────────────────────────────────────

async def test_diagnosis_confirmed(openai_client, base_cfg):
    msg = "I was officially diagnosed with diminished ovarian reserve by my gynaecologist last month."
    results = await _collect("DIAG_CONFIRMED", msg, openai_client, base_cfg)
    _check(results, "diagnosis", "diagnosis_confirmed", msg)


async def test_diagnosis_suspected(openai_client, base_cfg):
    msg = "My doctor thinks I might have endometriosis but I haven't had the laparoscopy yet to confirm."
    results = await _collect("DIAG_SUSPECTED", msg, openai_client, base_cfg)
    _check(results, "diagnosis", "diagnosis_suspected", msg)


async def test_diagnosis_none(openai_client, base_cfg):
    # Must be genuinely zero-signal: no tests, no concerns, no doctors involved yet
    msg = "We only just started trying last month. No tests, no concerns — just starting out."
    results = await _collect("DIAG_NONE", msg, openai_client, base_cfg)
    _check(results, "diagnosis", "diagnosis_none", msg)


# ── Urgency ───────────────────────────────────────────────────────────────────

async def test_urgency_high_age(openai_client, base_cfg):
    msg = "I'm turning 41 in two months and I feel like time is really running out for us."
    results = await _collect("URGENCY_HIGH_AGE", msg, openai_client, base_cfg)
    _check(results, "urgency", "urgency_high", msg)


async def test_urgency_high_combined(openai_client, base_cfg):
    msg = "We've been trying for 3 years, I'm 39, and my AMH is low. I feel incredibly urgent about this."
    results = await _collect("URGENCY_HIGH_ALL", msg, openai_client, base_cfg)
    _check(results, "urgency", "urgency_high", msg)


# ── Readiness ─────────────────────────────────────────────────────────────────

async def test_readiness_ready(openai_client, base_cfg):
    msg = "I want to book a consultation with Sonia right away — I'm ready to invest and get started."
    results = await _collect("READY", msg, openai_client, base_cfg)
    _check(results, "readiness", "readiness_ready", msg)


async def test_readiness_exploring(openai_client, base_cfg):
    msg = "I'm just browsing at the moment, not sure if coaching is the right fit for me yet."
    results = await _collect("EXPLORING", msg, openai_client, base_cfg)
    _check(results, "readiness", "readiness_exploring", msg)


async def test_readiness_considering(openai_client, base_cfg):
    msg = "I'm seriously thinking about working with Sonia — what does the programme involve exactly?"
    results = await _collect("CONSIDERING", msg, openai_client, base_cfg)
    _check(results, "readiness", "readiness_considering", msg)


# ── Fit ───────────────────────────────────────────────────────────────────────

async def test_fit_high(openai_client, base_cfg):
    msg = (
        "I've read Sonia's book, followed her for 2 years, I know exactly what programme I want. "
        "I'm ready to invest in proper support."
    )
    results = await _collect("FIT_HIGH", msg, openai_client, base_cfg)
    _check(results, "fit", "fit_high", msg)


async def test_fit_low(openai_client, base_cfg):
    msg = "I randomly saw this page. I'm not pregnant and don't plan to be. Just curious what this is."
    results = await _collect("FIT_LOW", msg, openai_client, base_cfg)
    _check(results, "fit", "fit_low", msg)


# ── Multi-signal: full high-value lead ───────────────────────────────────────

async def test_high_value_lead_all_signals(openai_client, base_cfg):
    """Classic high-value lead — long TTC, age pressure, confirmed diagnosis, ready to book."""
    msg = (
        "We've been trying for 4 years. I'm 40, diagnosed with PCOS, been through two failed IVF cycles. "
        "I've done a lot of research on natural approaches and I'm ready to book with Sonia."
    )
    results = await _collect("HIGH_VALUE_LEAD", msg, openai_client, base_cfg)
    _check(results, "ttc",       "ttc_2yr+",            msg)
    _check(results, "urgency",   "urgency_high",         msg)
    _check(results, "diagnosis", "diagnosis_confirmed",  msg)
    _check(results, "readiness", "readiness_ready",      msg)


# ── Tags reflect full history, not just the last message ─────────────────────

async def test_tags_use_full_conversation_history(openai_client, base_cfg):
    """Tags must be inferred from the whole conversation, not just the latest message."""
    history = [
        make_turn("user",      "We've been trying for 3 years and I'm 42."),
        make_turn("assistant", "Thank you for sharing that. I understand how challenging this journey has been."),
        make_turn("user",      "I was diagnosed with low AMH last year."),
        make_turn("assistant", "I really appreciate you trusting me with that. Low AMH can feel very daunting."),
    ]
    msg = "Okay, what are the next steps to work with Sonia?"
    results = await _collect("HISTORY_TAGS", msg, openai_client, base_cfg, history=history)
    _check(results, "ttc",       "ttc_2yr+",           msg)
    _check(results, "urgency",   "urgency_high",        msg)
    _check(results, "readiness", "readiness_ready",     msg)
