"""Knowledge retrieval - approved substance the writer is allowed to use.

The brain used to hold scripts about its own PROCESS and nothing about fertility
or Sonia's positioning. That is why it deflected real questions and described
itself in language that would fit any wellness coach - both complaints in her
2026-07-29 review.

An entry here is something Sonia has approved her bot saying. The writer may
phrase it in its own words; it may not introduce a fertility or positioning claim
that is not in the retrieved set. So the answer to "can anything help in the 6
weeks before IVF?" becomes a data question, editable by her in the admin panel,
rather than a prompt-instruction question.

The retrieval itself is pure and testable: `select` takes plain entries, so no
test in this module needs a database.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.brain.constants import LeadIntent, ResponseMode


class Kind:
    """What a piece of knowledge is FOR. Retrieval filters on this first."""
    POSITIONING = "positioning"    # what makes her approach different
    REFRAME = "reframe"            # the insight she returns to for a situation
    ANSWER = "answer"              # a real answer to a recurring question
    OBJECTION = "objection"        # how she meets a specific concern
    PROOF = "proof"                # track record, testimonials
    BOUNDARY = "boundary"          # what she will not do, and why
    NOT_A_FIT = "not_a_fit"        # how she says "you may not need this yet"

    ALL = (POSITIONING, REFRAME, ANSWER, OBJECTION, PROOF, BOUNDARY, NOT_A_FIT)


@dataclass
class KnowledgeEntry:
    kind: str
    topic: str
    content: str
    triggers: list[str] = field(default_factory=list)
    language: str = "en"
    source: str = ""
    active: bool = True
    id: Optional[int] = None


# Which kinds are worth retrieving for each response mode. A CELEBRATE turn needs
# no positioning; an EDUCATE turn needs exactly that.
KINDS_FOR_MODE: dict[ResponseMode, tuple] = {
    ResponseMode.ANSWER: (Kind.ANSWER, Kind.REFRAME, Kind.BOUNDARY, Kind.POSITIONING),
    ResponseMode.EDUCATE: (Kind.POSITIONING, Kind.PROOF, Kind.REFRAME),
    ResponseMode.QUALIFY: (Kind.REFRAME,),
    ResponseMode.ACKNOWLEDGE: (Kind.REFRAME,),
    ResponseMode.HONEST_DECLINE: (Kind.NOT_A_FIT,),
    ResponseMode.BOOK: (),
    ResponseMode.CELEBRATE: (),
    ResponseMode.RESOURCE: (),
    ResponseMode.HANDOFF: (),
}

# Objection intents pull their own kind first, so a financial concern and a
# skeptical partner stop getting the same generic reply.
_OBJECTION_TOPICS = {
    LeadIntent.OBJECTION_PRICE: "price",
    LeadIntent.OBJECTION_PARTNER: "partner",
    LeadIntent.OBJECTION_TRUST: "trust",
    LeadIntent.OBJECTION_FEAR_AFTER_FAILURE: "fear_after_failure",
    LeadIntent.OBJECTION_PAYING_TWICE: "paying_twice",
}


def _matches(entry: KnowledgeEntry, haystack: str) -> int:
    """How many of an entry's triggers appear in the text. 0 means no match."""
    hits = 0
    for trigger in entry.triggers:
        pattern = trigger.strip()
        if not pattern:
            continue
        try:
            if re.search(pattern, haystack, re.IGNORECASE):
                hits += 1
        except re.error:
            # A malformed trigger typed into the admin panel must not break a
            # live conversation; fall back to a plain substring test.
            if pattern.casefold() in haystack:
                hits += 1
    return hits


