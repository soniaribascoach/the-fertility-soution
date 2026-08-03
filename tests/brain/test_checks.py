"""Pure output-check tests (no LLM, no DB).

These enforce the promises made to Sonia about what a reply may and may not
contain. The question-policy tests are the ones that answer her complaint that
"it appears to believe that every message must end with a question".
"""
import pytest

from app.services.brain.checks import (
    ground,
    no_echo,
    no_reask,
    no_repeat,
    run_all,
    validate_draft,
)
from app.services.brain.constants import ResponseMode
from app.services.brain.writer import MODE_SPECS, truncate_at_link

LINK = "https://www.thefertilitysolution.com/free-call"


# --- question policy, enforced in both directions ----------------------------

@pytest.mark.parametrize("mode", [
    ResponseMode.CELEBRATE, ResponseMode.ACKNOWLEDGE, ResponseMode.HONEST_DECLINE,
])
def test_a_question_is_rejected_where_it_is_forbidden(mode):
    """Sonia: 'Sometimes the best response is simply to congratulate someone.'"""
    r = validate_draft(["congratulations!! how are you feeling?"], mode=mode, allow_urls=[])
    assert not r.ok
    assert "question_not_allowed" in r.violations


@pytest.mark.parametrize("mode", [
    ResponseMode.CELEBRATE, ResponseMode.ACKNOWLEDGE, ResponseMode.HONEST_DECLINE,
])
def test_no_question_is_accepted_where_it_is_forbidden(mode):
    assert validate_draft(["congratulations, that's such wonderful news."],
                          mode=mode, allow_urls=[]).ok


def test_qualify_must_ask_exactly_one_question():
    assert validate_draft(["got it. how old are you?"],
                          mode=ResponseMode.QUALIFY, allow_urls=[]).ok
    none = validate_draft(["got it, thanks."], mode=ResponseMode.QUALIFY, allow_urls=[])
    assert "expected_exactly_one_question" in none.violations
    two = validate_draft(["how old are you? and how long have you been trying?"],
                         mode=ResponseMode.QUALIFY, allow_urls=[])
    assert "expected_exactly_one_question" in two.violations


def test_answer_mode_may_ask_nothing():
    """The old validator capped questions at one but never permitted zero, which
    is why every reply ended in one."""
    assert validate_draft(["yes, six weeks is genuinely enough time to shift things."],
                          mode=ResponseMode.ANSWER, allow_urls=[]).ok


# --- links --------------------------------------------------------------------

def test_link_is_rejected_when_not_permitted():
    r = validate_draft([f"here you go {LINK}"], mode=ResponseMode.QUALIFY, allow_urls=[])
    assert "disallowed_url" in r.violations


def test_permitted_link_is_accepted_and_required():
    assert validate_draft([f"here's the link to book: {LINK}"],
                          mode=ResponseMode.BOOK, allow_urls=[LINK]).ok
    missing = validate_draft(["let's get you booked in."],
                             mode=ResponseMode.BOOK, allow_urls=[LINK])
    assert "missing_required_url" in missing.violations


def test_a_different_link_is_still_rejected():
    r = validate_draft(["try https://evil.example.com/book"],
                       mode=ResponseMode.BOOK, allow_urls=[LINK])
    assert "disallowed_url" in r.violations


# --- medical, price, format ---------------------------------------------------

@pytest.mark.parametrize("text", [
    "take 400 mg of CoQ10", "the dosage matters", "toma 600 mcg de folato",
    # Plurals: `\bdosage\b` silently missed "dosages", which is the more natural
    # phrasing and so the one that actually slipped through in a live run.
    "I can suggest dosages", "we adjust doses later", "about 400 milligrams",
])
def test_dosage_language_is_rejected(text):
    assert "medical_advice" in validate_draft([text], mode=ResponseMode.ANSWER,
                                              allow_urls=[]).violations


def test_disclaimer_wording_is_not_flagged_as_medical():
    """'prescribe' and 'protocol' appear in Sonia's own not-a-doctor line."""
    assert validate_draft(
        ["i'm a coach, not a doctor, so i don't prescribe anything or run protocols."],
        mode=ResponseMode.ANSWER, allow_urls=[],
    ).ok


def test_price_is_rejected_unless_allowed():
    assert "unexpected_price" in validate_draft(
        ["it's $4,000"], mode=ResponseMode.ANSWER, allow_urls=[]).violations
    assert validate_draft(["it's $4,000"], mode=ResponseMode.ANSWER,
                          allow_urls=[], allow_price=True).ok


