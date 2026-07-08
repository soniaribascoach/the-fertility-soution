"""Pure unit tests for the output validator (Step 6). No LLM, no DB."""
from app.services.brain.constants import Action
from app.services.brain import scripts
from app.services.brain.validator import validate, validate_generated
from app.services.brain.directive import TurnDirective


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


# --- Spanish -------------------------------------------------------------------

def _gen_directive(**kw):
    defaults = dict(mode="DISCOVERY", action=Action.ASK_DISCOVERY, generate=True,
                    objective="", reference_text="", language="es")
    defaults.update(kw)
    return TurnDirective(**defaults)


def test_spanish_medical_advice_rejected():
    for text in ("toma 50 mg de clomifeno", "la dosis recomendada es alta",
                 "toma 400 ui de vitamina D", "unos 200 microgramos al día"):
        r = validate_generated(_gen_directive(), text + " ¿cuántos años tienes?")
        assert not r.ok and "medical_advice" in r.violations, text


def test_inverted_question_marks_count_once():
    r = validate_generated(_gen_directive(), "entiendo, gracias por contarme. ¿Cuántos años tienes?")
    assert r.ok, r.violations


def test_spanish_disclaimer_accent_folded():
    d = _gen_directive(pinned_text="no soy doctora")
    ok = "Soy coach de fertilidad, NO SOY DOCTORA ni clínica. ¿Te interesa ese apoyo?"
    assert validate_generated(d, ok).ok
    missing = "Soy coach de fertilidad y te acompaño. ¿Te interesa ese apoyo?"
    r = validate_generated(d, missing)
    assert not r.ok and "missing_disclaimer" in r.violations


def test_spanish_verbatim_scripts_pass_and_english_text_fails():
    for action in scripts.SCRIPTS_ES:
        text = scripts.render(action, None, "es")
        assert validate(action, text, None, "es").ok, action
    # The English render must NOT pass as the Spanish verbatim.
    r = validate(Action.OOS_MENOPAUSE, scripts.render(Action.OOS_MENOPAUSE), None, "es")
    assert not r.ok and "not_verbatim" in r.violations


def test_spanish_length_budget_uses_directive_max_chars():
    text = ("te entiendo perfectamente y quiero acompañarte en esto con calma. " * 6
            + "¿Cuántos años tienes?")
    assert len(text) > 400
    assert validate_generated(_gen_directive(max_chars=480), text).ok
    assert "too_long" in validate_generated(_gen_directive(max_chars=400), text).violations


# --- Banned phrases (Sonia v1.1 regression backstop) ---------------------------

def test_banned_phrase_rejected_in_generated():
    d = _gen_directive(language="en")
    r = validate_generated(d, "Working with a coach can help elevate your chances. How old are you?")
    assert not r.ok and any(v.startswith("banned_phrase:") for v in r.violations)


def test_banned_phrase_matching_is_case_and_whitespace_insensitive():
    d = _gen_directive(language="en")
    r = validate_generated(d, "I can help Elevate  your\nchances of getting pregnant. How old are you?")
    assert not r.ok and any(v.startswith("banned_phrase:") for v in r.violations)


def test_banned_phrase_spanish_accent_folded():
    r = validate_generated(_gen_directive(), "puedo ayudarte a elevár tus posibilidades. ¿Cuántos años tienes?")
    assert not r.ok and any(v.startswith("banned_phrase:") for v in r.violations)


def test_banned_phrase_rejected_in_composed_discovery():
    r = validate(Action.ASK_DISCOVERY,
                 "Please take care of yourself in the meantime. How old are you?")
    assert not r.ok and any(v.startswith("banned_phrase:") for v in r.violations)


def test_grounded_text_passes_banned_phrase_check():
    d = _gen_directive(language="en")
    r = validate_generated(d, "Two years is a long time to carry this. How old are you?")
    assert r.ok, r.violations
