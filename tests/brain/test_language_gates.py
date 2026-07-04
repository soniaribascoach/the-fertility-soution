"""Pure tests for the language-aware stage-0 safety gate (no LLM, no DB):
casefold phrase matching (so Spanish phrases in the shared lists work) and
Spanish medical deflection selection by the sticky language slot."""
from app.services.brain import _check_phase1, _safety_gate
from app.services.brain.constants import empty_lead_state


def _first_message(text):
    return [{"role": "user", "content": text}]


def test_phase1_keywords_are_language_agnostic():
    # There is no Spanish CTA list: campaigns are English-only, and a bare
    # keyword carries no language signal. Spanish is entered only when the
    # lead actually writes Spanish (extractor -> sticky slot).
    cfg = {"phase1_cta_keywords": "BABY", "phase1_opening_message": "english opener"}
    assert _check_phase1(cfg, _first_message("BABY")) == "english opener"
    assert _check_phase1(cfg, _first_message("hola, necesito ayuda")) is None


# --- Safety gate ---------------------------------------------------------------

def test_blocklist_matches_accented_spanish_casefolded():
    cfg = {"medical_blocklist": "Clomifeno\nQUÉ DOSIS", "medical_deflection": "en deflection"}
    r = _safety_gate(cfg, ["Qué dosis debería tomar?"], empty_lead_state())
    assert r is not None and r.pause is True
    assert r.reply_text == "en deflection"


def test_spanish_lead_gets_spanish_deflection():
    cfg = {"medical_blocklist": "clomifeno", "medical_deflection": "en deflection",
           "medical_deflection_es": "deflexión en español"}
    state = empty_lead_state()
    state["slots"]["language"] = "es"
    r = _safety_gate(cfg, ["me recetaron clomifeno"], state)
    assert r is not None and r.reply_text == "deflexión en español"


def test_spanish_lead_falls_back_to_english_deflection_when_unset():
    cfg = {"medical_blocklist": "clomifeno", "medical_deflection": "en deflection"}
    state = empty_lead_state()
    state["slots"]["language"] = "es"
    r = _safety_gate(cfg, ["me recetaron clomifeno"], state)
    assert r is not None and r.reply_text == "en deflection"


def test_takeover_triggers_casefold_spanish():
    cfg = {"human_takeover_triggers": "quiero hablar con una persona"}
    r = _safety_gate(cfg, ["QUIERO HABLAR CON UNA PERSONA por favor"], empty_lead_state())
    assert r is not None and r.pause is True and r.reply_text is None