@pytest.mark.parametrize("text,violation", [
    ("this is **bold**", "markdown"),
    ("- a bullet point here", "markdown"),
    ("a thought, then, another one", None),
    ("a thought — then another", "em_dash"),
])
def test_format_rules(text, violation):
    r = validate_draft([text], mode=ResponseMode.ACKNOWLEDGE, allow_urls=[])
    if violation:
        assert violation in r.violations
    else:
        assert r.ok


def test_banned_openers_are_caught_as_a_backstop():
    r = validate_draft(["I hear you, that sounds hard."],
                       mode=ResponseMode.ACKNOWLEDGE, allow_urls=[])
    assert any(v.startswith("banned_phrase") for v in r.violations)


def test_bubble_and_length_budgets():
    spec = MODE_SPECS[ResponseMode.CELEBRATE]
    too_many = validate_draft(["a"] * (spec.bubbles[1] + 1),
                              mode=ResponseMode.CELEBRATE, allow_urls=[])
    assert "too_many_bubbles" in too_many.violations
    too_long = validate_draft(["x" * (spec.max_chars + 1)],
                              mode=ResponseMode.CELEBRATE, allow_urls=[])
    assert "too_long" in too_long.violations


def test_empty_reply_is_a_violation():
    assert validate_draft(["  "], mode=ResponseMode.ANSWER, allow_urls=[]).violations == ["empty"]


# --- grounding ----------------------------------------------------------------

def test_invented_number_is_rejected():
    """The 'you said your AMH was fine, right?' failure mode."""
    r = ground(["your AMH of 0.6 is workable"], lead_texts=["can you help me?"],
               knowledge_texts=[], known_facts={})
    assert any(v.startswith("invented_number") for v in r.violations)


def test_number_she_actually_said_is_fine():
    assert ground(["an AMH of 0.6 tells us about quantity, not quality"],
                  lead_texts=["my AMH is 0.6"], knowledge_texts=[], known_facts={}).ok


def test_number_from_approved_knowledge_is_fine():
    assert ground(["over 700 families so far"], lead_texts=["does it work?"],
                  knowledge_texts=["more than 700 families supported"], known_facts={}).ok


def test_small_numbers_are_not_policed():
    # Scale references and ordinary counts would otherwise produce constant noise.
    assert ground(["on a scale of 1 to 10, where are you?"], lead_texts=[""],
                  knowledge_texts=[], known_facts={}).ok


def test_invented_email_is_rejected():
    r = ground(["i've got you down as her@example.com"], lead_texts=["i booked!"],
               knowledge_texts=[], known_facts={})
    assert "invented_email" in r.violations


# --- no repeats ---------------------------------------------------------------

def test_repeating_an_earlier_sentence_is_rejected():
    """Sonia quoted 'How long have you been trying and what have you already
    done?' as appearing across very different conversations."""
    history = [{"role": "assistant",
                "content": "How long have you been trying, and what have you already tried?"}]
    r = no_repeat(["How long have you been trying and what have you already tried?"], history)
    assert not r.ok


def test_a_fresh_sentence_is_accepted():
    history = [{"role": "assistant", "content": "How long have you been trying?"}]
    assert no_repeat(["what has the last year actually looked like for you?"], history).ok


def test_short_fragments_are_not_compared():
    history = [{"role": "assistant", "content": "got it."}]
    assert no_repeat(["got it."], history).ok


# --- no echoing her back ------------------------------------------------------

def test_parroting_the_lead_is_rejected():
    """Seen live: a "just send me the booking link" turn came back opening with
    her own sentence. The transcript is in the writer's prompt and a small model
    will sometimes continue it instead of replying to it."""
    lead = ["just send me the booking link"]
    r = no_echo(["just send me the booking link. I can feel how much you want this."], lead)
    assert not r.ok
    assert r.violations[0].startswith("echoed_lead")


def test_echoing_a_whole_bubble_is_rejected():
    lead = ["I have been trying for two years and nothing has worked"]
    assert not no_echo(["I have been trying for two years and nothing has worked"], lead).ok


def test_a_real_reply_is_not_an_echo():
    lead = ["just send me the booking link"]
    assert no_echo(["before I do that, can I ask what's been going on?"], lead).ok


