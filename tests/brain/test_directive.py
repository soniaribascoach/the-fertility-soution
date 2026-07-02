"""Pure tests for build_directive (R1). No LLM, no DB."""
from app.services.brain.constants import Action, empty_lead_state
from app.services.brain.controller import decide
from app.services.brain.directive import build_directive
from app.services.brain.extractor import Extraction, SlotDeltas
from app.services.brain import scripts


def ext(intent="other", situation_type="none", oos_signal="none",
        takeover=False, takeover_reason=None, confidence=0.9, **slots):
    deltas = SlotDeltas(**{k: slots.get(k) for k in SlotDeltas.model_fields})
    return Extraction(slot_deltas=deltas, intent=intent, situation_type=situation_type,
                      oos_signal=oos_signal, takeover=takeover,
                      takeover_reason=takeover_reason, confidence=confidence)


def state(slots=None, flags=None, counters=None):
    st = empty_lead_state()
    st["slots"].update(slots or {})
    st["flags"].update(flags or {})
    st["counters"].update(counters or {})
    return st


def qualified():
    return state(
        slots={"trying_duration": "2 years", "age": 38, "treatment_path": "ivf",
               "what_tried": "IVF", "priority_score": 9, "open_to_holistic": True,
               "financial_ready": True, "partner_status": "solo"},
        flags={"explained_role": True, "situation_shared": True},
    )


def _directive_for(st, extraction, cfg=None):
    return build_directive(decide(st, extraction, cfg), cfg)


def test_booking_directive_allows_and_requires_link():
    d = _directive_for(qualified(), ext(intent="ready_to_book"))
    assert d.mode == "BOOK" and d.generate is True
    link = scripts.placeholders()["booking_link"]
    assert link in d.allow_urls
    assert link in d.must_include


def test_discovery_directive_carries_question_and_facts():
    st = state(slots={"trying_duration": "2 years"})
    d = _directive_for(st, ext(intent="shares_situation", diagnosis_detail="PCOS"))
    assert d.mode == "DISCOVERY" and d.generate is True
    assert d.reference_text == scripts.DISCOVERY_QUESTIONS["age"]
    assert "trying_duration" in d.known_facts
    assert d.still_needed  # agenda is non-empty early on


def test_explain_role_disclaimer_is_optional():
    # 5a ("have you considered working with a fertility coach...") is a like-for-like
    # alternate, so the not-a-doctor disclaimer is no longer hard-required.
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9}
    d = _directive_for(state(slots=slots), ext(intent="answers_question"))
    assert d.mode == "EXPLAIN_ROLE"
    assert d.pinned_text is None


def test_price_reveal_allows_figure_and_requires_tokens():
    st = qualified()
    st["counters"]["price_ask_count"] = 1
    d = _directive_for(st, ext(intent="asks_price"))
    assert d.mode == "REVEAL_PRICE" and d.allow_price_figure is True
    assert "$1,500" in d.must_include and "$14,000" in d.must_include


def test_price_deflect_forbids_figure():
    d = _directive_for(qualified(), ext(intent="asks_price"))
    assert d.mode == "DEFLECT_PRICE" and d.allow_price_figure is False
    assert d.must_include == []


def test_oos_is_pinned_verbatim_not_generated():
    d = _directive_for(empty_lead_state(), ext(oos_signal="blocked_tubes", tubes_blocked="both"))
    assert d.mode == "OOS" and d.generate is False
    assert d.pinned_text == scripts.render(Action.OOS_BOTH_TUBES)
    assert d.pause is True and d.add_tag is True


def test_takeover_sends_nothing():
    d = _directive_for(empty_lead_state(), ext(intent="is_this_ai", takeover=True))
    assert d.generate is False and d.send_message is False
    assert d.pinned_text is None and d.pause is True


def test_send_booking_directive_is_qualified_handoff():
    d = _directive_for(qualified(), ext(intent="ready_to_book"))
    assert d.qualified is True and d.pause is True


def test_explain_role_uses_short_guidance_not_long_script():
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9}
    d = _directive_for(state(slots=slots), ext(intent="answers_question"))
    # Short guidance reference + a tighter length budget than the long verbatim script.
    assert d.max_chars <= 600
    assert d.reference_text != scripts.render(Action.EXPLAIN_ROLE)


def test_masterclass_allows_only_register_link():
    d = _directive_for(empty_lead_state(), ext(intent="asks_masterclass"))
    reg = scripts.placeholders()["register_link"]
    assert d.allow_urls == [reg] and reg in d.must_include
