"""The conversation library: loading, and choosing which conversations go into a turn.

Each file in `few_shots/` is one scenario holding one or two COMPLETE conversations, first message
to final outcome. Fragments teach wording; whole arcs teach pacing, when to stop asking, and how a
conversation resolves, including the arcs that correctly end without a booking link.

Selection is driven by the intent and tags the READ call returned, not by matching patterns against
the prospect's prose. The old regex table misfired often (`ivf_failed` firing for a woman preparing
for her first cycle, `partner_hesitation` firing on the word "afford") and it stopped at the first
hit, so the most relevant example frequently lost to whichever pattern happened to be earlier in
the dict.
"""
import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

FEW_SHOTS_DIR = "few_shots"

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(
    r"^(?P<head>WHY THIS WORKS|CONVERSATION\b.*|DO NOT WRITE THIS)\s*$",
    re.MULTILINE,
)
_BOOKING_PLACEHOLDER = "{{booking_link}}"


@dataclass
class Playbook:
    name: str
    intent: str = ""
    tags: list[str] = field(default_factory=list)
    situation: str = ""
    ends_in: str = ""
    priority: str = "normal"          # "high" wins a slot whenever it matches at all
    why: str = ""
    conversations: list[str] = field(default_factory=list)
    counter_example: str = ""
    raw: str = ""

    @property
    def books(self) -> bool:
        return any(_BOOKING_PLACEHOLDER in c for c in self.conversations)

    def render(self, *, allow_booking: bool) -> str:
        """The example as it appears in the WRITE prompt.

        When this turn may not invite a booking, arcs that end in the link are dropped rather than
        stripped: a conversation with its ending removed teaches the wrong shape. Two-arc files
        degrade to their non-booking arc, which is why the high-traffic scenarios carry both.
        """
        arcs = self.conversations
        if not allow_booking:
            arcs = [c for c in arcs if _BOOKING_PLACEHOLDER not in c]
        if not arcs:
            return ""

        parts = [f"### EXAMPLE: {self.name}"]
        if self.situation:
            parts.append(f"Situation: {self.situation}")
        if self.why:
            parts.append(self.why)
        parts.extend(arcs)
        if self.counter_example:
            parts.append(self.counter_example)
        return "\n\n".join(p.strip() for p in parts if p.strip())


def _parse_front_matter(text: str) -> tuple[dict, str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def parse_playbook(text: str, name: str) -> Playbook:
    meta, body = _parse_front_matter(text)

    why = ""
    counter = ""
    conversations: list[str] = []

    matches = list(_SECTION_RE.finditer(body))
    for i, match in enumerate(matches):
        head = match.group("head").strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section = body[start:end].strip()
        if head == "WHY THIS WORKS":
            why = section
        elif head == "DO NOT WRITE THIS":
            counter = section
        else:
            conversations.append(section)

    return Playbook(
        name=name,
        intent=meta.get("intent", ""),
        tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        situation=meta.get("situation", ""),
        ends_in=meta.get("ends_in", ""),
        priority=meta.get("priority", "normal"),
        why=why,
        conversations=conversations,
        counter_example=counter,
        raw=text,
    )


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


def score_playbook(pb: Playbook, intent: str, tags: set[str], language: str) -> int:
    """Tags decide, intent breaks ties.

    Intent is coarse, a dozen files answer to `fertility_question`, so scoring it heavily fills
    the prompt with conversations that merely belong to the same category as hers. A shared tag is
    what actually means "this is her situation", so tags carry the weight and intent alone is not
    enough to earn a slot.
    """
    # Spanish variants only exist for Spanish conversations, and are preferred within them.
    is_spanish = "spanish" in pb.tags
    if is_spanish != (language == "es"):
        # An English conversation never sees a Spanish file. A Spanish one still falls back to the
        # English library when no Spanish version of her situation exists.
        if is_spanish:
            return 0

    overlap = len(tags & set(pb.tags))
    score = overlap * 6
    if pb.intent and pb.intent == intent:
        score += 2
    if is_spanish and overlap:
        score += 5
    if pb.priority == "high" and overlap:
        score += 8
    return score


# Below this, a file only matched on intent, which is not a reason to show a whole conversation.
_RELEVANT = 6


def select_playbooks(
    playbooks: dict[str, Playbook],
    *,
    intent: str,
    tags: list[str] | None = None,
    language: str = "en",
    allow_booking: bool = True,
    limit: int = 3,
) -> list[Playbook]:
    """Return the conversations most worth showing the writer this turn.

    Full arcs are long, so fewer and sharper beats more and vaguer, two relevant conversations
    teach more than two relevant plus one that merely shares a category. Anything that renders
    empty under the current gating (a booking-only file on a turn that may not book) is discarded
    here rather than silently occupying a slot.
    """
    tag_set = set(tags or [])
    scored = []
    for pb in playbooks.values():
        score = score_playbook(pb, intent, tag_set, language)
        if score <= 0 or not pb.render(allow_booking=allow_booking):
            continue
        scored.append((score, pb.name, pb))
    scored.sort(key=lambda row: (-row[0], row[1]))

    chosen = [pb for score, _, pb in scored[:limit] if score >= _RELEVANT]
    if not chosen and scored:
        # She said nothing that maps to a tag. A vague opener, say. One example of the right kind
        # of conversation is better than three of roughly the right category.
        chosen = [scored[0][2]]

    logger.debug(
        "select_playbooks intent=%s tags=%s -> %s", intent, sorted(tag_set),
        [pb.name for pb in chosen],
    )
    return chosen


def render_examples(
    playbooks: list[Playbook],
    *,
    allow_booking: bool,
    values: dict | None = None,
) -> str:
    """Assemble the chosen conversations for the prompt, with their placeholders resolved.

    The conversations hold no facts of their own, `{{booking_link}}`, `{{price_range}}` and the
    rest are filled from config here, at the same moment and from the same source as the knowledge
    base. Without this the writer would be shown literal braces and would cheerfully send them.
    """
    from app.services.prompts import fill_placeholders

    rendered = [pb.render(allow_booking=allow_booking) for pb in playbooks]
    body = "\n\n\n".join(r for r in rendered if r)
    if not body:
        return ""
    body = fill_placeholders(body, values or {})
    return (
        "# HOW THESE CONVERSATIONS GO\n\n"
        "Complete conversations of mine, start to finish. Learn the judgment and the pacing from "
        "them. Never copy a sentence out of one. Notice where they end: some in a call, some in "
        "an honest no, some in nothing more than a good answer.\n\n"
        f"{body}"
    )
