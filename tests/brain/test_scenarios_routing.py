"""Sonia's reported failures, proved against the router without the API.

The router is pure code, so "a grieving woman is never qualified" and "answer
her question before qualifying" are properties that can be asserted for free on
every run. The same fixtures are replayed end-to-end against the real model in
`test_scenarios_live.py`.

    pytest tests/brain/test_scenarios_routing.py
"""
import pytest

from app.services.brain import turn as turn_mod
from app.services.brain.constants import ResponseMode
from app.services.brain.router import route
from scenario_loader import (
    apply_slots,
    build_state,
    load_scenarios,
    stub_classification,
)

CFG = {
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "masterclass_register_link": "https://www.thefertilitysolution.com/masterclass",
}


def _params():
    params = []
    for scenario in load_scenarios():
        if not scenario.routable:
            continue
        marks = []
        reason = scenario.xfails("routing")
        if reason:
            marks.append(pytest.mark.xfail(reason=reason, strict=True))
        params.append(pytest.param(scenario, marks=marks, id=scenario.id))
    return params


def test_scenarios_are_loadable():
    """A malformed fixture must fail loudly here, not as a confusing collection error."""
    scenarios = load_scenarios()
    assert scenarios, "no scenario fixtures found"
    for s in scenarios:
        assert s.turns, f"{s.id} has no turns"
        assert s.why, f"{s.id} has no `why` - a red test must explain itself"


@pytest.mark.parametrize("scenario", _params())
def test_router_decision(scenario):
    state = build_state(scenario)

    for i, t in enumerate(scenario.turns, start=1):
        where = f"{scenario.id} turn {i}"
        classification = stub_classification(t.classify)
        apply_slots(state, t.set_slots, scenario.id)
        # Mirrors run_turn_v2: a rich situation ends discovery outright.
        if classification.situation_richness == "rich":
            state["flags"]["situation_rich"] = True

        r = route(state, classification, CFG)
        state = r.lead_state
        e = t.expect

        if e.mode:
            assert r.mode.value in e.mode, (
                f"{where}: routed {r.mode.value} ({r.reason}), expected one of "
                f"{e.mode}\n  why this matters: {scenario.why}"
            )
        for banned in e.not_mode:
            assert r.mode.value != banned, (
                f"{where}: routed {banned} ({r.reason}), which is exactly the "
                f"failure reported\n  why this matters: {scenario.why}"
            )
        if e.silent is not None:
            assert (r.send_message is False) == e.silent, (
                f"{where}: send_message={r.send_message}, expected silent={e.silent}"
            )
        if e.pause is not None:
            assert r.pause == e.pause, f"{where}: pause={r.pause}, expected {e.pause}"

        if e.next_question_not:
            asked = (
                turn_mod._next_question(state)
                if r.mode is ResponseMode.QUALIFY
                else None
            )
            assert asked not in e.next_question_not, (
                f"{where}: about to ask {asked!r}, which she has already answered\n"
                f"  why this matters: {scenario.why}"
            )
