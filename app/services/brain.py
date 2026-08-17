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
from app.services.few_shots import load_few_shot_scenarios, render_examples, select_playbooks
from app.services.message_splitter import strip_dashes
from app.services.prompts import build_write_prompt, config_values
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
}

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


def _list(items: list[str]) -> str:
    """"a, b or c", so the brief reads as a sentence rather than as a form."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " or " + items[-1]


def _brief(gate: dossier.Gate, read: dict, state: dict, openings: list[str]) -> str:
    """The per-turn instructions: what this reply has to do, and what it must not contain."""
    lines = ["# THIS TURN"]

    question = read.get("explicit_question")
    if question:
        lines.append(f"- She asked: \"{question}\". Answer it in this message, before anything else.")
    if read.get("emotional_state"):
        lines.append(f"- She reads as: {read['emotional_state']}. Match that.")

    missing = dossier.missing_facts(state)

    if gate.allow_booking:
        lines.append(
            "- A consultation is available to you this turn. Offer it only if it is genuinely the "
            "most useful next step for her right now, most turns it is not. If you do offer it, "
            "the link goes in this message: never ask whether she would like you to send it."
        )
    else:
        lines.append(
            "- No consultation this turn. Do not offer a call, do not hint at one, and do not "
            "suggest she get in touch to arrange one."
        )

    # Step 4 of the conversation flow. The gate can withhold a link but it cannot ask a question,
    # so a conversation that never learns anything about her stalls with the link shut and no
    # route to opening it. Naming the gap is what turns "no consultation this turn" from a dead
    # end into the next thing to do.
    # Age gets its own line rather than a place in the list. A comma list carries no priority, so
    # "ask the one that matters most" was read off the emotional beat of her message and the answer
    # was almost always partner status or priorities, which feel warmer to ask. Age is the only one
    # that can end the conversation, so on this turn it is the only one worth a question.
    if gate.block_reason == "age_unknown":
        lines.append(
            "- You do not know how old she is, and it is the one thing you cannot invite her to a "
            "call without knowing. It is not an item on a list of useful facts: it decides whether "
            "there is anything here for her at all, so it comes before the rest of them and before "
            "anything about a partner, which only ever changes who else is on the call. Answer what "
            "she asked, then ask her age, on its own and in your own words. Nothing else is worth a "
            "question this turn."
        )
    elif gate.block_reason in ("not_enough_context", "first_exchange") and missing:
        lines.append(
            "- You still do not know " + _list(missing) + ". Until you know at least three things "
            "about her situation, a call cannot honestly be offered, so the way forward is to "
            "learn one of them. Answer what she asked first, then ask for the single one that "
            "would most change what you say next. One question, in her words, not a list and not "
            "an intake form."
        )
    elif missing and gate.allow_booking:
        lines.append(
            "- Before this becomes a booking you should know " + _list(missing) + ". If you are "
            "about to send the link and cannot say what she told you about those, ask the one "
            "that matters most instead and send the link on a later turn."
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
        "currently_pregnant": (
            "- She is pregnant now. Congratulate her before anything else. Coaching through a "
            "pregnancy is not what you do, so there is nothing here to sell and nothing to "
            "qualify: no program, no price, no next step, no call. If she asks you to coach her "
            "through it, say plainly that this is not what you do and leave her with the people "
            "caring for her."
        ),
    }
    if gate.block_reason in reason_rules:
        lines.append(reason_rules[gate.block_reason])

    # A boundary is not the end of the conversation, and the gate can shut the link but it cannot
    # ask a question. The forward move above was reachable only from the two context reasons, so a
    # turn gated for any other reason arrived at the writer as a prohibition with nothing to do
    # instead: four messages answered with four refusals, no question asked in any of them, and the
    # last one explaining away the missing link, which `60_contract.md` forbids by name.
    #
    # Only the reasons that leave something to talk about. `recent_loss` and `currently_pregnant`
    # are turns where asking her anything is the mistake, the structural and age reasons have
    # already ended it, and `tubal_status_unclear` carries a question of its own above: a second one
    # would put two question marks in a reply the contract allows one in.
    if gate.block_reason in CONTINUES and missing:
        lines.append(
            "- That is why the link is shut this turn, not a reason the conversation is over. Say "
            "it once, do not spend the whole message on it, then take her forward: you still do "
            "not know " + _list(missing) + ", so ask the one that would most change what you say "
            "next. One question, in her words."
        )

    # The spiral, counted here rather than left to the writer to notice. Five rounds of "count the
    # general questions" in the static prompt never closed it: by the time the conversation is
    # eight questions deep, each one still looks like a reasonable question asked by a reasonable
    # person, and the model answers it. A number in front of it is harder to talk past than a rule.
    # Only where she is actually being taught. A woman working through a structural boundary asks
    # the same shape of question, "so is there really nothing that can open them up", and it counts
    # as general because it tells us nothing new about her. Handing her the masterclass at that
    # moment reads as a consolation prize for the answer she has just been given.
    teaching = int((state.get("counters") or {}).get("teaching", 0))
    if gate.block_reason not in ("", "first_exchange", "not_enough_context", "age_unknown"):
        teaching = 0

    already_sent = bool((state.get("flags") or {}).get("masterclass_sent"))
    if teaching >= 3 and already_sent:
        # Without this the instruction reads as "do it again", and it was followed exactly: six
        # consecutive replies of the same two sentences and the same link. Saying the same thing a
        # sixth time is its own failure, and a lead reading it knows precisely what she is talking
        # to.
        lines.append(
            "- These are still general questions and you have already sent her the masterclass, so "
            "do not send it again and do not repeat what you said when you did. Answer this one in "
            "a single line if it has an honest one-line answer, or say you have nothing to add "
            "from here. Then ask the one thing that would let you say something real about her "
            "situation, or leave the door open and stop."
        )
    elif teaching >= 3:
        lines.append(
            f"- This is general question number {teaching} in a row, with nothing about her in any "
            "of them. Stop teaching. Do not answer this one: say plainly that going one question "
            "at a time is not getting her anywhere, and send the masterclass link in this message."
        )
    elif teaching == 2:
        lines.append(
            "- That is two general questions in a row. Answer this one briefly, then stop "
            "teaching: say what you have noticed and send the masterclass link in this message."
        )

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
            _brief(gate, read, state, openings),
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

    # Applied here rather than in the worker so that every caller gets it: the worker, the admin
    # sandbox and the probe all read `reply_text`, and a transcript that shows a dash the lead
    # would never have received is a transcript nobody can review against the writing rules.
    reply = strip_dashes((response.choices[0].message.content or "").strip())
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