def test_short_lead_messages_are_not_echo_checked():
    # "yes" appearing in a reply must not trip this.
    assert no_echo(["yes, that's exactly the kind of thing I look at"], ["yes"]).ok


# --- no re-asking -------------------------------------------------------------

def test_reasking_a_known_fact_is_rejected():
    """Sonia: 'It repeatedly asks for information that the prospect has already
    provided.'"""
    r = no_reask(["so how old are you?"], {"age": 38})
    assert not r.ok
    assert r.violations == ["reask:age"]


def test_asking_an_unknown_fact_is_fine():
    assert no_reask(["so how old are you?"], {"trying_duration": "2 years"}).ok


def test_reask_check_covers_what_she_already_tried():
    assert not no_reask(["what have you tried so far?"], {"what_tried": "4 IVF cycles"}).ok


# --- few-shot link truncation -------------------------------------------------

def test_exemplar_is_cut_before_the_link():
    """Gen 2 sent 17 transcripts that nearly all ended with Sonia pasting the
    booking link, which taught the model that conversations end that way."""
    messages = [
        {"role": "user", "content": "i've been trying 2 years"},
        {"role": "assistant", "content": "that's a long time to carry."},
        {"role": "user", "content": "yes it is"},
        {"role": "assistant", "content": f"here's my link: {LINK}"},
    ]
    out = truncate_at_link(messages)
    assert len(out) == 2
    assert all(LINK not in m["content"] for m in out)


def test_truncation_never_ends_on_an_unanswered_user_turn():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": f"book here {LINK}"},
    ]
    assert truncate_at_link(messages) == []


def test_truncation_leaves_link_free_exemplars_alone():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey, what's been going on?"},
    ]
    assert truncate_at_link(messages) == messages


# --- everything together ------------------------------------------------------

def test_run_all_collects_violations_from_every_layer():
    r = run_all(
        [f"I hear you. your AMH of 0.9 is fine. book here {LINK}"],
        mode=ResponseMode.ACKNOWLEDGE, allow_urls=[], allow_price=False,
        history=[], lead_texts=["hello"], knowledge_texts=[], known_facts={},
    )
    assert not r.ok
    assert "disallowed_url" in r.violations
    assert any(v.startswith("banned_phrase") for v in r.violations)
    assert any(v.startswith("invented_number") for v in r.violations)


def test_a_clean_reply_passes_everything():
    assert run_all(
        ["that's a lot to be carrying after four rounds.",
         "and it makes sense you'd want something different this time."],
        mode=ResponseMode.ACKNOWLEDGE, allow_urls=[], allow_price=False,
        history=[], lead_texts=["i've done 4 rounds of ivf"],
        knowledge_texts=[], known_facts={},
    ).ok


# --- cross-conversation sameness ---------------------------------------------
# Sonia: "We repeatedly saw phrases such as 'I hear you' ... used across very
# different conversations and objections, making the replies feel automated."
# `no_repeat` only ever sees one thread, so it cannot see this at all.

def test_an_opening_already_used_on_another_lead_is_rejected():
    from app.services.brain.checks import no_stock_opening

    r = no_stock_opening(
        ["I hear you, that sounds really tough.", "how long has it been?"],
        ["I hear you, that sounds really tough."],
    )
    assert not r.ok
    assert any(v.startswith("stock_opening") for v in r.violations)


def test_a_fresh_opening_passes():
    from app.services.brain.checks import no_stock_opening

    assert no_stock_opening(
        ["four rounds is a lot to have carried."],
        ["I hear you, that sounds really tough.",
         "that's such good news, congratulations!"],
    ).ok


def test_only_the_opening_is_compared():
    """Two replies may legitimately share a later sentence - an approved
    boundary, a link instruction. A shared OPENING is what makes a set of
    conversations read as one template."""
    from app.services.brain.checks import no_stock_opening

    assert no_stock_opening(
        ["four rounds is a lot to have carried.",
         "I don't give supplement protocols over DM."],
        ["I don't give supplement protocols over DM."],
    ).ok


def test_no_history_of_other_leads_is_not_a_violation():
    from app.services.brain.checks import no_stock_opening

    assert no_stock_opening(["anything at all."], []).ok


def test_a_stock_opening_is_soft():
    """Worth a regeneration, never worth silence: sending nothing costs the lead
    far more than a familiar opening line does."""
    from app.services.brain.checks import is_hard

    assert not is_hard("stock_opening:I hear you")
