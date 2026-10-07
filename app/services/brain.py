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

A CTA keyword opener is the other turn no model sees, for the opposite reason. A conversation that
begins with the word she commented on a reel and nothing else contains no information to read and
nothing to answer, so it gets Sonia's own welcome and waits. See `cta.py`.

Two things the app needs from any implementation, both unchanged:

  * a `TurnResult`, whose fields ARE the side effects the worker applies - reply, pause, tag, and
    the lead state to persist;
  * `lead_state`, an arbitrary JSON dict owned entirely by the brain.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.services import cta, dossier
from app.services.few_shots import load_few_shot_scenarios, render_examples
from app.services.message_splitter import strip_dashes, use_digits
from app.services.prompts import build_write_prompt, config_values, turn_notes
from app.services.reader import read_turn

logger = logging.getLogger(__name__)

# ManyChat tag applied whenever a turn needs a human. Set in their dashboard.
HUMAN_REVIEW_TAG = 86596410

DEFAULT_MODEL = "gpt-4.1-mini"

# The two stages want different things, so they no longer share a model. Reading is extraction
# under load: twenty typed answers about a whole transcript, and the flags `reader.py` documents
# degrading in long context are the ones a handover depends on, so that call is worth a model that
# thinks. Writing is voice, where thinking buys little and costs the `temperature` dial, which the
# GPT-5 family does not offer at all. Either is overridable from admin.
DEFAULT_READ_MODEL = "gpt-5-mini"

# USD per 1M tokens, (prompt, completion). Unknown models fall back to the default's rate so a
# model swap in admin never breaks cost reporting. Reasoning tokens are billed as completion
# tokens, so the read stage's completion figure is mostly thinking rather than the JSON.
_RATES = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6-sol": (2.00, 10.00),
}


def _write_tuning(model: str, temperature: float) -> dict:
    """The writer's sampling arguments, in the form each model family accepts.

    Voice wants a temperature. The original GPT-5 models reject it outright, so they get the least
    thinking they allow instead. From 5.1 on, and in GPT-6, reasoning can be switched off entirely,
    and with it off the temperature is accepted again.
    """
    if model in ("gpt-5", "gpt-5-mini", "gpt-5-nano"):
        return {"reasoning_effort": "minimal"}
    if model.startswith(("gpt-5.", "gpt-6")):
        return {"reasoning_effort": "none", "temperature": temperature}
    return {"temperature": temperature}


_playbook_cache: dict | None = None

# Gated turns that still have a conversation in front of them: the boundary is about the thing she
# just asked for, and the next question is still worth asking. See `_brief`.
CONTINUES = ("out_of_scope_request", "lab_request", "demands_guarantee")


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


def _usage(read_model: str, write_model: str, read_usage: dict, response) -> dict:
    """Token cost for the turn. A handover turn only ever paid for the read call.

    The two stages are priced separately because they are two different models now. Charging the
    whole turn at one rate was close enough while they were the same string and is not close at
    all once reading costs less per token than writing.
    """
    write_prompt = getattr(getattr(response, "usage", None), "prompt_tokens", 0)
    write_completion = getattr(getattr(response, "usage", None), "completion_tokens", 0)
    return {
        "prompt_tokens": read_usage["prompt_tokens"] + write_prompt,
        "completion_tokens": read_usage["completion_tokens"] + write_completion,
        # The row records the model whose voice is on the message, which is the writer's.
        "ai_model": write_model,
        "token_cost": (
            _cost(read_model, read_usage["prompt_tokens"], read_usage["completion_tokens"])
            + _cost(write_model, write_prompt, write_completion)
        ),
    }


