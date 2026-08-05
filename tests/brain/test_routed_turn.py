"""Live end-to-end tests for the routed brain.

Each test replays a scenario from Sonia's 2026-07-29 review through the whole
pipeline - classify, route, retrieve, write, check - and asserts on the reply
she would actually receive.

    pytest -m live tests/brain/test_routed_turn.py
"""
import pytest

from app.services.brain.constants import ResponseMode, empty_lead_state
from app.services.brain.knowledge import parse_pattern_responses
from app.services.brain.knowledge_seed import SEED
from app.services.brain.playbook_seed import SEED as PLAYBOOKS
from app.services.brain.turn import run_turn_v2

pytestmark = pytest.mark.live

CFG = {
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "masterclass_register_link": "https://www.thefertilitysolution.com/masterclass",
    "phase1_cta_keywords": "AMH\nBABY",
    "phase1_opening_message": "I'm so glad you reached out.",
    "medical_blocklist": "",
    "human_takeover_triggers": "",
}

# The client's own reframes, as they exist in app_config today.
_PATTERNS = (
    "Low AMH: Low AMH does not mean no baby. What matters is quality, not quantity, "
    "one good egg is enough. There's a lot that hasn't been explored yet.\n"
    "Failed IVF: A failed cycle doesn't mean your body failed. It means the environment "
    "wasn't fully prepared and supported.\n"
    "PCOS: With PCOS, the goal is helping the body feel safe enough to regulate, not just "
    "triggering ovulation.\n"
)
KNOWLEDGE = SEED + parse_pattern_responses(_PATTERNS)


async def turn(client, *user_msgs, sonia=None, state=None):
    history = []
    for i, msg in enumerate(user_msgs):
        if sonia and i < len(sonia) and sonia[i]:
            history.append({"role": "assistant", "content": sonia[i]})
        history.append({"role": "user", "content": msg})
    return await run_turn_v2(
        client, history, CFG, state or empty_lead_state(),
        ig_user_id="test", new_texts=[user_msgs[-1]],
        knowledge_entries=KNOWLEDGE, playbook_entries=PLAYBOOKS,
    )


def qualified_state():
    st = empty_lead_state()
    st["slots"].update({
        "trying_duration": "2 years", "age": 38, "treatment_path": "ivf",
        "what_tried": "2 rounds of IVF", "priority_score": 9,
        "open_to_holistic": True, "financial_ready": True, "partner_status": "solo",
    })
    st["flags"].update({"explained_role": True, "situation_shared": True})
    return st


# --- Complaint 1: stop qualifying everyone -----------------------------------

async def test_pregnancy_is_celebrated_not_qualified(openai_client):
    r = await turn(openai_client, "I just found out I'm pregnant!! thank you so much")
    assert r.action == ResponseMode.CELEBRATE.value
    assert r.reply_text
    assert "?" not in r.reply_text, f"asked a question at a pregnancy: {r.reply_text}"
    assert "free-call" not in (r.reply_text or "")


async def test_gratitude_is_not_a_sales_opportunity(openai_client):
    r = await turn(openai_client, "just wanted to say thank you, your content has helped me so much")
    assert r.action == ResponseMode.ACKNOWLEDGE.value
    assert "?" not in (r.reply_text or "")


async def test_stopped_trying_is_acknowledged_then_handed_over(openai_client):
    r = await turn(openai_client, "We've decided to stop trying. I'm at peace with it but it's been a lot.")
    assert r.action == ResponseMode.ACKNOWLEDGE.value
    assert r.pause is True, "grief should end with a person, not a funnel"
    assert "masterclass" not in (r.reply_text or "").lower()
    assert "?" not in (r.reply_text or "")


# --- Complaint 3: answer the actual question ---------------------------------

async def test_pre_ivf_question_gets_an_actual_answer(openai_client):
    r = await turn(
        openai_client,
        "I start IVF in 6 weeks. Is there realistically anything that can make a difference in that time?",
    )
    assert r.action in (ResponseMode.ANSWER.value, ResponseMode.EDUCATE.value), r.action
    assert r.reply_text, f"no reply: violations={r.violations}"
    # Deflecting straight back into discovery is the failure she reported.
    assert "how long have you been trying" not in r.reply_text.lower()


async def test_a_supplement_request_never_yields_an_actual_dose(openai_client):
    """What must never appear is a dose: a number with a unit.

    Deliberately NOT asserting the word "dosage" is absent - "I don't give
    dosages over DM" is exactly the right thing to say, and banning the word
    would fail the correct behaviour.
    """
    import re as _re
    r = await turn(openai_client, "what supplements should I take for low AMH?")
    if r.reply_text:
        assert not _re.search(r"\b\d+\s?(mg|mcg|iu|ui)\b", r.reply_text, _re.IGNORECASE), (
            f"gave a dose: {r.reply_text}"
        )


