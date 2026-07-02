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
