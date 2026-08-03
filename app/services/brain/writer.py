"""Writer - LLM call #2. The only surface that produces user-facing words.

Replaces `voice.py`, which paraphrased a finished script into one bubble of at
most 400 characters with at most one question. That contract is why the bot read
as a form: the same discovery sentence came out identically every time because
`reference_text` WAS that sentence.

Here the contract is per-mode. A CELEBRATE turn may not ask a question at all; a
QUALIFY turn must ask exactly one. The substance comes from retrieved knowledge
rather than from a script, and a link is physically absent from the prompt unless
the mode permits it - so the model cannot send one early even if it wants to.

The instructions are not written here. `behavior/` compiles Sonia's Operating
Manual into a persistent core plus one contract per mode, and `generate` loads
core + the routed mode as the system message. Two consequences worth keeping:
the prompt has exactly one source, so nothing can drift the way the hand-written
persona here did (it claimed 15 years while the manual says 16); and the system
message is byte-identical across every turn in a mode, which is what makes
provider prompt caching pay for the larger prompt.

Everything conversation-specific goes in the user message. Never move any of it
into the system block.
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.services.brain import behavior, playbooks, scripts
from app.services.brain.constants import ResponseMode
from app.services.brain.knowledge import KnowledgeEntry
from app.services.brain.llm import model_for, usage_of, with_retry
from app.services.few_shots import load_few_shot_scenarios, select_few_shots

logger = logging.getLogger(__name__)

FEW_SHOTS_DIR = "few_shots"

# How many questions a reply of this mode may contain.
FORBIDDEN, OPTIONAL, REQUIRED, AT_MOST_ONE = "forbidden", "optional", "required", "at_most_one"


@dataclass(frozen=True)
class ModeSpec:
    """The mechanical limits of a mode. What the reply is FOR is prose, and lives
    in `behavior/modes/<MODE>.md` - one source, so the two cannot drift apart."""
    question_policy: str
    bubbles: tuple           # (min, max)
    max_chars: int           # per reply, across all bubbles
    few_shots: bool = True   # mode-scoped: a celebration must not learn to qualify
    url_names: tuple = ()    # placeholder names whose links are allowed this turn
    require_url: bool = False


# Sonia: "Sometimes the best response is simply to congratulate someone,
# acknowledge what they are going through, answer the question directly or share
# the next step. Forcing a question into every response often makes the
# conversation feel transactional."
MODE_SPECS: dict[ResponseMode, ModeSpec] = {
    ResponseMode.CELEBRATE: ModeSpec(
        question_policy=FORBIDDEN, bubbles=(1, 2), max_chars=320, few_shots=False,
    ),
    ResponseMode.ACKNOWLEDGE: ModeSpec(
        question_policy=FORBIDDEN, bubbles=(1, 2), max_chars=420,
    ),
    ResponseMode.ANSWER: ModeSpec(
        question_policy=OPTIONAL, bubbles=(1, 3), max_chars=700,
    ),
    ResponseMode.EDUCATE: ModeSpec(
        question_policy=OPTIONAL, bubbles=(1, 3), max_chars=700,
    ),
    ResponseMode.RESOURCE: ModeSpec(
        question_policy=FORBIDDEN, bubbles=(1, 2), max_chars=420, few_shots=False,
        url_names=("register_link",), require_url=True,
    ),
    ResponseMode.QUALIFY: ModeSpec(
        question_policy=REQUIRED, bubbles=(1, 3), max_chars=600,
    ),
    ResponseMode.BOOK: ModeSpec(
        # No few-shots: nearly every transcript ends with the link, which is the
        # in-context prior that made Gen 2 send it far too freely.
        question_policy=AT_MOST_ONE, bubbles=(1, 2), max_chars=700, few_shots=False,
        url_names=("booking_link",), require_url=True,
    ),
    ResponseMode.HONEST_DECLINE: ModeSpec(
        question_policy=FORBIDDEN, bubbles=(1, 3), max_chars=700, few_shots=False,
    ),
}


# The pacing discipline from prompt_builder._CONVERSATION_FLOW, which was written
# in Gen 2, never included in the assembled prompt, and is a plausible reason the
# bot offered the call far too early. Only the matching stance is injected.
_STANCE = {
    "early_trust": (
        "Early in this conversation. Your only job is that she feels heard. "
        "Reflect what she shared and invite her to say more. No reframes, no "
        "education, no solutions yet."
    ),
    "synthesize": (
        "You have several things from her now. Put them together into one picture "
        "she probably has not heard before, in a sentence or two, tied to exactly "
        "what she said."
    ),
    "reframe_invite": (
        "Trust is established. You can offer a reframe that shifts how she sees "
        "her situation, staying grounded in her specific story. Never speak in "
        "generalities."
    ),
}


class Draft(BaseModel):
    """One reply, already split the way Sonia actually sends messages.

    Explicit bubbles replace `message_splitter.split_reply`, which guessed by
    splitting on blank lines and merging adjacent ones 40% of the time at random.
    """
    bubbles: list[str]
    # One bit, not a float: gpt-4o-mini's confidence numbers carry no signal.
    unsure: bool
    unsure_reason: Optional[str]


@dataclass
class WriterInput:
    mode: ResponseMode
    known_facts: dict = field(default_factory=dict)
    knowledge: list = field(default_factory=list)
    question_asked: Optional[str] = None
    still_needed: list = field(default_factory=list)
    next_question: Optional[str] = None
    # True when this topic has already been put to her once and went unanswered.
    already_asked: bool = False
    language: str = "en"
    stance: str = "early_trust"
    allow_urls: list = field(default_factory=list)
    playbook: Optional[object] = None
    ig_user_id: str = ""
    # Length ceiling for THIS reply. Sonia: "if someone writes one short
    # sentence, avoid responding with a long essay."
    max_chars: Optional[int] = None


_URL_RE = re.compile(r"https?://\S+")
_scenario_cache: Optional[dict] = None


def _scenarios() -> dict:
    global _scenario_cache
    if _scenario_cache is None:
        try:
            _scenario_cache = load_few_shot_scenarios(FEW_SHOTS_DIR)
        except OSError:
            logger.warning("Few-shot directory %s unavailable", FEW_SHOTS_DIR)
            _scenario_cache = {}
    return _scenario_cache


def truncate_at_link(messages: list[dict]) -> list[dict]:
    """Cut an exemplar before the first Sonia turn containing a URL.

    Nearly every transcript in `few_shots/` ends with Sonia pasting the booking
    link. Gen 2 sent all 17 on every request, giving the model seventeen
    demonstrations that conversations end by sending the link - a direct cause of
    the calendar flooding. Keeping the tone while dropping that ending is the
    whole trick, and it is done here rather than by editing her transcripts.
    """
    out = []
    for msg in messages:
        if msg.get("role") == "assistant" and _URL_RE.search(msg.get("content", "")):
            break
        out.append(msg)
    # Never end on a user turn with no reply to demonstrate.
    while out and out[-1].get("role") == "user":
        out.pop()
    return out


def few_shot_messages(
    spec: ModeSpec,
    conversation_text: str,
    *,
    allow_urls: list,
    playbook=None,
    ig_user_id: str = "",
) -> list[dict]:
    """Exemplars for this turn.

    A retrieved playbook wins outright. Its examples were written for this exact
    situation, so they are safe even for the modes that deliberately refuse the
    generic transcripts: `few_shots/` contains nothing but qualification
    conversations ending in a booking link, which is the worst possible thing to
    show the model before it congratulates someone on a pregnancy.
    """
    if playbook is not None and playbook.examples:
        messages = playbooks.as_messages(playbooks.rotate_examples(playbook, ig_user_id))
        if messages:
            return messages if allow_urls else truncate_at_link(messages)
    if not spec.few_shots:
        return []
    selected = select_few_shots(_scenarios(), conversation_text)
    if allow_urls:
        return selected
    return truncate_at_link(selected)


def energy_max_chars(spec: ModeSpec, lead_texts: list[str]) -> int:
    """Cap this reply against the length of HER message.

    Sonia, manual 6.6: "If someone writes one short sentence, avoid responding
    with a long essay." The per-mode ceiling alone cannot do that - it is the
    same number whether she wrote three words or three paragraphs, which is how
    a six-word message came back with three paragraphs including "I can imagine
    how overwhelming the whole process can feel."

    A floor is still needed: a reply carrying a link, or one that has to decline
    honestly and explain why, cannot be two sentences.
    """
    written = sum(len(t or "") for t in lead_texts)
    if not written:
        return spec.max_chars
    floor = 320 if spec.url_names else 220
    return max(floor, min(spec.max_chars, written * 4))


def stance_for(history: list[dict]) -> str:
    """Pacing from how far in we are. Code decides; the model is told one line."""
    turns = sum(1 for m in history if m.get("role") == "assistant")
    if turns <= 1:
        return "early_trust"
    if turns <= 3:
        return "synthesize"
    return "reframe_invite"


def allowed_urls(spec: ModeSpec, cfg: Optional[dict]) -> list[str]:
    ph = scripts.placeholders(cfg)
    return [ph[name] for name in spec.url_names if ph.get(name)]


def _question_rule(policy: str) -> str:
    return {
        FORBIDDEN: "Do NOT ask a question. This reply must contain no question mark at all.",
        OPTIONAL: "You may end with one question if it genuinely follows, or none at all.",
        REQUIRED: "End with exactly ONE question.",
        AT_MOST_ONE: "At most one question.",
    }[policy]


def _fmt_facts(facts: dict) -> str:
    if not facts:
        return "(nothing yet)"
    return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items())


def _fmt_knowledge(entries: list[KnowledgeEntry]) -> str:
    if not entries:
        return ("(nothing retrieved - so do not make any claim about fertility or "
                "about your approach this turn)")
    return "\n".join(f"- {e.content}" for e in entries)


def build_prompt(inp: WriterInput, history: list[dict], spec: ModeSpec) -> str:
    lines = ["CONVERSATION SO FAR (most recent last):"]
    for m in history[-8:]:
        who = "Lead" if m.get("role") == "user" else "Sonia"
        lines.append(f"{who}: {m.get('content', '')}")
    body = "\n".join(lines)

    parts = [body]
    playbook_block = playbooks.prompt_block(inp.playbook)
    if playbook_block:
        parts.append("\n" + playbook_block)
    parts.append(f"\nPACING: {_STANCE[inp.stance]}")
    if inp.question_asked:
        parts.append(
            f"\nSHE ASKED THIS, ANSWER IT: \"{inp.question_asked}\"\n"
            "Answering this is the point of the reply. Do not deflect it into a "
            "question of your own."
        )
    parts.append(
        f"\nSHE HAS TOLD YOU (acknowledge what is relevant, invent nothing else): "
        f"{_fmt_facts(inp.known_facts)}"
    )
    parts.append(f"\nAPPROVED SUBSTANCE (use in your own words; claim nothing beyond it):\n"
                 f"{_fmt_knowledge(inp.knowledge)}")
    if inp.next_question and spec.question_policy == REQUIRED:
        parts.append(f"\nTHE ONE THING TO ASK: {inp.next_question}")
        if inp.already_asked:
            # The opener asks about duration and what she has tried, so a lead who
            # answers it partially sends us straight back to the same question. It
            # still needs asking - but repeating the sentence verbatim is what the
            # repeat check rejects, and going silent over it is far worse than
            # rephrasing.
            parts.append(
                "\nYou have ALREADY asked her this once and she did not answer it. "
                "Ask it again in COMPLETELY different words - different sentence "
                "shape, different opening. Acknowledge what she DID tell you first, "
                "so it does not read as though you ignored her."
            )
    if inp.still_needed:
        parts.append("\nSTILL UNKNOWN over the coming messages (do not rush these): "
                     + ", ".join(inp.still_needed))

    reqs = [_question_rule(spec.question_policy)]
    if inp.allow_urls:
        reqs.append("Include this link EXACTLY as written: " + " , ".join(inp.allow_urls))
        if spec.require_url:
            reqs.append("The link must appear in your reply.")
    else:
        reqs.append("Do NOT include any link or URL.")
    reqs.append(f"{spec.bubbles[0]} to {spec.bubbles[1]} bubbles, "
                f"{inp.max_chars or spec.max_chars} characters total at most.")
    parts.append("\nREQUIREMENTS:\n" + "\n".join(f"- {r}" for r in reqs))
    parts.append("\nWrite Sonia's next message now, in Spanish."
                 if inp.language == "es" else "\nWrite Sonia's next message now.")
    return "\n".join(parts)


def _normalize(text: str) -> str:
    """Straighten smart quotes and dashes so output matches Sonia's plain style
    and never trips the em-dash guard."""
    return (
        text.replace("’", "'").replace("‘", "'")
        .replace("“", '"').replace("”", '"')
        .replace("—", ", ").replace("–", "-")
    )


async def generate(
    openai_client: AsyncOpenAI,
    history: list[dict],
    inp: WriterInput,
    *,
    cfg: Optional[dict] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
) -> tuple[Draft, dict]:
    """Write the reply for this turn. Returns (Draft, usage)."""
    spec = MODE_SPECS[inp.mode]
    model = model or model_for("writer", cfg)

    system = behavior.system_prompt(inp.mode, inp.language)
    messages = [{"role": "system", "content": system}]

    convo_text = " ".join(m.get("content", "") for m in history if m.get("role") == "user")
    messages += few_shot_messages(
        spec, convo_text, allow_urls=inp.allow_urls,
        playbook=inp.playbook, ig_user_id=inp.ig_user_id,
    )
    messages.append({"role": "user", "content": build_prompt(inp, history, spec)})

    async def _call():
        return await openai_client.chat.completions.parse(
            model=model, messages=messages, response_format=Draft,
            temperature=temperature, max_tokens=500,
        )

    completion = await with_retry(_call, what="writer")
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Writer returned no parsed output")

    parsed.bubbles = [_normalize(b.strip()) for b in parsed.bubbles if b and b.strip()]
    return parsed, usage_of(completion, model, "writer")
