"""The behavioral layer compiled from Sonia's Operating Manual v1.0.

These are cheap structural guarantees about the prompt that is paid for on every
single turn: it exists for every mode, it stays inside budget, it is stable
enough to be cached, and it does not contradict itself.
"""
import pytest

from app.services.brain import behavior
from app.services.brain.constants import ResponseMode


def test_every_mode_has_a_contract():
    """A mode without a contract must fail loudly.

    Silently falling back to a generic prompt is how QUALIFY behaviour leaks into
    CELEBRATE, which is the failure Sonia reported in the first place.
    """
    assert behavior.missing_contracts() == []


def test_unknown_mode_raises_rather_than_defaulting(tmp_path, monkeypatch):
    monkeypatch.setattr(behavior, "MODES_DIR", tmp_path)
    behavior.mode_contract.cache_clear()
    with pytest.raises(FileNotFoundError):
        behavior.mode_contract(ResponseMode.QUALIFY)
    behavior.mode_contract.cache_clear()


@pytest.mark.parametrize("mode", list(ResponseMode), ids=lambda m: m.value)
def test_prompt_stays_within_budget(mode):
    en = behavior.approx_tokens(behavior.system_prompt(mode))
    es = behavior.approx_tokens(behavior.system_prompt(mode, "es"))
    assert en <= behavior.MAX_PROMPT_TOKENS, (
        f"{mode.value} core+contract is ~{en} tokens, over "
        f"{behavior.MAX_PROMPT_TOKENS}. This is paid on every turn - trim the "
        f"core rather than raising the budget."
    )
    assert es <= behavior.MAX_PROMPT_TOKENS_ES


@pytest.mark.parametrize("mode", list(ResponseMode), ids=lambda m: m.value)
def test_prompt_is_byte_stable(mode):
    """Prefix caching only pays if the block is identical every time."""
    assert behavior.system_prompt(mode) == behavior.system_prompt(mode)
    assert behavior.system_prompt(mode, "es").startswith(behavior.system_prompt(mode))


@pytest.mark.parametrize("mode", list(ResponseMode), ids=lambda m: m.value)
def test_no_em_dashes_in_the_prompt(mode):
    """The prompt forbids em-dashes and the checks reject them in output.

    A prompt that uses sixteen of them while banning them is demonstrating the
    opposite of what it says.
    """
    prompt = behavior.system_prompt(mode, "es")
    assert "—" not in prompt and "–" not in prompt


def test_core_carries_the_non_negotiables():
    """Spot-checks against the manual's section 3, in her terms.

    Not a full transcription test - the point is that a future edit cannot
    quietly drop a rule she called non-negotiable.
    """
    core = behavior.core().casefold()
    for phrase in [
        "already given you",          # never ask twice
        "first person",               # section 17
        "not a doctor",               # positioning
        "no markdown",                # plain text
    ]:
        assert phrase in core, f"core.md no longer states: {phrase}"


def test_core_holds_no_business_facts():
    """Part 5 is the single source of truth for facts, and it is the knowledge
    table, not this file. Hardcoding them here is exactly how the running code
    ended up claiming 15 years in one place and 'over 700 families' in another."""
    core = behavior.core()
    for fact in ["16 years", "15 years", "735", "700", "$1,500", "http"]:
        assert fact not in core, (
            f"core.md contains the business fact {fact!r}; it belongs in the "
            f"knowledge table where Sonia can edit it"
        )


def test_forbidden_question_modes_say_so():
    """The mode contract and the mechanical policy must agree."""
    from app.services.brain.writer import FORBIDDEN, MODE_SPECS

    for mode, spec in MODE_SPECS.items():
        if spec.question_policy != FORBIDDEN:
            continue
        contract = behavior.mode_contract(mode).casefold()
        assert "not ask" in contract or "ask nothing" in contract, (
            f"{mode.value} forbids questions mechanically but its contract "
            f"never tells the writer that"
        )
