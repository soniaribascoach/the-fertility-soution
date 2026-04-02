"""
test_tone.py — Empathy, warmth, booking flow, and conversation coherence.

Uses the production prompt. GEval judges semantic quality.
AI reply is always printed before any assertion fires.

Run with:  pytest tests/test_tone.py -s -v
"""
import pytest
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval

from tests.conftest import run_reply, make_turn, print_result

pytestmark = pytest.mark.live

TRIALS = 3


# ── GEval helpers ─────────────────────────────────────────────────────────────

def _geval(name, criteria, params=None, threshold=0.7):
    return GEval(
        name=name,
        criteria=criteria,
        evaluation_params=params or [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        threshold=threshold,
    )


def _assert_geval(metric, input_, output, trial, context=None):
    tc = LLMTestCase(input=input_, actual_output=output, context=context)
    metric.measure(tc)
    assert metric.score >= metric.threshold, (
        f"\nTrial {trial}/{TRIALS} — [{metric.name}] FAILED\n"
        f"Score : {metric.score:.2f}  (threshold {metric.threshold})\n"
        f"Reason: {metric.reason}\n"
        f"Reply :\n{output}"
    )


# ── Metrics ───────────────────────────────────────────────────────────────────

_EMPATHY = _geval(
    "Empathy Before Advice",
    "The user has expressed emotional distress. "
    "A PASSING reply leads with genuine emotional acknowledgement before any practical guidance. "
    "Score 1.0 if empathy comes first. Score 0.0 if it jumps straight to advice.",
)

_BOOKING = _geval(
    "Booking Request Handling",
    "The user wants to book a call. A PASSING reply: "
    "(1) responds warmly, (2) includes NO URL or link, "
    "(3) sets the expectation that someone will be in touch. "
    "Score 1.0 if all three. Score 0.0 if a URL appears or the intent is ignored.",
    threshold=0.8,
)

_HISTORY_RECALL = _geval(
    "Conversation History Recall",
    "The conversation context contains details the user already shared (name, age, TTC duration, diagnosis). "
    "A PASSING reply shows awareness of at least one of those details — e.g. uses the user's name, "
    "references their diagnosis, or acknowledges their timeline. "
    "A PASSING reply MAY ask new questions not yet answered in the context — that is normal coaching behaviour. "
    "A FAILING reply ignores the context entirely (treats the user as if they just arrived with no history), "
    "OR explicitly re-asks a question already answered (e.g. 'how long have you been trying?' "
    "when the context already says '2 years'). "
    "Score 1.0 if the reply draws on at least one detail from the context. "
    "Score 0.0 if the reply ignores all prior context.",
    params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.CONTEXT],
    threshold=0.6,
)

# ── Cold/clinical language to avoid (plain keyword check) ────────────────────

_COLD_PHRASES = [
    "clinical trial",
    "refer to a doctor",
    "consult a doctor",
    "consult your doctor",
    "seek medical advice",
    "i cannot diagnose",
]


def _assert_no_cold_language(reply, message):
    lower = reply.lower()
    for phrase in _COLD_PHRASES:
        assert phrase not in lower, (
            f"\nCold/clinical phrase found: {phrase!r}\n"
            f"Input : {message}\nReply :\n{reply}"
        )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_empathy_for_hopelessness(openai_client, base_cfg):
    """Reply must lead with empathy when user feels hopeless. 3 trials."""
    msg = "I've been trying for 2 years and I honestly feel so hopeless. I don't know if this will ever happen for me."
    for trial in range(1, TRIALS + 1):
        result = await run_reply(msg, openai_client, base_cfg)
        print_result("EMPATHY:HOPELESS", trial, TRIALS, msg, result)
        _assert_geval(_EMPATHY, msg, result.reply, trial)


async def test_empathy_after_failed_ivf(openai_client, base_cfg):
    """Grief after failed IVF must be met with warmth first. 3 trials."""
    msg = "After 3 failed IVF cycles I feel completely broken. I don't know where to turn anymore."
    for trial in range(1, TRIALS + 1):
        result = await run_reply(msg, openai_client, base_cfg)
        print_result("EMPATHY:IVF", trial, TRIALS, msg, result)
        _assert_geval(_EMPATHY, msg, result.reply, trial)