def select(
    entries: list[KnowledgeEntry],
    *,
    mode: ResponseMode,
    intent: LeadIntent,
    text: str,
    language: str = "en",
    limit: int = 3,
) -> list[KnowledgeEntry]:
    """The approved substance for this turn, most relevant first.

    Objection entries matching the specific objection come first and always
    survive the limit: they are the reason the four objection types stopped
    collapsing into one reply.
    """
    haystack = (text or "").casefold()
    wanted = KINDS_FOR_MODE.get(mode, ())
    pool = [e for e in entries if e.active and e.language == language]

    # 1. The exact objection, if this is one.
    pinned = []
    topic = _OBJECTION_TOPICS.get(intent)
    if topic:
        pinned = [e for e in pool if e.kind == Kind.OBJECTION and e.topic == topic]

    # 2. Everything else this mode can use, ranked by trigger hits.
    scored = []
    for entry in pool:
        if entry in pinned or entry.kind not in wanted:
            continue
        hits = _matches(entry, haystack)
        if hits:
            scored.append((hits, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    # 3. Positioning is the answer to "what makes you different", so an EDUCATE
    # turn gets it even when nothing in her message matched a trigger.
    chosen = pinned + [e for _, e in scored]
    if mode is ResponseMode.EDUCATE and not any(e.kind == Kind.POSITIONING for e in chosen):
        chosen += [e for e in pool if e.kind == Kind.POSITIONING][:1]

    return chosen[:max(limit, len(pinned))]


def parse_pattern_responses(raw: str, *, source: str = "prompt_pattern_responses") -> list:
    """Parse the admin `prompt_pattern_responses` block into reframe entries.

    Format is one per line, `Topic: the reframe`. This content has existed in
    app_config since Gen 2, in Sonia's own voice, and has been read by nothing.
    """
    entries = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        topic, content = line.split(":", 1)
        topic, content = topic.strip(), content.strip()
        if not topic or not content:
            continue
        entries.append(KnowledgeEntry(
            kind=Kind.REFRAME,
            topic=topic.casefold().replace(" ", "_"),
            content=content,
            triggers=_triggers_for_topic(topic),
            source=source,
        ))
    return entries


# Trigger vocabulary per known reframe topic. Mirrors the approach already proven
# by few_shots.SCENARIO_PATTERNS rather than introducing embeddings.
_TOPIC_TRIGGERS = {
    "low amh": [r"\bamh\b", r"anti.{0,10}mullerian", r"egg.{0,5}reserve",
                r"low.{0,10}reserve", r"egg.{0,5}quality"],
    "ivf pressure": [r"\bivf\b", r"in.{0,5}vitro", r"only.{0,10}option",
                     r"pushed.{0,10}toward", r"referral"],
    "unexplained infertility": [r"unexplained", r"normal.{0,10}results?",
                                r"nothing.{0,10}wrong", r"no.{0,10}answers?"],
    "failed ivf": [r"failed.{0,10}(ivf|cycle|round|transfer)", r"didn.?t.{0,5}work",
                   r"negative.{0,10}(test|beta)"],
    "donor egg pressure": [r"donor.{0,5}egg", r"egg.{0,5}donor"],
    "pcos": [r"\bpcos\b", r"polycystic"],
    "endometriosis": [r"endo(metriosis)?\b", r"\badeno"],
    "poi": [r"\bpoi\b", r"premature.{0,10}ovarian", r"early.{0,10}menopause"],
    "irregular cycles": [r"irregular", r"no.{0,5}period", r"cycles?.{0,15}(off|weird|all over)",
                         r"anovulat"],
    "perimenopause or age concern": [r"perimenopaus", r"too.{0,5}old", r"\bage\b",
                                     r"running.{0,10}out.{0,10}time", r"\b4[0-9]\b"],
    "recurrent miscarriage": [r"miscarr", r"pregnancy.{0,5}loss", r"chemical.{0,5}preg",
                              r"recurrent.{0,5}loss", r"lost.{0,10}bab"],
}


def _triggers_for_topic(topic: str) -> list[str]:
    """Known topics get a curated pattern list; anything new falls back to its
    own words, so an entry Sonia adds tomorrow is still retrievable."""
    known = _TOPIC_TRIGGERS.get(topic.casefold())
    if known:
        return list(known)
    words = [w for w in re.findall(r"[a-z]{4,}", topic.casefold())]
    return [rf"\b{re.escape(w)}" for w in words] or [re.escape(topic.casefold())]