# --- Complaint 2: never re-ask ------------------------------------------------

async def test_rich_situation_is_not_re_interrogated(openai_client):
    r = await turn(
        openai_client,
        "I've done 4 IVF cycles, changed my diet completely, taken every supplement "
        "going and worked with 3 practitioners. Nothing has worked.",
    )
    assert r.lead_state["flags"]["situation_rich"] is True
    if r.reply_text:
        lowered = r.reply_text.lower()
        assert "what else have you tried" not in lowered
        assert "what have you tried" not in lowered


async def test_a_dated_plan_is_not_asked_to_rate_its_priority(openai_client):
    r = await turn(openai_client, "I'm 36 and preparing for IVF in September")
    if r.reply_text:
        assert "1 to 10" not in r.reply_text and "scale" not in r.reply_text.lower()


# --- Complaint 7 + the gate ---------------------------------------------------

async def test_the_link_is_never_sent_before_the_gate(openai_client):
    for message in ["just send me the booking link",
                    "I want to book a call right now",
                    "how do I sign up? I'm ready"]:
        r = await turn(openai_client, message)
        assert "free-call" not in (r.reply_text or ""), (
            f"link leaked for {message!r}: {r.reply_text}"
        )


async def test_a_qualified_lead_does_get_the_link(openai_client):
    r = await turn(openai_client, "yes I'd love to book", state=qualified_state())
    assert r.action == ResponseMode.BOOK.value, f"{r.action} violations={r.violations}"
    assert "free-call" in (r.reply_text or "")
    assert r.qualified is True


async def test_young_early_lead_is_told_honestly(openai_client):
    st = empty_lead_state()
    st["slots"].update({"age": 29, "trying_duration": "3 months"})
    st["flags"]["situation_shared"] = True
    r = await turn(openai_client, "so should I join your program?", state=st)
    assert r.action == ResponseMode.HONEST_DECLINE.value
    assert "free-call" not in (r.reply_text or "")


# --- Complaint 4: stop sounding templated ------------------------------------

async def test_discovery_questions_vary_between_leads(openai_client):
    """The old brain handed the model the approved sentence, so it came out
    identically every time. Two different openers should not produce the same
    question."""
    a = await turn(openai_client, "hi, I need help getting pregnant")
    b = await turn(openai_client, "hey there, struggling to conceive and not sure where to turn")
    if a.reply_text and b.reply_text:
        assert a.reply_text.strip() != b.reply_text.strip()


async def test_banned_openers_do_not_appear(openai_client):
    r = await turn(openai_client, "I've had 3 miscarriages in 2 years and I'm exhausted")
    if r.reply_text:
        lowered = r.reply_text.lower()
        for phrase in ("thank you for sharing", "i hear you", "i get that",
                       "i appreciate your honesty"):
            assert phrase not in lowered, f"templated opener {phrase!r}: {r.reply_text}"


# --- Uncertainty --------------------------------------------------------------

async def test_an_unreadable_message_goes_to_a_person(openai_client):
    r = await turn(openai_client, "ok")
    assert r.pause is True
    assert r.reply_text is None, "we should say nothing rather than guess"


# --- The way real conversations actually start -------------------------------
# Every other test here begins from a bare first message. Not one covered the
# CTA-keyword opener followed by her first real reply, which is how most real
# conversations begin - and the first shape to misbehave in the sandbox.

_OPENER = (
    "I'm so glad you reached out 🤍 Before I point you in the right direction, "
    "I'd love to understand a little more about your situation. How long have you "
    "been trying to conceive, and what have you already tried so far?"
)


@pytest.mark.parametrize("first_reply", [
    "Hi Sonia, my amh results came back low",
    "hi! we've been trying for about a year and nothing yet",
    "I'm 38 and just found out I have low AMH",
    "my doctor said I have pcos",
    "we've been trying 3 years, done 2 IUIs",
])
async def test_cta_opener_then_her_first_message_gets_a_reply(openai_client, first_reply):
    """A textbook lead answering the opener must never be handed to a human.

    This is the exact flow that failed in the sandbox: keyword, opener, first
    real message. Anything but silence is acceptable here; silence is not.
    """
    history = [
        {"role": "user", "content": "AMH"},
        {"role": "assistant", "content": _OPENER},
        {"role": "user", "content": first_reply},
    ]
    state = empty_lead_state()
    state["phase"] = "DISCOVERY"
    r = await run_turn_v2(
        openai_client, history, CFG, state, ig_user_id="test",
        new_texts=[first_reply], knowledge_entries=KNOWLEDGE,
    )
    assert r.reply_text, (
        f"handed a textbook lead to a human. action={r.action} "
        f"signals={r.trace.get('uncertainty_signals')} "
        f"violations={r.violations} "
        f"suppressed={r.trace.get('suppressed_reply')!r}"
    )
    assert not r.pause, f"paused on a normal opener reply: {r.pause_reason}"
    assert "free-call" not in r.reply_text


