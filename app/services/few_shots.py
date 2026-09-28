"""The conversation library: every file in `few_shots/`, sent to the writer on every turn.

Each file is one complete conversation, first message to final outcome, in Sonia's voice. There is
no selection. The library is small enough to show whole, and choosing between files by tag was the
source of more wrong examples than it prevented.

What still varies per turn is which links may appear. A conversation that reaches a booking, the
masterclass or the post-booking replay shows that link only when the gate has opened the matching
knowledge block this turn. Otherwise the link is replaced with a marker, so the writer sees how the
conversation goes without being handed a URL it may not send.
"""
import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

FEW_SHOTS_DIR = "few_shots"

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

# Link placeholder -> the knowledge block that must be open this turn for it to be shown.
_LINK_BLOCKS = {
    "{{booking_link}}": "booking",
    "{{masterclass_link}}": "free_resource",
    "{{replay_link}}": "post_booking",
}
_WITHHELD = "[link not available this turn]"


@dataclass
class Playbook:
    name: str
    text: str          # the conversation, front matter removed
    raw: str = ""

    def render(self, *, allowed_blocks: set[str]) -> str:
        body = self.text
        for placeholder, block in _LINK_BLOCKS.items():
            if block not in allowed_blocks:
                body = body.replace(placeholder, _WITHHELD)
        return f"### EXAMPLE: {self.name}\n\n{body.strip()}"


def parse_playbook(text: str, name: str) -> Playbook:
    return Playbook(name=name, text=_FRONT_MATTER_RE.sub("", text, count=1), raw=text)


def load_few_shot_scenarios(directory: str = FEW_SHOTS_DIR) -> dict[str, Playbook]:
    """Load every conversation file. Name kept for the admin editor, which refreshes this cache."""
    playbooks: dict[str, Playbook] = {}
    for filename in sorted(os.listdir(directory)):
        path = os.path.join(directory, filename)
        if filename.startswith(".") or not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            playbooks[filename] = parse_playbook(fh.read(), name=filename)
    logger.info("Loaded %d conversation playbooks", len(playbooks))
    return playbooks


def get_few_shot_scenarios(app_state, directory: str = FEW_SHOTS_DIR) -> dict[str, Playbook]:
    cached = getattr(app_state, "few_shot_scenarios", None)
    if cached is None:
        cached = load_few_shot_scenarios(directory)
        app_state.few_shot_scenarios = cached
    return cached


def render_examples(
    playbooks: list[Playbook],
    *,
    allowed_blocks: set[str],
    values: dict | None = None,
) -> str:
    """Assemble the conversations for the prompt, with their placeholders resolved.

    The conversations hold no facts of their own, `{{booking_link}}`, `{{price_range}}` and the
    rest are filled from config here, at the same moment and from the same source as the knowledge
    base. Without this the writer would be shown literal braces and would cheerfully send them.
    """
    from app.services.prompts import fill_placeholders

    body = "\n\n\n".join(pb.render(allowed_blocks=allowed_blocks) for pb in playbooks)
    if not body:
        return ""
    body = fill_placeholders(body, values or {})
    return (
        "# HOW THESE CONVERSATIONS GO\n\n"
        "Complete conversations of mine, start to finish. Learn the judgment and the pacing from "
        "them. Never copy a sentence out of one. Notice where they end: some in a call, some in "
        "an honest no, some in nothing more than a good answer.\n\n"
        f"Where a conversation shows {_WITHHELD}, she had reached a point where I sent a link. "
        "You may not send that link on this turn. Only send a link that appears in the knowledge "
        "above.\n\n"
        f"{body}"
    )