async def test_no_cold_clinical_language(openai_client, base_cfg):
    """Replies must never sound like a clinical document."""
    messages = [
        "I have irregular cycles — what could be causing that?",
        "Is it possible to get pregnant naturally at 42?",
        "My AMH is low — what does that mean for my chances?",
    ]
    for msg in messages:
        result = await run_reply(msg, openai_client, base_cfg)
        print_result("COLD_LANG", 1, 1, msg, result)
        _assert_no_cold_language(result.reply, msg)


async def test_booking_request_handled_warmly_no_url(openai_client, base_cfg):
    """Booking request: warm, no URL, team will follow up. 3 trials."""
    msg = "I'd love to book a call with Sonia — where can I do that?"
    for trial in range(1, TRIALS + 1):
        result = await run_reply(msg, openai_client, base_cfg)
        print_result("BOOKING", trial, TRIALS, msg, result)
        _assert_geval(_BOOKING, msg, result.reply, trial)


async def test_first_name_used_naturally(openai_client, base_cfg):
    """When a first name is provided, AI should use it at least once. 3 trials."""
    msg = "Hi, I just wanted to know a bit more about how Sonia works with clients."
    for trial in range(1, TRIALS + 1):
        result = await run_reply(msg, openai_client, base_cfg, first_name="Emma")
        print_result("FIRST_NAME", trial, TRIALS, msg, result)
        assert "Emma" in result.reply, (
            f"\nTrial {trial}/{TRIALS} — 'Emma' not used in reply.\nReply:\n{result.reply}"
        )


async def test_first_name_absent_when_not_provided(openai_client, base_cfg):
    """Without a first name the reply should still be complete and non-empty."""
    msg = "I've been trying to conceive for a year — can you help?"
    result = await run_reply(msg, openai_client, base_cfg, first_name=None)
    print_result("NO_FIRST_NAME", 1, 1, msg, result)
    assert result.reply.strip() != "", "Reply is empty when no first name given"


async def test_conversation_history_coherence(openai_client, base_cfg):
    """Reply must reference details shared in earlier turns. 3 trials."""
    history = [
        make_turn("user",      "Hi, I'm Sarah, I'm 38 years old and I've been trying to conceive for 2 years."),
        make_turn("assistant", "Thank you for sharing that, Sarah. I can hear how much this journey means to you."),
        make_turn("user",      "I was also diagnosed with PCOS last year which has made things harder."),
        make_turn("assistant", "I'm so sorry to hear that. PCOS can add another layer of complexity but there is absolutely hope."),
    ]
    msg = "What do you think my chances are of conceiving naturally at this point?"
    context = [f"{t.role}: {t.content}" for t in history]

    for trial in range(1, TRIALS + 1):
        result = await run_reply(msg, openai_client, base_cfg, history=history)
        print_result("HISTORY_RECALL", trial, TRIALS, msg, result)
        _assert_geval(_HISTORY_RECALL, msg, result.reply, trial, context=context)


async def test_does_not_re_ask_already_answered_questions(openai_client, base_cfg):
    """AI must not re-ask for info the user already gave in history."""
    history = [
        make_turn("user",      "I'm 36, been trying for 18 months, no diagnosis."),
        make_turn("assistant", "Thank you for sharing that. 18 months is a meaningful journey."),
    ]
    msg = "What would be a good first step for someone like me?"
    result = await run_reply(msg, openai_client, base_cfg, history=history)
    print_result("NO_REPEAT_Q", 1, 1, msg, result)

    lower = result.reply.lower()
    repeated_questions = [
        "how long have you been trying",
        "how old are you",
        "what is your age",
        "do you have a diagnosis",
    ]
    for q in repeated_questions:
        assert q not in lower, (
            f"\nAI re-asked: {q!r}\nInput : {msg}\nReply :\n{result.reply}"
        )
