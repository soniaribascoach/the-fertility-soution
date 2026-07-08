"""Pure unit tests for the verbatim script registry (Step 2). No LLM, no DB."""
import pytest

from app.services.brain.constants import Action
from app.services.brain import scripts


# Actions whose verbatim text legitimately contains a URL.
URL_ALLOWED = {
    Action.SEND_BOOKING,
    Action.FINANCIAL_DECLINE,
    Action.EXPLAIN_ROLE_TFS3,
    Action.MASTERCLASS_SEND,
    Action.POST_BOOKING_CONFIRM_NATALIA,
    Action.POST_BOOKING_CONFIRM_MONIKA,
    Action.NURTURE_CLOSE,
}


def test_every_script_renders_with_no_unfilled_placeholder():
    for action in scripts.SCRIPTS:
        text = scripts.render(action)
        assert text.strip(), f"{action} rendered empty"
        assert "{" not in text and "}" not in text, f"{action} has an unfilled placeholder"


def test_ask_discovery_is_not_templated():
    # ASK_DISCOVERY is the only generative action — it must NOT have a template.
    assert Action.ASK_DISCOVERY not in scripts.SCRIPTS
    with pytest.raises(KeyError):
        scripts.render(Action.ASK_DISCOVERY)


def test_human_takeover_has_no_template():
    # Takeover sends nothing; there is deliberately no script for it.
    assert Action.HUMAN_TAKEOVER not in scripts.SCRIPTS


def test_no_em_dashes_anywhere():
    # Honor the no-em-dash preference across all scripted content.
    for action in scripts.SCRIPTS:
        assert "—" not in scripts.render(action), f"em-dash in {action}"
    for name in scripts.FOLLOWUPS:
        assert "—" not in scripts.render_followup(name), f"em-dash in followup {name}"


def test_only_url_allowed_actions_contain_links():
    for action in scripts.SCRIPTS:
        text = scripts.render(action)
        if action in URL_ALLOWED:
            assert "http" in text, f"{action} should contain a URL"
        else:
            assert "http" not in text, f"{action} must NOT contain a URL"


def test_booking_link_default_and_override():
    assert "https://www.thefertilitysolution.com/free-call" in scripts.render(Action.SEND_BOOKING)
    custom = scripts.render(Action.SEND_BOOKING, {"booking_link": "https://example.com/book"})
    assert "https://example.com/book" in custom
    assert "thefertilitysolution.com/free-call" not in custom


def test_only_price_range_actions_contain_a_dollar_figure():
    # Price is never quoted EXCEPT the explicit range-reveal actions (2nd+ ask).
    import re
    allowed = {Action.PRICE_RANGE, Action.PRICE_RANGE_FIRM}
    for action in scripts.SCRIPTS:
        text = scripts.render(action)
        if action in allowed:
            assert re.search(r"\$\s*\d", text), f"{action} should contain the range"
        else:
            assert not re.search(r"\$\s*\d", text), f"unexpected price number in {action}"


def test_price_deflect_late_does_not_reask_discovery():
    # The bug fix: a price deflect after discovery must not re-ask known facts.
    text = scripts.render(Action.PRICE_DEFLECT_LATE).lower()
    assert "how long have you been trying" not in text
    assert "what you've already" not in text


def test_price_range_is_config_overridable():
    custom = scripts.render(Action.PRICE_RANGE, {"price_range": "$2,000 to $10,000"})
    assert "$2,000 to $10,000" in custom


def test_closer_phone_numbers_present():
    assert "+1 (415) 694-1799" in scripts.render(Action.POST_BOOKING_CONFIRM_NATALIA)
    assert "+1 (647) 992-6383" in scripts.render(Action.POST_BOOKING_CONFIRM_MONIKA)


def test_explain_role_is_not_a_medical_provider_claim():
    text = scripts.render(Action.EXPLAIN_ROLE)
    assert "not a doctor or fertility clinic" in text
    assert "Is that the kind of support you're looking for?" in text


def test_render_unknown_action_raises():
    with pytest.raises(KeyError):
        scripts.render_followup("does_not_exist")


# --- Spanish registry ---------------------------------------------------------

