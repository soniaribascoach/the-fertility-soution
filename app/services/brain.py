"""The brain: one turn in, one reply out.

Three stages. A cheap model reads the conversation and reports facts; plain Python merges those
facts into the lead's dossier and decides what the writer is allowed to be told; the same cheap
model writes the reply with the right conversations in front of it.

The safety model is what the writer is *given*, not what it produces. A turn that must not invite a
booking never has the link rendered into its prompt, so there is no link to send and nothing to
police afterwards. Nothing in this file inspects generated text.

A handover turn is the limit case of that: the writer is not called at all. She gets either nothing
or one fixed line from config, so the AI cannot answer the question it has just decided it should
not be answering.

Two things the app needs from any implementation, both unchanged:

  * a `TurnResult`, whose fields ARE the side effects the worker applies - reply, pause, tag, and
    the lead state to persist;
  * `lead_state`, an arbitrary JSON dict owned entirely by the brain.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.services import dossier
from app.services.few_shots import load_few_shot_scenarios, render_examples, select_playbooks
from app.services.prompts import build_write_prompt, config_values
from app.services.reader import read_turn

logger = logging.getLogger(__name__)

# ManyChat tag applied whenever a turn needs a human. Set in their dashboard.
HUMAN_REVIEW_TAG = 86596410

DEFAULT_MODEL = "gpt-4.1-mini"

# USD per 1M tokens, (prompt, completion). Unknown models fall back to the default's rate so a
# model swap in admin never breaks cost reporting.
_RATES = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

_playbook_cache: dict | None = None


@dataclass
class TurnResult:
    """What one turn produced, and what the worker should do about it."""
    reply_text: Optional[str] = None      # None means say nothing
    lead_state: dict = field(default_factory=dict)
    pause: bool = False                   # stop the AI; a human takes over
    pause_reason: Optional[str] = None
    add_tag: bool = False                 # flag her in ManyChat
    qualified: bool = False               # tag as qualified rather than review
    action: Optional[str] = None          # short label for the log
    usage: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)
    trace: dict = field(default_factory=dict)


def _playbooks() -> dict:
    global _playbook_cache
    if _playbook_cache is None:
        _playbook_cache = load_few_shot_scenarios()
    return _playbook_cache


def reload_playbooks() -> None:
    """Drop the cache so an edit in the admin few-shots editor takes effect immediately."""
    global _playbook_cache
    _playbook_cache = None


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_rate, completion_rate = _RATES.get(model, _RATES[DEFAULT_MODEL])
    return round(
        (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000, 6
    )


def _usage(model: str, read_usage: dict, response) -> dict:
    """Token cost for the turn. A handover turn only ever paid for the read call."""
    prompt_tokens = read_usage["prompt_tokens"] + getattr(
        getattr(response, "usage", None), "prompt_tokens", 0
    )
    completion_tokens = read_usage["completion_tokens"] + getattr(
        getattr(response, "usage", None), "completion_tokens", 0
    )
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "ai_model": model,
        "token_cost": _cost(model, prompt_tokens, completion_tokens),
    }


def _brief(gate: dossier.Gate, read: dict, openings: list[str]) -> str:
    """The per-turn instructions: what this reply has to do, and what it must not contain."""
    lines = ["# THIS TURN"]

    question = read.get("explicit_question")
    if question:
        lines.append(f"- She asked: \"{question}\". Answer it in this message, before anything else.")
    if read.get("emotional_state"):
        lines.append(f"- She reads as: {read['emotional_state']}. Match that.")

    if gate.allow_booking:
        lines.append(
            "- A consultation is available to you this turn. Offer it only if it is genuinely the "
            "most useful next step for her right now, most turns it is not."
        )
    else:
        lines.append(
            "- No consultation this turn. Do not offer a call, do not hint at one, and do not "
            "suggest she get in touch to arrange one."
        )

    # The reason a turn was gated is usually also the thing the reply must not do.
    reason_rules = {
        "lab_request": (
            "- She has put test results in front of you. Do not tell her what any number means, "
            "not even loosely, not even with a caveat, and do not say a value is low, high, "
            "borderline or optimal. Explain why reading them properly needs her whole picture, "
            "and give her something useful to do instead."
        ),
        "out_of_scope_request": (
            "- She is asking for something you do not provide. Say so plainly in one sentence and "
            "point her to who does provide it."
        ),
        "tubal_status_unclear": (
            "- Ask whether both tubes are affected or only one. Do not answer the rest of her "
            "question until you know."
        ),
        "recent_loss": (
            "- She is grieving a recent loss. Ask her nothing about her history, assess nothing, "
            "and offer nothing. Be with her. This holds for the practical question that comes "
            "next as well: what testing is usual, whether to push for answers, when to try "
            "again. Tell her nothing about what is normally done, say the question is worth "
            "asking and is one for the person who cared for her, and stay with the fact that it "
            "is days old."
        ),
        "demands_guarantee": (
            "- She wants a guarantee. Say clearly that no honest coach can give one, and do not "
            "supply a softened version of one in its place."
        ),
    }
    if gate.block_reason in reason_rules:
        lines.append(reason_rules[gate.block_reason])

    if openings:
        lines.append("")
        lines.append("Openings already used with other people recently. Do not start like any of them:")
        lines += [f"  · {o}" for o in openings[:12]]

    return "\n".join(lines)


async def run_turn(
    openai_client: AsyncOpenAI,
    history: list[dict],
    cfg: dict,
    lead_state: Optional[dict] = None,
    *,
    ig_user_id: str = "",
    new_texts: Optional[list[str]] = None,
) -> TurnResult:
    """Read the conversation, decide the reply.

    `history` is the whole conversation as `{"role": "user"|"assistant", "content": str}`, oldest
    first. `new_texts` is the batch of messages she just sent (they are already the tail of
    `history`). `cfg` is the `app_config` table as a flat dict - links, knowledge base, model.
    """
    model = (cfg.get("brain_model") or "").strip() or DEFAULT_MODEL
    openings = cfg.get("_recent_openings") or []
    state = dossier.empty_state() if lead_state is None else {**dossier.empty_state(), **lead_state}

    if not history:
        return TurnResult(lead_state=state, action="NO_HISTORY")

    try:
        read, read_usage = await read_turn(openai_client, history, model=model)
    except Exception:
        logger.exception("Reader failed for %s. Pausing rather than guessing", ig_user_id)
        return TurnResult(
            lead_state=state,
            pause=True,
            pause_reason="reader_error",
            add_tag=True,
            action="READER_ERROR",
        )

    state = dossier.merge(state, read)
    gate = dossier.gate(state, read)

    trace = {
        "read": read,
        "gate": {
            "allow_booking": gate.allow_booking,
            "escalate": gate.escalate,
            "reason": gate.escalate_reason,
            "handover_message": gate.handover_message,
            "notes": gate.notes,
        },
    }

    if gate.escalate:
        # The writer is never called on a handover turn, so nothing about it is generated. She
        # gets either nothing or one fixed line Sonia wrote, which is the only way to be certain
        # the AI cannot answer her question on its way out of the conversation.
        fixed = (cfg.get(gate.handover_message) or "").strip() if gate.handover_message else ""
        logger.info(
            "Handover for %s: %s (%s)", ig_user_id, gate.escalate_reason,
            "fixed line" if fixed else "silent",
        )
        state["phase"] = state.get("phase") or dossier.EXPLORING
        return TurnResult(
            reply_text=fixed or None, lead_state=state, pause=True,
            pause_reason=gate.escalate_reason, add_tag=True,
            action=f"HANDOVER:{gate.escalate_reason}",
            usage=_usage(model, read_usage, None), trace=trace,
        )

    chosen = select_playbooks(
        _playbooks(),
        intent=read["intent"],
        tags=read["tags"] + gate.tags,
        language=read["language"],
        allow_booking=gate.allow_booking,
        limit=3,
    )
    trace["playbooks"] = [pb.name for pb in chosen]

    system = "\n\n---\n\n".join(
        part for part in (
            build_write_prompt(cfg, gate.blocks),
            render_examples(
                chosen, allow_booking=gate.allow_booking, values=config_values(cfg),
            ),
            dossier.render(state),
            _brief(gate, read, openings),
        ) if part
    )

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            temperature=float(cfg.get("brain_temperature") or 0.8),
            messages=[{"role": "system", "content": system}] + history,
        )
    except Exception:
        logger.exception("Writer failed for %s. Pausing rather than sending nothing", ig_user_id)
        return TurnResult(
            lead_state=state, pause=True, pause_reason="writer_error",
            add_tag=True, action="WRITER_ERROR", trace=trace,
        )

    reply = (response.choices[0].message.content or "").strip()
    usage = _usage(model, read_usage, response)

    booking_link = (cfg.get("booking_link") or "").strip()
    sent_link = bool(booking_link) and booking_link in reply

    if state.get("phase") == dossier.LINK_SENT and (state.get("slots") or {}).get("email"):
        state["phase"] = dossier.POST_BOOKING
        return TurnResult(
            reply_text=reply or None, lead_state=state, pause=True,
            pause_reason="qualified_link_sent", add_tag=False,
            action="POST_BOOKING", usage=usage, trace=trace,
        )

    if sent_link:
        state["phase"] = dossier.LINK_SENT
        return TurnResult(
            reply_text=reply or None, lead_state=state, pause=True,
            pause_reason="qualified_link_sent", add_tag=True, qualified=True,
            action="BOOKING_SENT", usage=usage, trace=trace,
        )

    state["phase"] = state.get("phase") or dossier.OPENING
    if (state.get("counters") or {}).get("turns", 0) > 1:
        state["phase"] = dossier.EXPLORING

    return TurnResult(
        reply_text=reply or None, lead_state=state,
        action=f"REPLY:{read['intent']}", usage=usage, trace=trace,
    )
