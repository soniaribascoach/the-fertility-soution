"""Conversation playbooks - Part 4 of Sonia's Operating Manual, as data.

    "The biggest improvements going forward will come from building the
     Conversation Playbook Library with real, edited conversations."

A playbook is one conversation pattern she regularly has: what the situation is,
what the reply is trying to achieve, how it should leave her feeling, what to
avoid, and at least three real examples that demonstrate it. One is retrieved per
turn, and its examples become that turn's few-shots.

This is what CELEBRATE, HONEST_DECLINE and BOOK have never had. They use no
few-shots today because `few_shots/` contains nothing resembling them - every
transcript there is a qualification conversation ending in a booking link, which
is precisely the wrong thing to demonstrate for a pregnancy announcement.

WHAT GOES IN THE PROMPT, AND WHAT DOES NOT
------------------------------------------
The manual's Standard Playbook Structure has eleven fields. Only the ones that
change the reply are injected: `situation`, `goal`, `emotional_outcome`,
`communication_priorities`, `mistakes_to_avoid` and `examples`.

`success_criteria`, `why_this_works`, `decision_outcome`, `conversation_state`
and `information_that_matters` are kept as columns because they are how Sonia
reasons about and reviews a playbook, but they describe the pattern rather than
instruct the reply, and every token here is paid on every turn.

Retrieval is deterministic and pure: `select` takes plain objects, so nothing in
this module needs a database to test.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.brain.constants import LeadIntent, ResponseMode, Stage

logger = logging.getLogger(__name__)

# An exemplar conversation is a list of turns. `lead` is what she wrote, `sonia`
# is the reply being demonstrated.
Example = dict


@dataclass
class Playbook:
    slug: str
    title: str
    # Retrieval keys.
    intents: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    mode: Optional[str] = None
    language: str = "en"

    # Injected into the writer prompt.
    situation: str = ""
    goal: str = ""
    emotional_outcome: str = ""
    communication_priorities: list[str] = field(default_factory=list)
    mistakes_to_avoid: list[str] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)

    # Kept for Sonia's review; never injected.
    conversation_state: str = ""
    success_criteria: str = ""
    information_that_matters: str = ""
    decision_outcome: str = ""
    why_this_works: str = ""

    source: str = ""
    active: bool = True
    id: Optional[int] = None


def _trigger_hits(playbook: Playbook, haystack: str) -> int:
    hits = 0
    for trigger in playbook.triggers:
        pattern = (trigger or "").strip()
        if not pattern:
            continue
        try:
            if re.search(pattern, haystack, re.IGNORECASE):
                hits += 1
        except re.error:
            # A malformed regex typed into the admin panel must never break a
            # live conversation.
            if pattern.casefold() in haystack:
                hits += 1
    return hits


def select(
    playbooks: list[Playbook],
    *,
    mode: ResponseMode,
    intent: LeadIntent,
    stage: Stage,
    text: str = "",
    language: str = "en",
) -> Optional[Playbook]:
    """The single best playbook for this turn, or None.

    Ranked by specificity, because a playbook naming this exact intent knows more
    about the conversation than one that merely covers the mode:

        intent match > stage match > trigger hits > mode-only fallback

    Returning None is a normal outcome, not a failure: the mode contract alone is
    a complete instruction, and a wrong playbook is worse than no playbook.
    """
    haystack = (text or "").casefold()
    pool = [p for p in playbooks if p.active and p.language == language]
    if not pool:
        return None

    scored = []
    for p in pool:
        if p.mode and p.mode != mode.value:
            continue
        intent_match = intent.value in p.intents
        # A playbook that names intents but not this one is about another
        # conversation, even if it shares the mode.
        if p.intents and not intent_match:
            continue
        stage_match = stage.value in p.stages
        if p.stages and not stage_match:
            continue
        score = (
            (100 if intent_match else 0)
            + (10 if stage_match else 0)
            + _trigger_hits(p, haystack)
        )
        scored.append((score, p.slug, p))

    if not scored:
        return None
    # Slug breaks ties so retrieval is deterministic across runs.
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2]


def rotate_examples(playbook: Playbook, ig_user_id: str = "") -> list[Example]:
    """The playbook's examples, ordered per-lead.

    Two people in the same situation must not receive near-identical replies.
    The model leans hardest on the first exemplar, so rotating which one leads is
    a cheap, deterministic source of variation - the same lead always sees the
    same order, so a conversation stays self-consistent.
    """
    examples = list(playbook.examples or [])
    if len(examples) < 2 or not ig_user_id:
        return examples
    offset = sum(ord(c) for c in ig_user_id) % len(examples)
    return examples[offset:] + examples[:offset]


def as_messages(examples: list[Example]) -> list[dict]:
    """Exemplars as chat messages, the shape the writer already expects."""
    messages: list[dict] = []
    for example in examples:
        for turn in example.get("turns", []):
            lead, sonia = turn.get("lead"), turn.get("sonia")
            if lead:
                messages.append({"role": "user", "content": lead})
            if sonia:
                messages.append({"role": "assistant", "content": sonia})
    # Never end on a lead turn: there is no reply to demonstrate.
    while messages and messages[-1]["role"] == "user":
        messages.pop()
    return messages


def prompt_block(playbook: Optional[Playbook]) -> str:
    """The instruction fragment for this turn. Empty when nothing was retrieved."""
    if playbook is None:
        return ""
    lines = [f"THIS SITUATION: {playbook.situation or playbook.title}"]
    if playbook.goal:
        lines.append(f"WHAT THIS REPLY IS FOR: {playbook.goal}")
    if playbook.emotional_outcome:
        lines.append(f"SHE SHOULD COME AWAY: {playbook.emotional_outcome}")
    if playbook.communication_priorities:
        lines.append("WHAT MATTERS MOST: " + "; ".join(playbook.communication_priorities))
    if playbook.mistakes_to_avoid:
        lines.append("DO NOT: " + "; ".join(playbook.mistakes_to_avoid))
    return "\n".join(lines)
