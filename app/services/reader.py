"""Stage 1: read the conversation and report what she actually said.

Deliberately narrow. This call writes nothing a lead will ever see, holds no opinions about tone,
and never decides anything, it extracts facts so that selection and the gates have typed values to
work with. A small model does this reliably precisely because it is the only thing being asked.

One field gets a second opinion before it is trusted. `language: "other"` is the only value in the
extraction that ends a conversation on its own, silently, with no reply sent, so a single sample of
it is not enough. See `_confirm_unsupported_language`.
"""
import json
import logging
import re

from openai import AsyncOpenAI

from app.services.prompts import build_language_prompt, build_read_prompt, build_safety_prompt

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

VALID_INTENTS = {
    "new_prospect", "warm_prospect", "existing_client", "former_client",
    "pregnancy_announcement", "birth_announcement", "gratitude", "fertility_question",
    "program_question", "price_question", "ivf_question", "emotional_distress",
    "grief_or_loss", "advice_request", "free_info_request", "collaboration",
    "media_request", "technical_support", "complaint", "not_a_fit", "spam_or_aggression",
}

PATHS = ("terminal", "direct_answer", "nurturing", "qualification")


def _coerce(raw: str) -> dict:
    """Parse the model's JSON, tolerating a code fence or a stray sentence around it."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(raw or "")
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    logger.warning("Reader returned unparseable JSON: %r", (raw or "")[:300])
    return {}


def normalise(data: dict) -> dict:
    """Force the extraction into the shape the rest of the pipeline expects.

    A reader that invents an intent or returns a string where a list belongs must not be able to
    take the turn down with it; anything unrecognised degrades to the safe default rather than
    raising.
    """
    intent = data.get("intent")
    if intent not in VALID_INTENTS:
        if intent:
            logger.info("Reader returned unknown intent %r, falling back", intent)
        intent = "new_prospect"

    language = data.get("language")
    if language not in ("en", "es", "other"):
        language = "en"

    # Manual §A: which of the 4 conversation types this message is. Unknown means no note.
    path = data.get("path")
    if path not in PATHS:
        path = None

    slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
    flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}

    age = slots.get("age")
    if isinstance(age, str) and age.strip().isdigit():
        slots["age"] = int(age.strip())
    elif age is not None and not isinstance(age, int):
        slots.pop("age", None)

    # `structural` is documented under boundary facts; accept it at either level.
    structural = data.get("structural") or flags.get("structural") or slots.pop("structural", None)
    if structural:
        flags["structural"] = structural

    return {
        "path": path,
        "intent": intent,
        "language": language,
        "explicit_question": data.get("explicit_question") or None,
        "slots": slots,
        "flags": flags,
    }


def _transcript(history: list[dict]) -> str:
    lines = []
    for message in history:
        who = "Lead" if message.get("role") == "user" else "Sonia"
        lines.append(f"{who}: {message.get('content', '')}")
    return "\n".join(lines)


def _just_sent(history: list[dict]) -> str:
    """The messages she sent this turn, which is the run of user messages at the end.

    Several in a row is the debounce: she typed four things before the worker woke up, and they are
    one turn. Everything before the last assistant message belongs to the conversation, not to this
    turn, and both of the narrow calls below are deliberately about this turn only.
    """
    latest = []
    for message in reversed(history):
        if message.get("role") != "user":
            break
        latest.append(message.get("content", ""))
    return "\n".join(reversed(latest))


def _tuning(model: str, effort: str) -> dict:
    """The arguments that differ between a reasoning model and a completion model.

    The GPT-5 family rejects `temperature` outright, only the default 1 is accepted, so the
    determinism this file has always asked for has to be bought a different way: `reasoning_effort`
    is the only dial it offers, and its thinking is billed as completion tokens. The 4.1 family
    knows nothing about reasoning and takes `temperature=0`. Neither set of arguments is valid for
    the other model, so the call cannot simply send both.
    """
    if model in ("gpt-5", "gpt-5-mini", "gpt-5-nano"):
        return {"reasoning_effort": effort}
    # GPT-5.1 onwards and GPT-6 have no `minimal`; the least thinking they allow is `none`, and
    # with it off they accept `temperature` again.
    if model.startswith(("gpt-5.", "gpt-6")):
        if effort == "minimal":
            return {"reasoning_effort": "none", "temperature": 0}
        return {"reasoning_effort": effort}
    return {"temperature": 0}


def _cap(model: str, visible: int) -> dict:
    """A ceiling on the answer, expressed the way this model wants it.

    `max_tokens` is rejected by the GPT-5 family in favour of `max_completion_tokens`, and the two
    do not mean the same thing: the reasoning budget comes out of the same allowance, so a cap
    sized for the visible answer is spent thinking and the content comes back empty. Hence the
    headroom, which is a ceiling rather than a spend and is not normally reached.
    """
    if model.startswith(("gpt-5", "gpt-6")):
        return {"max_completion_tokens": visible + 512}
    return {"max_tokens": visible}


# Asked on its own rather than as one field of the extraction, because the point is a second
# opinion and a second sample of the same question is not one. The extractor is answering twenty
# questions at once about a long transcript; this asks one question about her words.
# Legacy wording, kept for reference. The live prompt is `prompts_simple/language.md`.
_LANGUAGE_PROMPT = (
    "You identify what language somebody is writing in. Answer with one word and nothing else:\n\n"
    "en   - English, including broken, minimal or heavily misspelled English\n"
    "es   - Spanish, including a message that mixes Spanish and English\n"
    "other - a language that is neither English nor Spanish\n\n"
    "Portuguese, Italian and Catalan resemble Spanish and are not Spanish: they are `other`. "
    "Spanish is not `other`, however short the message. Judge the words she actually wrote, not "
    "how well she writes."
)


async def _confirm_language(
    client: AsyncOpenAI,
    history: list[dict],
    *,
    model: str,
) -> tuple[str, dict]:
    """Ask a second time, narrowly, which language she is actually writing in.

    This decides whether she is answered at all, and it gets the answer wrong in both directions.
    `other` sets `needs_human`, and that handover sends nothing: measured on the round 5 corpus the
    extractor returned `other` for plain Spanish about 1 time in 10, and the woman who tripped that
    coin flip stopped being answered. In the other direction it read a Portuguese message as `es`
    5 times in 10 and the reply came back in a mixture of the two.

    Spanish and Portuguese are the confusable pair, so both are worth a second look and `en` is
    not: nothing here is ever mistaken for English.

    Only the message she just sent is asked about. An earlier draft sent her last four, and on the
    conversation this exists for, three of them were English and the Portuguese one she had just
    switched into was outvoted: the answer came back `es` and she was replied to in a mixture of
    Spanish and Portuguese. The language she is writing in now is the one that has to be read.
    """
    said = _just_sent(history)
    if not said:
        return "en", {"prompt_tokens": 0, "completion_tokens": 0}

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_language_prompt()},
            {"role": "user", "content": said},
        ],
        **_tuning(model, "minimal"),
        **_cap(model, 3),
    )
    answer = (response.choices[0].message.content or "").strip().strip(".`").lower()
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
    }
    # An unparseable answer is no opinion, and the caller acts on nothing. It used to be read as
    # `other`, which is not the same thing: on a lead the extraction had already called `es`, a
    # missing answer would confirm a language we do not support and end her conversation. A
    # reasoning model can return an empty completion where a completion model essentially never
    # did, so the difference stopped being theoretical.
    return (answer if answer in ("en", "es", "other") else ""), usage


# The flags where a miss is catastrophic, a false positive costs a human five minutes, and the
# message decides it on its own. All three conditions matter. Every one of these ends the turn, so
# a false positive silently stops a conversation that was going well, and the only reason that is
# an acceptable trade is that these four are unmistakable in one message.
#
# `requested_medication` and `requested_surgery_advice` are deliberately NOT here, although they
# are the two F63 measured degrading in context. They cannot be judged from one message because
# the thing being asked about is usually a pronoun: "is it worth doing or should I wait?" needs the
# previous message to say what "it" is. Asked without that, the check fired on "is it worth me even
# trying naturally?", on "should I push for more testing?" and on "is there really nothing that can
# open them up?", and ended five conversations that were going correctly. They stay with the main
# extraction, which can see what she is referring to.
# These four are defined twice: in `safety.md` for this pass, and in `read.md` for the main
# extraction. The two have to agree. This pass is additive and can only turn a flag ON, so where
# they disagree this one wins and the carve-outs in `read.md` are silently discarded. That is
# exactly what happened to client review point 9: the phone-number carve-out was added to the
# reader prompt, the safety copy was not touched, and the flag kept firing.
SAFETY_FLAGS = ("crisis", "urgent_medical", "asked_if_ai", "asked_for_human")


async def _safety_read(
    client: AsyncOpenAI,
    history: list[dict],
    *,
    model: str,
) -> tuple[list[str], dict]:
    """A second, narrow look at what she just sent, asked without the conversation around it.

    Round 5 measured the same words setting `requested_surgery_advice` 10 times out of 10 as a
    first message and 6 times out of 10 after seven turns, and `asked_if_ai` 6 times out of 10 in a
    long transcript against 6 out of 6 alone. The flags are not weaker in principle, they are
    weaker in context: the extractor is answering twenty questions about a whole conversation and
    the one that matters is competing with the rest.

    So this asks the six that must never be missed, about her latest message only, which is the
    position they were measured strongest in. It cannot clear a flag, only add one, so the worst it
    can do is send a conversation to a person who did not need it.
    """
    latest = _just_sent(history)
    if not latest:
        return [], {"prompt_tokens": 0, "completion_tokens": 0}

    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_safety_prompt()},
            {"role": "user", "content": latest},
        ],
        **_tuning(model, "minimal"),
    )
    data = _coerce(response.choices[0].message.content or "")
    triggers = data.get("triggers") if isinstance(data.get("triggers"), list) else []
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
    }
    return [t for t in triggers if t in SAFETY_FLAGS], usage


async def read_turn(
    client: AsyncOpenAI,
    history: list[dict],
    *,
    model: str,
) -> tuple[dict, dict]:
    """Return (extraction, usage)."""
    # The one call here worth paying to think. It answers twenty questions at once about a whole
    # transcript, and that is exactly the condition the flags were measured degrading under. The
    # two narrow calls below judge one short message and stay at `minimal`.
    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_read_prompt()},
            {"role": "user", "content": _transcript(history)},
        ],
        **_tuning(model, "low"),
    )
    raw = response.choices[0].message.content or ""
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
    }
    read = normalise(_coerce(raw))

    extracted_human = bool(read["flags"].get("asked_for_human"))
    triggers, safety_usage = await _safety_read(client, history, model=model)
    usage = {key: usage[key] + safety_usage[key] for key in usage}
    for flag in triggers:
        if not read["flags"].get(flag):
            logger.info("Safety read caught %s that the extraction missed", flag)
        read["flags"][flag] = True

    # A request for Sonia's number is a request for another channel to the same person, and the safety
    # pass, which sees only her last message, still reads it as a request for a human about one run
    # in three. So on a phone request the handover stands only if the main extraction, which has the
    # whole conversation, also saw her ask for somebody else.
    if read["flags"].get("asked_for_phone") and read["flags"].get("asked_for_human") \
            and not extracted_human:
        logger.info("Dropping asked_for_human on a phone request: she asked for a channel")
        read["flags"].pop("asked_for_human", None)

    if read["language"] in ("es", "other"):
        second, extra = await _confirm_language(client, history, model=model)
        usage = {key: usage[key] + extra[key] for key in usage}

        # The narrow call is only allowed to answer the question it was asked, which is whether
        # this is a language we support. Choosing between two languages we do support is the
        # extraction's job: it has the whole conversation, and the narrow call has her last few
        # messages, so on a Spanish conversation where she writes one line in English it would
        # switch the reply language and drop the Spanish conversations from the prompt.
        if not second:
            logger.warning("Language check returned nothing. Leaving the extraction as it is")
        elif read["language"] == "other" and second != "other":
            # `read.md` asks for `needs_human` on the same line that asks for `other`, so the
            # flag is part of the answer being withdrawn and has to go with it. Anything that
            # genuinely needs a person is read again from the whole transcript next turn.
            read["flags"].pop("needs_human", None)
            read["language"] = second
            logger.info("Reader said language=other, second opinion says %s. Not escalating", second)
        elif read["language"] == "es" and second == "other":
            read["language"] = "other"
            logger.info("Reader said language=es, second opinion says other. Escalating")

    return read, usage
