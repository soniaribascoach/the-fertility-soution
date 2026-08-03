"""Measure writer models against Sonia's own reported failures.

    ./.venv/bin/python scripts/compare_writers.py
    ./.venv/bin/python scripts/compare_writers.py gpt-4o-mini gpt-5

Runs every scenario in `tests/brain/scenarios/` once per candidate writer model
and reports, per model:

* how many scenarios routed to the right mode and produced a sendable reply
* how many turns the brain refused to send (an abort is a lead who gets silence)
* the "Specific To Her" judge score, which is Sonia's own Part 3 test
* tokens and real USD per turn, cached prefix tokens counted separately

Only `model_writer` changes between runs. The classifier and the checker stay on
the cheap model throughout, because the complaint being tested is about how the
replies READ, and that is the writer's job alone.

Cost figures come from `llm._COSTS`, which holds OpenAI's published standard
rates. Latency is wall-clock for the whole turn, so it includes the classifier.
"""
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "brain"))

from config import settings  # noqa: E402

os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

from openai import AsyncOpenAI  # noqa: E402

from app.services.brain.knowledge import parse_pattern_responses  # noqa: E402
from app.services.brain.knowledge_seed import SEED as KNOWLEDGE_SEED  # noqa: E402
from app.services.brain.playbook_seed import SEED as PLAYBOOKS  # noqa: E402
from app.services.brain.turn import run_turn_v2  # noqa: E402
from scenario_loader import build_state, check_text, load_scenarios  # noqa: E402

CFG_BASE = {
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "masterclass_register_link": "https://www.thefertilitysolution.com/masterclass",
    "phase1_cta_keywords": "AMH\nBABY",
    "phase1_opening_message": "I'm so glad you reached out.",
    "medical_blocklist": "",
    "human_takeover_triggers": "",
}
_PATTERNS = (
    "Low AMH: Low AMH does not mean no baby. What matters is quality, not quantity, "
    "one good egg is enough. There's a lot that hasn't been explored yet.\n"
    "Failed IVF: A failed cycle doesn't mean your body failed. It means the environment "
    "wasn't fully prepared and supported.\n"
)
KNOWLEDGE = KNOWLEDGE_SEED + parse_pattern_responses(_PATTERNS)

DEFAULT_MODELS = ["gpt-4o-mini", "gpt-4.1", "gpt-5"]


async def run_model(client, model: str, scenarios) -> dict:
    cfg = dict(CFG_BASE, model_writer=model)
    rows, replies = [], []

    for scenario in scenarios:
        state = build_state(scenario)
        history: list[dict] = []
        for turn in scenario.turns:
            if turn.sonia_before:
                history.append({"role": "assistant", "content": turn.sonia_before})
            history.append({"role": "user", "content": turn.lead})

            started = time.perf_counter()
            result = await run_turn_v2(
                client, history, cfg, state,
                ig_user_id=f"cmp_{model}_{scenario.id}",
                new_texts=[turn.lead],
                knowledge_entries=KNOWLEDGE, playbook_entries=PLAYBOOKS,
            )
            elapsed = time.perf_counter() - started
            state = result.lead_state
            if result.reply_text:
                history.append({"role": "assistant", "content": result.reply_text})

            action = result.action or ""
            aborted = action.endswith("_ABORTED")
            expected = turn.expect.mode
            mode_ok = (not expected) or action in expected
            text_ok = not check_text(result.reply_text, turn.expect)
            usage = result.usage or {}

            rows.append({
                "ok": bool(mode_ok and text_ok and not aborted),
                "aborted": aborted,
                "seconds": elapsed,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "cached_tokens": usage.get("cached_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "cost": usage.get("token_cost", 0.0),
                "chars": len(result.reply_text or ""),
            })
            if result.reply_text:
                replies.append((turn.lead, result.reply_text))

    return {"model": model, "rows": rows, "replies": replies}


def judge_specificity(replies) -> float:
    """Sonia's Part 3 test: could this be pasted into another conversation?"""
    import test_eval  # imported late: constructing GEval needs the API key set

    scores = []
    from deepeval.test_case import LLMTestCase
    for lead, reply in replies:
        test_eval._SPECIFIC_TO_HER.measure(
            LLMTestCase(input=lead, actual_output=reply))
        scores.append(test_eval._SPECIFIC_TO_HER.score)
    return statistics.mean(scores) if scores else 0.0


def report(results):
    print()
    print(f"{'model':<14}{'passed':>9}{'silent':>8}{'specific':>10}"
          f"{'tok/turn':>10}{'cached':>8}{'USD/turn':>11}{'USD/1k':>9}{'sec':>7}")
    print("-" * 86)
    for r in results:
        rows = r["rows"]
        n = len(rows)
        passed = sum(1 for x in rows if x["ok"])
        aborted = sum(1 for x in rows if x["aborted"])
        tok = statistics.mean(x["prompt_tokens"] + x["completion_tokens"] for x in rows)
        cached = statistics.mean(x["cached_tokens"] for x in rows)
        cost = statistics.mean(x["cost"] for x in rows)
        secs = statistics.mean(x["seconds"] for x in rows)
        print(f"{r['model']:<14}{passed:>5}/{n:<3}{aborted:>8}{r['specificity']:>10.2f}"
              f"{tok:>10.0f}{cached:>8.0f}{cost:>11.5f}{cost * 1000:>9.2f}{secs:>7.1f}")
    print()
    print("passed   = right mode, sendable reply, text assertions met")
    print("silent   = turns the brain refused to send (the lead gets nothing)")
    print("specific = mean 'Specific To Her' judge score, 0-1, higher is better")
    print("cached   = mean prefix tokens billed at the cached rate")
    print("USD/1k   = cost per 1000 lead turns, all calls in the turn included")


async def main():
    models = sys.argv[1:] or DEFAULT_MODELS
    scenarios = load_scenarios()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    results = []
    for model in models:
        print(f"running {len(scenarios)} scenarios on {model} ...", flush=True)
        # Twice: the first pass warms the prefix cache, and a cold-cache figure
        # would misrepresent steady-state cost for every model differently.
        await run_model(client, model, scenarios)
        result = await run_model(client, model, scenarios)
        result["specificity"] = judge_specificity(result["replies"])
        results.append(result)

    report(results)


if __name__ == "__main__":
    asyncio.run(main())