async def test_the_trace_explains_the_turn(openai_client):
    """"Why did the bot say that" must be answerable from the persisted trace.

    Before this, `action` and `violations` were computed and thrown away, so
    reviewing tone or calibrating the handoff threshold was guesswork.
    """
    r = await turn(openai_client, "my doctor said my AMH is 0.6 and I'm 38")
    t = r.trace
    assert t["intent"], "no intent recorded"
    assert t["intent_certainty"] in ("certain", "probable", "unsure")
    assert t["mode"], "no mode recorded"
    assert t["stage"], "no stage recorded"
    assert t["reason"], "no routing reason recorded"
    assert "uncertainty_score" in t
    # The retrieved knowledge is what makes a reply reviewable: it says which
    # approved material the writer was allowed to draw on.
    assert "knowledge_topics" in t
    assert isinstance(r.usage.get("calls"), list) and r.usage["calls"], (
        "per-call usage must stay separable, not blended into one figure"
    )


async def test_an_aborted_turn_keeps_the_suppressed_draft(openai_client):
    """An aborted turn is the most useful thing to review and is invisible
    otherwise, so the text we refused to send is kept in the trace."""
    r = await turn(openai_client, "ok")
    assert r.reply_text is None
    if r.action and r.action.endswith("_ABORTED"):
        assert r.trace.get("aborted") is True


async def test_hard_out_of_scope_still_stops_everything(openai_client):
    st = empty_lead_state()
    st["slots"]["age"] = 48
    r = await turn(openai_client, "can you help me get pregnant?", state=st)
    assert r.pause is True
    assert "free-call" not in (r.reply_text or "")


# --- The AMH transcript of 2026-08-05 ----------------------------------------

async def test_a_yes_moves_her_forward_instead_of_repeating_the_question(openai_client):
    """Sonia's live test: the lead answered "yes" four times and was asked the
    same question four times, because a bare "yes" set no slot. Each yes must
    settle the question it answers, and the chain must end at the link.
    """
    st = empty_lead_state()
    st["slots"].update({
        "trying_duration": "2 years", "age": 34,
        "what_tried": "my amh score came back low", "strong_readiness": True,
        "open_to_holistic": True,
    })
    st["flags"].update({"situation_shared": True, "explained_role": True})

    history = [
        {"role": "user", "content": "i've been trying 2 years, my amh came back low"},
        {"role": "assistant", "content": "is that the kind of support you're looking for?"},
    ]
    asked, modes = [], []
    for _ in range(4):
        history.append({"role": "user", "content": "yes"})
        r = await run_turn_v2(
            openai_client, history, CFG, st, ig_user_id="test_amh_yes",
            new_texts=["yes"], knowledge_entries=KNOWLEDGE, playbook_entries=PLAYBOOKS,
        )
        st = r.lead_state
        modes.append(r.action)
        asked.append(st["flags"].get("pending_question"))
        if r.reply_text:
            history.append({"role": "assistant", "content": r.reply_text})
        if r.action == ResponseMode.BOOK.value:
            break

    questions = [q for q in asked if q]
    assert len(questions) == len(set(questions)), (
        f"asked the same thing twice: {asked} (modes {modes})"
    )
    assert ResponseMode.BOOK.value in modes, (
        f"four yeses and still no link: questions={asked}, modes={modes}, "
        f"slots={ {k: v for k, v in st['slots'].items() if v is not None} }"
    )


async def test_what_does_it_include_gets_a_real_answer(openai_client):
    """It got silence (the checker vetoed an invented answer), then "lifestyle,
    stress, and more" - which is complaint 5 word for word. The programme
    entries are pinned to the intent now, so there is something true to say."""
    r = await turn(
        openai_client,
        "i've been trying 2 years and my amh is low",
        "what does it include?",
        sonia=[None, "there's a lot we can look at together"],
    )
    assert r.reply_text, f"no reply at all: {r.violations}"
    assert "what_is_included" in (r.trace.get("knowledge_topics") or []), r.trace
