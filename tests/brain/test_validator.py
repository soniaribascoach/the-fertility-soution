"""Pure unit tests for the output validator (Step 6). No LLM, no DB."""
from app.services.brain.constants import Action
from app.services.brain import scripts
from app.services.brain.validator import validate


# --- Composed (ASK_DISCOVERY) checks ----------------------------------------

def test_clean_discovery_passes():
    r = validate(Action.ASK_DISCOVERY, "Thank you for sharing that. How old are you?")
    assert r.ok, r.violations


def test_url_rejected():
    r = validate(Action.ASK_DISCOVERY, "Here you go: https://x.com How old are you?")
    assert not r.ok and "url" in r.violations


def test_price_number_rejected():
    r = validate(Action.ASK_DISCOVERY, "It's about $1,500. How old are you?")
    assert not r.ok and "money" in r.violations


def test_medical_advice_rejected():
    r = validate(Action.ASK_DISCOVERY, "You should take 600mg of CoQ10. How old are you?")
    assert not r.ok and "medical_advice" in r.violations


def test_em_dash_rejected():
    r = validate(Action.ASK_DISCOVERY, "Two years — that's a long time. How old are you?")
    assert not r.ok and "em_dash" in r.violations


def test_markdown_rejected():
    r = validate(Action.ASK_DISCOVERY, "**Thanks** for sharing. How old are you?")
    assert not r.ok and "markdown" in r.violations


def test_multiple_questions_rejected():
    r = validate(Action.ASK_DISCOVERY, "How old are you? Are you trying naturally?")
    assert not r.ok and any(v.startswith("question_count") for v in r.violations)


def test_zero_questions_rejected():
    r = validate(Action.ASK_DISCOVERY, "Thank you for sharing that.")
    assert not r.ok and any(v.startswith("question_count") for v in r.violations)


def test_too_long_rejected():
    long = "This is a sentence. " * 10 + "How old are you?"
    r = validate(Action.ASK_DISCOVERY, long)
    assert not r.ok and "too_long" in r.violations


# --- Scripted (verbatim) checks ---------------------------------------------

def test_scripted_verbatim_passes():
    text = scripts.render(Action.SEND_BOOKING)
    assert validate(Action.SEND_BOOKING, text).ok


def test_scripted_mutation_rejected():
    text = scripts.render(Action.SEND_BOOKING) + " extra tacked on"
    r = validate(Action.SEND_BOOKING, text)
    assert not r.ok and "not_verbatim" in r.violations


def test_every_scripted_action_passes_its_own_render():
    for action in scripts.SCRIPTS:
        text = scripts.render(action)
        assert validate(action, text).ok, action


# --- Fallback ----------------------------------------------------------------

def test_minimal_discovery_fallback_is_valid():
    text = "Thank you for sharing that. How long have you been trying, and what have you already tried?"
    assert validate(Action.ASK_DISCOVERY, text).ok