# Every scripted action the controller can actually reach must have a Spanish
# version. Dormant actions (POST_BOOKING_*, BOOKING_WHO_*, unused explain-role
# variants, OLD_CONVO, COLD_OUTREACH) intentionally fall back to English.
REACHABLE_ACTIONS = {
    Action.ASK_PRIORITY, Action.REENGAGE_LOW_PRIORITY,
    Action.LOW_PRIORITY_INFO_GATHERING, Action.NURTURE_CLOSE,
    Action.EXPLAIN_ROLE, Action.EXPLAIN_ROLE_CONFIRM, Action.EXPLAIN_ROLE_TFS3,
    Action.FINANCIAL_CHECK, Action.FINANCIAL_DECLINE,
    Action.PARTNER_CHECK, Action.PARTNER_ASK_JOIN, Action.PARTNER_PUSHBACK,
    Action.SEND_BOOKING, Action.BOOKING_IS_IT_SONIA, Action.BOOKING_CALL_PROCESS,
    Action.ADVICE_DEFLECT, Action.ADVICE_DEFLECT_LATE,
    Action.ADVICE_DEFLECT_PUSH, Action.ADVICE_DEFLECT_PUSH_LATE,
    Action.PRICE_DEFLECT, Action.PRICE_DEFLECT_LATE,
    Action.PRICE_RANGE, Action.PRICE_RANGE_FIRM,
    Action.PHONE_NUMBER_DEFLECT, Action.MASTERCLASS_SEND, Action.SOCIAL_PROOF,
    Action.PAYING_TWICE, Action.IVF_ONLY_OFFER, Action.TROUBLE_BOOKING,
    Action.NO_MONEY,
    Action.ASK_BOTH_TUBES, Action.ASK_MENOPAUSE_REASON, Action.ASK_MENOPAUSE_AGE,
    Action.OOS_BOTH_TUBES, Action.OOS_MENOPAUSE, Action.OOS_AGE_OVER_46,
    Action.OOS_DEAF,
}


def test_scripts_es_covers_reachable_set():
    missing = REACHABLE_ACTIONS - set(scripts.SCRIPTS_ES)
    assert not missing, f"reachable actions without a Spanish script: {missing}"


def test_scripts_es_placeholder_parity():
    import re
    # Same placeholders as the English template, modulo the documented
    # price_range -> price_range_es swap (the EN default embeds English "to").
    for action, es in scripts.SCRIPTS_ES.items():
        en_ph = set(re.findall(r"{(\w+)}", scripts.SCRIPTS[action]))
        es_ph = set(re.findall(r"{(\w+)}", es))
        en_ph = {"price_range_es" if p == "price_range" else p for p in en_ph}
        assert es_ph == en_ph, f"placeholder mismatch in ES {action}: {es_ph} != {en_ph}"


def test_render_es_falls_back_to_english_for_dormant_actions():
    assert Action.OLD_CONVO not in scripts.SCRIPTS_ES
    assert scripts.render(Action.OLD_CONVO, None, "es") == scripts.render(Action.OLD_CONVO)


def test_every_es_script_renders_clean():
    for action in scripts.SCRIPTS_ES:
        text = scripts.render(action, None, "es")
        assert text.strip(), f"ES {action} rendered empty"
        assert "{" not in text and "}" not in text, f"ES {action} has an unfilled placeholder"
        assert "—" not in text, f"em-dash in ES {action}"


def test_es_price_range_uses_spanish_connector():
    text = scripts.render(Action.PRICE_RANGE, None, "es")
    assert "$1,500 a $14,000" in text
    custom = scripts.render(Action.PRICE_RANGE, {"price_range_es": "$2,000 a $10,000"}, "es")
    assert "$2,000 a $10,000" in custom


def test_es_explain_role_contains_disclaimer_phrase():
    # Iteration 3 pins this exact phrase as the Spanish disclaimer key.
    assert "no soy doctora" in scripts.render(Action.EXPLAIN_ROLE, None, "es")


def test_es_banks_key_parity():
    assert set(scripts.EMPATHY_VARIANTS_ES) == set(scripts.EMPATHY_VARIANTS)
    assert set(scripts.DISCOVERY_QUESTIONS_ES) == set(scripts.DISCOVERY_QUESTIONS)
    assert len(scripts.AFFIRMATIONS_ES) == len(scripts.AFFIRMATIONS)


def test_no_banned_phrases_in_any_approved_content():
    # The validator's Sonia-v1.1 backstop must never reject approved content
    # (the fallback path re-validates scripts, so a hit here would silence a turn).
    from app.services.brain.validator import _banned_phrase

    for action in scripts.SCRIPTS:
        assert _banned_phrase(scripts.render(action)) is None, action
    for action in scripts.SCRIPTS_ES:
        assert _banned_phrase(scripts.render(action, None, "es")) is None, f"ES {action}"
    for bank in (scripts.EMPATHY_VARIANTS, scripts.EMPATHY_VARIANTS_ES,
                 scripts.DISCOVERY_QUESTIONS, scripts.DISCOVERY_QUESTIONS_ES):
        for variants in bank.values():
            texts = variants if isinstance(variants, (list, tuple)) else [variants]
            for t in texts:
                assert _banned_phrase(t) is None, t
    for t in list(scripts.AFFIRMATIONS) + list(scripts.AFFIRMATIONS_ES):
        assert _banned_phrase(t) is None, t
    for name in scripts.FOLLOWUPS:
        assert _banned_phrase(scripts.render_followup(name)) is None, name
