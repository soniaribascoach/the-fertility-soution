"""Pure tests for build_directive (R1). No LLM, no DB."""
from app.services.brain.constants import Action, empty_lead_state
from app.services.brain.controller import decide
from app.services.brain.directive import build_directive
from app.services.brain.extractor import Extraction, SlotDeltas
from app.services.brain import scripts


def ext(intent="other", situation_type="none", oos_signal="none",
        takeover=False, takeover_reason=None, confidence=0.9, language="en", **slots):
    deltas = SlotDeltas(**{k: slots.get(k) for k in SlotDeltas.model_fields})
    return Extraction(slot_deltas=deltas, intent=intent, situation_type=situation_type,
                      oos_signal=oos_signal, language=language, takeover=takeover,
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


def test_explain_role_disclaimer_required():
    # Sonia v1.1: the role step must always answer plainly and carry the
    # not-a-doctor disclaimer (the old style-B coach-question alternate is gone).
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9}
    d = _directive_for(state(slots=slots), ext(intent="answers_question"))
    assert d.mode == "EXPLAIN_ROLE"
    assert d.pinned_text == "not a doctor"


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


def test_unsupported_language_sends_nothing():
    d = _directive_for(empty_lead_state(), ext(language="other"))
    assert d.action == Action.UNSUPPORTED_LANGUAGE
    assert d.generate is False and d.send_message is False
    assert d.pinned_text is None and d.pause is True and d.add_tag is True


def test_language_threads_from_lead_state():
    st = empty_lead_state()
    st["slots"]["trying_duration"] = "1 year"
    d = _directive_for(st, ext(language="es", intent="shares_situation"))
    assert d.language == "es"

    d_default = _directive_for(empty_lead_state(), ext(intent="shares_situation"))
    assert d_default.language == "en"


def test_es_oos_decline_is_pinned_spanish_verbatim():
    d = _directive_for(empty_lead_state(), ext(language="es", oos_signal="age_over_46", age=49))
    assert d.generate is False
    assert d.pinned_text == scripts.render(Action.OOS_AGE_OVER_46, None, "es")


def test_es_max_chars_bumped_and_disclaimer_key_spanish():
    slots = {"language": "es", "trying_duration": "2 años", "age": 38,
             "treatment_path": "ivf", "priority_score": 9}
    st = state(slots=slots)
    d = _directive_for(st, ext(language="es", intent="answers_question"))
    assert d.action == Action.EXPLAIN_ROLE
    en_d = _directive_for(state(slots={**slots, "language": None}),
                          ext(intent="answers_question"))
    assert d.max_chars == int(en_d.max_chars * 1.2)
    assert d.pinned_text == "no soy doctora"


def test_es_discovery_brief_carries_spanish_question():
    st = state(slots={"language": "es"})
    d = _directive_for(st, ext(language="es", intent="shares_situation"))
    assert d.action == Action.ASK_DISCOVERY
    assert d.reference_text == scripts.DISCOVERY_QUESTIONS_ES["trying_duration"]


def test_es_price_reveal_requires_spanish_range_tokens():
    st = state(slots={"language": "es", "trying_duration": "2 años", "age": 38,
                      "treatment_path": "ivf"},
               counters={"price_ask_count": 1})
    d = _directive_for(st, ext(language="es", intent="asks_price"))
    assert d.action == Action.PRICE_RANGE and d.allow_price_figure
    rendered = scripts.render(Action.PRICE_RANGE, None, "es")
    for token in d.must_include:
        assert token in rendered, (token, rendered)


def test_send_booking_directive_is_qualified_but_not_paused():
    # Sonia v1.2: tagged qualified, but the AI stays live for the post-booking turns.
    d = _directive_for(qualified(), ext(intent="ready_to_book"))
    assert d.qualified is True and d.pause is False


def test_post_booking_email_directive_requires_the_prep_link():
    d = _directive_for(qualified(), ext(intent="ready_to_book"))
    d2 = _directive_for(d.lead_state, ext(intent="booked"))
    assert d2.action == Action.POST_BOOKING_ASK_EMAIL
    prep = scripts.placeholders()["prep_link"]
    assert prep in d2.allow_urls and prep in d2.must_include
    # The booking link must NOT be re-emitted on this turn.
    assert scripts.placeholders()["booking_link"] not in d2.allow_urls


def test_explain_role_uses_short_guidance_not_long_script():
    slots = {"trying_duration": "2y", "age": 38, "treatment_path": "ivf", "priority_score": 9}
    d = _directive_for(state(slots=slots), ext(intent="answers_question"))
    # Short guidance reference + a tighter length budget than the long verbatim script.
    assert d.max_chars <= 600
    assert d.reference_text != scripts.render(Action.EXPLAIN_ROLE)


def test_multi_fact_turn_asks_priority_with_reflection():
    # Sonia v1.1: several new facts in one message -> the priority-question
    # brief tells the Voice to reflect them back first, with room to do it.
    d = _directive_for(empty_lead_state(),
                       ext(intent="shares_situation", age=39,
                           trying_duration="2 years", what_tried="2 failed IUIs"))
    assert d.action == Action.ASK_PRIORITY
    assert d.objective.startswith("She just shared several new details")
    assert d.max_chars == 440


def test_single_fact_turn_asks_priority_without_reflection_prefix():
    st = state(slots={"trying_duration": "2 years", "what_tried": "2 IUIs"})
    d = _directive_for(st, ext(intent="shares_situation", age=41))
    assert d.action == Action.ASK_PRIORITY
    assert not d.objective.startswith("She just shared")
    assert d.max_chars == 320


def test_masterclass_allows_only_register_link():
    d = _directive_for(empty_lead_state(), ext(intent="asks_masterclass"))
    reg = scripts.placeholders()["register_link"]
    assert d.allow_urls == [reg] and reg in d.must_include