def _brief(gate: dossier.Gate, read: dict, state: dict, openings: list[str]) -> str:
    """The per-turn notes: what this reply has to do, and what it must not contain.

    This only decides which notes apply. Their wording lives in `prompts_simple/turn.md`, so a
    change to what the writer is told is a prompt edit, not a deploy.
    """
    notes = turn_notes()
    lines = ["# THIS TURN"]

    def add(name: str, **values) -> None:
        text = notes.get(name)
        if not text:
            return
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        lines.append(f"- {text}")

    flags = read.get("flags") or {}
    sticky = state.get("flags") or {}

    if read.get("explicit_question"):
        add("question", question=read["explicit_question"])
    if read.get("path"):
        add(f"path_{read['path']}")

    if flags.get("asked_if_ai"):
        add("asked_if_ai")
    # A request for Sonia's number is a request for another channel to the same person, not a doubt
    # about who is typing. If she raised both, the AI note above covers it.
    elif flags.get("asked_for_phone"):
        add("asked_for_phone")
        add("phone_with_link" if gate.allow_booking else "phone_no_link")

    if sticky.get("wants_pregnancy_support"):
        add("pregnancy_support")
    if flags.get("has_other_provider"):
        add("has_other_provider")

    if gate.allow_booking:
        add("booking_open")
        if not dossier._stated((state.get("slots") or {}).get("age")):
            add("age_unknown")
        add("partner")
    else:
        add("booking_shut")

    if gate.block_reason in ("not_enough_context", "first_exchange"):
        add("early")
    if gate.block_reason:
        add(f"reason_{gate.block_reason}")
    if gate.block_reason in CONTINUES:
        add("continues")

    # The education spiral, counted in `dossier` rather than left to the writer to notice. Only
    # where she is being taught: a woman working through a boundary asks the same shape of
    # question, and a masterclass handed to her then reads as a consolation prize.
    teaching = int((state.get("counters") or {}).get("teaching", 0))
    if gate.block_reason not in ("", "first_exchange", "not_enough_context"):
        teaching = 0
    if teaching >= 3 and sticky.get("masterclass_sent"):
        add("teaching_repeat")
    elif teaching >= 3:
        add("teaching_many", count=teaching)
    elif teaching == 2:
        add("teaching_two")

    if openings and notes.get("openings"):
        lines.append("")
        lines.append(notes["openings"])
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
    read_model = (cfg.get("read_model") or "").strip() or DEFAULT_READ_MODEL
    openings = cfg.get("_recent_openings") or []
    state = dossier.empty_state() if lead_state is None else {**dossier.empty_state(), **lead_state}

    if not history:
        return TurnResult(lead_state=state, action="NO_HISTORY")

    # A conversation that opens with a CTA keyword and nothing else is answered by Sonia's own line,
    # with no model called at all. See `cta.py`: the word is how the DM opened rather than anything
    # she has told us, so there is nothing to read and nothing to write. The counters are left alone
    # on purpose, which makes her *answer* the first real exchange rather than the second.
    welcome = (cfg.get("cta_welcome_message") or "").strip()
    if welcome and cta.is_opener(history, cfg):
        logger.info("CTA keyword opener for %s, sending the fixed welcome", ig_user_id)
        state["phase"] = state.get("phase") or dossier.OPENING
        return TurnResult(
            reply_text=welcome, lead_state=state, action="CTA_WELCOME",
            trace={"cta": {"keyword": cta.normalise(history[-1].get("content", ""))}},
        )

    try:
        read, read_usage = await read_turn(openai_client, history, model=read_model)
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
            usage=_usage(read_model, model, read_usage, None), trace=trace,
        )

    chosen = list(_playbooks().values())
    trace["playbooks"] = [pb.name for pb in chosen]

    system = "\n\n---\n\n".join(
        part for part in (
            build_write_prompt(cfg, gate.blocks),
            render_examples(chosen, allowed_blocks=gate.blocks, values=config_values(cfg)),
            dossier.render(state),
            _brief(gate, read, state, openings),
        ) if part
    )

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}] + history,
            **_write_tuning(model, float(cfg.get("brain_temperature") or 0.8)),
        )
    except Exception:
        logger.exception("Writer failed for %s. Pausing rather than sending nothing", ig_user_id)
        return TurnResult(
            lead_state=state, pause=True, pause_reason="writer_error",
            add_tag=True, action="WRITER_ERROR", trace=trace,
        )

    # Applied here rather than in the worker so that every caller gets it: the worker, the admin
    # sandbox and the probe all read `reply_text`, and a transcript that shows a dash the lead
    # would never have received is a transcript nobody can review against the writing rules.
    reply = use_digits(strip_dashes((response.choices[0].message.content or "").strip()))
    usage = _usage(read_model, model, read_usage, response)

    booking_link = (cfg.get("booking_link") or "").strip()
    sent_link = bool(booking_link) and booking_link in reply

    # Remembered so the next turn can be told not to send it twice, which is the difference between
    # closing an education spiral and answering six questions with the same two sentences.
    masterclass_link = (cfg.get("masterclass_link") or "").strip()
    if masterclass_link and masterclass_link in reply:
        state["flags"]["masterclass_sent"] = True

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

    # A conversation that has reached the link keeps the phase it reached. Overwriting it here sent
    # the turn after a booking back to EXPLORING, which drops the `post_booking` block from the
    # gate, so the writer had no masterclass link to send and the one scripted sequence in the
    # manual ran with a piece missing.
    if state.get("phase") not in (dossier.LINK_SENT, dossier.POST_BOOKING):
        state["phase"] = state.get("phase") or dossier.OPENING
        if (state.get("counters") or {}).get("turns", 0) > 1:
            state["phase"] = dossier.EXPLORING

    return TurnResult(
        reply_text=reply or None, lead_state=state,
        action=f"REPLY:{read['intent']}", usage=usage, trace=trace,
    )
