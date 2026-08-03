"""The same fixtures as `test_scenarios_routing.py`, replayed against the real
model through the whole pipeline - classify, route, retrieve, write, check.

The routing suite proves the decision; this one proves the message she would
actually receive. `classify:` blocks are ignored here: the real classifier runs,
which is the point.

    pytest -m live tests/brain/test_scenarios_live.py
"""
import pytest

from app.services.brain.knowledge import parse_pattern_responses
from app.services.brain.knowledge_seed import SEED
from app.services.brain.playbook_seed import SEED as PLAYBOOKS
from app.services.brain.turn import run_turn_v2
from scenario_loader import build_state, check_text, load_scenarios

pytestmark = pytest.mark.live

CFG = {
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "masterclass_register_link": "https://www.thefertilitysolution.com/masterclass",
    "phase1_cta_keywords": "AMH\nBABY",
    "phase1_opening_message": "I'm so glad you reached out.",
    "medical_blocklist": "",
    "human_takeover_triggers": "",
}

# The client's own reframes, as they exist in app_config today.
_PATTERNS = (
    "Low AMH: Low AMH does not mean no baby. What matters is quality, not quantity, "
    "one good egg is enough. There's a lot that hasn't been explored yet.\n"
    "Failed IVF: A failed cycle doesn't mean your body failed. It means the environment "
    "wasn't fully prepared and supported.\n"
    "PCOS: With PCOS, the goal is helping the body feel safe enough to regulate, not just "
    "triggering ovulation.\n"
)
KNOWLEDGE = SEED + parse_pattern_responses(_PATTERNS)


def _params():
    params = []
    for scenario in load_scenarios():
        marks = []
        reason = scenario.xfails("live")
        if reason:
            # Not strict: a live run is non-deterministic, so an occasional pass
            # on unbuilt behaviour must not turn the suite red.
            marks.append(pytest.mark.xfail(reason=reason, strict=False))
        params.append(pytest.param(scenario, marks=marks, id=scenario.id))
    return params


@pytest.mark.parametrize("scenario", _params())
async def test_scenario_end_to_end(openai_client, scenario):
    state = build_state(scenario)
    history: list[dict] = []

    for i, t in enumerate(scenario.turns, start=1):
        where = f"{scenario.id} turn {i}"
        if t.sonia_before:
            history.append({"role": "assistant", "content": t.sonia_before})
        history.append({"role": "user", "content": t.lead})

        result = await run_turn_v2(
            openai_client, history, CFG, state,
            ig_user_id=f"scenario_{scenario.id}",
            new_texts=[t.lead],
            knowledge_entries=KNOWLEDGE, playbook_entries=PLAYBOOKS,
        )
        state = result.lead_state
        if result.reply_text:
            history.append({"role": "assistant", "content": result.reply_text})

        e = t.expect
        action = result.action or ""
        assert not action.endswith("_ABORTED"), (
            f"{where}: turn was suppressed ({result.violations}); the draft it "
            f"refused to send was:\n  {result.trace.get('suppressed_reply')!r}"
        )

        if e.mode:
            assert action in e.mode, (
                f"{where}: acted {action}, expected one of {e.mode}\n"
                f"  reply: {result.reply_text!r}\n  why this matters: {scenario.why}"
            )
        for banned in e.not_mode:
            assert action != banned, (
                f"{where}: acted {banned}, which is exactly the failure reported\n"
                f"  reply: {result.reply_text!r}\n  why this matters: {scenario.why}"
            )
        if e.silent is not None:
            assert (result.reply_text is None) == e.silent, (
                f"{where}: reply_text={result.reply_text!r}, expected silent={e.silent}"
            )
        if e.pause is not None:
            assert result.pause == e.pause, f"{where}: pause={result.pause}"

        problems = check_text(result.reply_text, e)
        assert not problems, (
            f"{where}:\n  " + "\n  ".join(problems)
            + f"\n  why this matters: {scenario.why}"
        )
