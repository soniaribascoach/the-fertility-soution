"""Drive scripted conversations through the real brain and write each one up as markdown.

This is the cheap equivalent of sitting in /admin/chat and typing: it calls `run_turn` directly,
the same function the worker and the admin sandbox call, so nothing here can drift away from what
a lead actually gets.

The config is the seed from the brain-v2 migration rather than whatever is in the local database,
because the local database still holds the old v14 keys and an empty knowledge base would make
every reply look broken for the wrong reason.

    python manual_testing/probe.py              # every scenario
    python manual_testing/probe.py age_51 tubes # named scenarios only
"""
import asyncio
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI  # noqa: E402

from app.services.brain import run_turn  # noqa: E402
from config import settings  # noqa: E402
from manual_testing.scenarios import SCENARIOS  # noqa: E402

ALL_SCENARIOS = SCENARIOS

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic", "versions", "r8s9t0u1v2w3_brain_v2_knowledge_base.py",
)


def load_config() -> dict:
    """The knowledge base exactly as the migration seeds it into `app_config`."""
    spec = importlib.util.spec_from_file_location("_kb_seed", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module._SEED)


def _fmt_read(read: dict) -> list[str]:
    out = []
    out.append(f"- intent: `{read.get('intent')}`  tags: `{', '.join(read.get('tags') or []) or '-'}`"
               f"  language: `{read.get('language')}`")
    if read.get("explicit_question"):
        out.append(f"- explicit_question: {read['explicit_question']!r}")
    if read.get("emotional_state"):
        out.append(f"- emotional_state: {read['emotional_state']!r}")
    slots = {k: v for k, v in (read.get("slots") or {}).items() if v not in (None, "", [])}
    flags = {k: v for k, v in (read.get("flags") or {}).items() if v}
    if slots:
        out.append(f"- slots: `{json.dumps(slots, ensure_ascii=False)}`")
    out.append(f"- flags: `{json.dumps(flags, ensure_ascii=False) if flags else '{}'}`")
    return out


async def run_scenario(client: AsyncOpenAI, cfg: dict, scenario: dict) -> dict:
    """Play the script.

    A scripted message may be a list, which models the debounce: several messages typed in a row
    that the worker batches into one turn. `start_state` seeds the dossier for scenarios that only
    make sense partway through a conversation. `continue_after_pause` keeps playing past a pause,
    which the worker would not do, and is only for probing what the next turn *would* have said.
    """
    history: list[dict] = []
    lead_state = scenario.get("start_state")
    turns = []
    ended = None

    for message in scenario["messages"]:
        texts = message if isinstance(message, list) else [message]
        history += [{"role": "user", "content": t} for t in texts]
        result = await run_turn(
            client, history, cfg, lead_state,
            ig_user_id=f"probe_{scenario['id']}", new_texts=texts,
        )
        lead_state = result.lead_state
        if result.reply_text:
            history.append({"role": "assistant", "content": result.reply_text})

        turns.append({
            "lead": "\n".join(texts) if len(texts) > 1 else texts[0],
            "batched": len(texts) > 1,
            "reply": result.reply_text,
            "action": result.action,
            "pause": result.pause,
            "pause_reason": result.pause_reason,
            "qualified": result.qualified,
            "trace": result.trace,
            "cost": (result.usage or {}).get("token_cost", 0.0),
        })

        if result.pause and not scenario.get("continue_after_pause"):
            # The worker stops the AI here, so anything the script had queued after this point
            # would never have been answered in production either.
            ended = f"AI paused after turn {len(turns)}: `{result.pause_reason}`"
            break

    return {"scenario": scenario, "turns": turns, "ended": ended, "final_state": lead_state}


def write_markdown(run: dict) -> str:
    scenario = run["scenario"]
    total = round(sum(t["cost"] for t in run["turns"]), 6)

    lines = [
        f"# {scenario['id']}: {scenario['title']}",
        "",
        f"**What the manual requires:** {scenario['expected']}",
        "",
        f"**Manual references:** {scenario['refs']}",
        "",
        f"_Run {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}, "
        f"{len(run['turns'])} turns, ${total}_",
        "",
        "---",
        "",
    ]

    for i, turn in enumerate(run["turns"], 1):
        gate = (turn["trace"] or {}).get("gate") or {}
        read = (turn["trace"] or {}).get("read") or {}
        books = (turn["trace"] or {}).get("playbooks") or []

        lines.append(f"### Turn {i}")
        lines.append("")
        lines.append(f"**Lead:** {turn['lead']}")
        lines.append("")
        if turn["reply"]:
            lines.append("**Sonia:**")
            lines.append("")
            for para in [p for p in turn["reply"].split("\n") if p.strip()]:
                lines.append(f"> {para.strip()}")
                lines.append(">")
            lines.append("")
        else:
            lines.append("**Sonia:** _(no reply sent)_")
            lines.append("")
        lines.append("<details><summary>trace</summary>")
        lines.append("")
        lines += _fmt_read(read)
        lines.append(
            f"- gate: allow_booking=`{gate.get('allow_booking')}` "
            f"escalate=`{gate.get('escalate')}` notes=`{'; '.join(gate.get('notes') or [])}`"
        )
        lines.append(f"- playbooks: `{', '.join(books) or '-'}`")
        lines.append(f"- action: `{turn['action']}`  pause: `{turn['pause']}`"
                     f"  reason: `{turn['pause_reason']}`")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if run["ended"]:
        lines += [f"**Conversation ended.** {run['ended']}", ""]
    else:
        lines += ["**Conversation ran to the end of the script; the AI never paused.**", ""]

    lines += ["---", "", "## Verdict", "", "_(filled in during review)_", ""]
    return "\n".join(lines)


async def main() -> None:
    wanted = sys.argv[1:]
    scenarios = [s for s in ALL_SCENARIOS if not wanted or s["id"] in wanted]
    if not scenarios:
        print(f"no scenario matched {wanted}. known: {[s['id'] for s in ALL_SCENARIOS]}")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    cfg = load_config()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    semaphore = asyncio.Semaphore(4)

    async def guarded(scenario):
        async with semaphore:
            try:
                return await run_scenario(client, cfg, scenario)
            except Exception as exc:  # a broken scenario must not take the batch down
                return {"scenario": scenario, "turns": [], "ended": f"HARNESS ERROR: {exc!r}",
                        "final_state": None}

    runs = await asyncio.gather(*(guarded(s) for s in scenarios))

    grand_total = 0.0
    for run in runs:
        path = os.path.join(OUT_DIR, f"{run['scenario']['id']}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(write_markdown(run))
        cost = sum(t["cost"] for t in run["turns"])
        grand_total += cost
        print(f"{run['scenario']['id']:<28} {len(run['turns'])} turns  ${cost:.4f}  "
              f"{run['ended'] or 'ran to end'}")

    # Merge rather than overwrite, so re-running one scenario does not discard the rest of the
    # batch it was extracted from.
    raw_path = os.path.join(OUT_DIR, "_raw.json")
    merged = {}
    if os.path.exists(raw_path):
        with open(raw_path, encoding="utf-8") as fh:
            merged = {r["scenario"]["id"]: r for r in json.load(fh)}
    merged.update({r["scenario"]["id"]: r for r in runs})
    with open(raw_path, "w", encoding="utf-8") as fh:
        json.dump([merged[k] for k in sorted(merged)], fh, indent=1, ensure_ascii=False, default=str)
    print(f"\ntotal ${grand_total:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
