"""Stamp the verdicts from `verdicts.py` into the transcripts in `runs/`.

Separate from `probe.py` so the review can be rewritten without spending another API call, and so
the transcript on disk is never edited by hand.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manual_testing.verdicts import VERDICTS  # noqa: E402

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
_VERDICT_RE = re.compile(r"## Verdict\n.*\Z", re.DOTALL)


def render(verdict: dict) -> str:
    lines = ["## Verdict", "", f"**{verdict['status']}**"]
    if verdict["findings"]:
        lines[-1] += "  ·  findings: " + ", ".join(verdict["findings"])
    lines.append("")
    lines += [f"- {note}" for note in verdict["notes"]]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    missing = []
    for name in sorted(os.listdir(RUNS_DIR)):
        if not name.endswith(".md"):
            continue
        scenario_id = name[:-3]
        verdict = VERDICTS.get(scenario_id)
        if not verdict:
            missing.append(scenario_id)
            continue
        path = os.path.join(RUNS_DIR, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if not _VERDICT_RE.search(text):
            print(f"{scenario_id}: no verdict section to replace, skipped")
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_VERDICT_RE.sub(render(verdict), text))
        print(f"{scenario_id}: {verdict['status']}")

    if missing:
        print(f"\nno verdict written for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
