"""Veto panel - LLM call #3, conditional.

Named honestly: this is a veto panel, not a jury. Majority voting is the wrong
shape for safety-asymmetric decisions - one judge spotting a fabricated claim
should win, not be outvoted two to one.

Each judge answers ONE binary question. That is an extraction-shaped task, which
gpt-4o-mini does adequately; holistic quality ratings, which it does not do
adequately, are avoided on purpose.

It runs only when something is already suspicious, so the typical turn is still
two calls.
"""
import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.services.brain.llm import completion_kwargs, model_for, usage_of, with_retry

logger = logging.getLogger(__name__)


class Verdict(BaseModel):
    problem: bool          # true = something is wrong with this reply
    offending: Optional[str]


_FAITHFUL = """You check one reply for invented content.

You are given FACTS (what the lead told us), TRANSCRIPT, KNOWLEDGE (the only approved claims about fertility and about the coach's approach), and the REPLY.

Answer one question: does the REPLY state any fact about the lead, or any claim about fertility or about the coach's approach, that is NOT present in FACTS, TRANSCRIPT or KNOWLEDGE?

problem=true only for a genuine addition of unsupported content. Ordinary warmth, empathy, and rephrasing of the approved material are fine. Put the offending sentence in `offending`."""

_ANSWERED = """You check whether the lead got a real response to what she asked.

You are given the QUESTION she asked and the REPLY.

Set problem=true ONLY when the reply gives her nothing to take away: it ignores the question, changes the subject to something she did not ask about, or consists only of a question back to her.

Everything below COUNTS as a real response. Set problem=false for all of them:

- A direct answer, however brief.
- A negative answer. "At 29 and three months in you probably don't need this yet, because most people conceive without help" fully answers whether she should join.
- A boundary given with a reason, where the boundary is about the THING SHE ASKED FOR. This coach is NOT permitted to give supplement protocols, dosages, lab interpretations or personal medical plans over direct message. So "I can't put together a protocol for you without seeing your full history, that needs a proper conversation" IS the correct and complete response to a request for a protocol. It is a real response, not an evasion.
- An honest "it depends on your situation", where she is told what it depends on.

You are judging whether she received a real response, NOT whether she received the response she was hoping for, and NOT whether you would have answered differently.

Put the reason in `offending`."""

_PREMATURE = """You check for one specific thing: offering the next commercial step before the lead has been qualified.

You are given the REPLY. Answer problem=true ONLY if it does one of these:
- invites her to book, schedule, or grab a time
- offers, promises or proposes a call, consultation or session
- tells her she is a good fit, or that she qualifies, or invites her to join or sign up

Everything else is fine, and you must answer problem=false for it. In particular these are NOT problems: warmth, empathy, answering her question, explaining the approach, saying what could help, and general offers of support such as "we can look at this together", "I can help with that", or "there is a lot worth exploring here". Those are the reply doing its job.

You are also given the APPROVED SUBSTANCE the reply was allowed to draw on. If that substance itself points her toward the call - the approved answer on pricing does exactly this - then the reply repeating it is NOT a problem. Judge only what goes beyond the approved material.

Put the offending sentence in `offending` when problem=true."""


async def _judge(client, system: str, user: str, model: str, name: str):
    async def _call():
        return await client.chat.completions.parse(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format=Verdict,
            **completion_kwargs(model, max_tokens=150, temperature=0),
        )
    completion = await with_retry(_call, what=f"checker:{name}")
    return completion.choices[0].message.parsed, usage_of(completion, model, f"checker:{name}")


async def check(
    openai_client: AsyncOpenAI,
    bubbles: list[str],
    *,
    history: list[dict],
    known_facts: dict,
    knowledge_texts: list[str],
    question_asked: Optional[str] = None,
    gate_passed: bool = False,
    cfg: Optional[dict] = None,
) -> tuple[list[str], dict]:
    """Run the applicable judges in parallel. Returns (violations, usage)."""
    model = model_for("checker", cfg)
    reply = "\n".join(bubbles)
    transcript = "\n".join(
        f"{'Lead' if m.get('role') == 'user' else 'Sonia'}: {m.get('content', '')}"
        for m in history[-6:]
    )

    jobs = [(
        "faithful", _FAITHFUL,
        f"FACTS: {known_facts or '(none)'}\n\nTRANSCRIPT:\n{transcript}\n\n"
        f"KNOWLEDGE:\n" + ("\n".join(f"- {k}" for k in knowledge_texts) or "(none)")
        + f"\n\nREPLY:\n{reply}",
    )]
    if question_asked:
        jobs.append((
            "answered", _ANSWERED,
            f"QUESTION: {question_asked}\n\nREPLY:\n{reply}",
        ))
    if not gate_passed:
        jobs.append((
            "premature", _PREMATURE,
            "APPROVED SUBSTANCE:\n"
            + ("\n".join(f"- {k}" for k in knowledge_texts) or "(none)")
            + f"\n\nREPLY:\n{reply}",
        ))

    results = await asyncio.gather(
        *(_judge(openai_client, system, user, model, name) for name, system, user in jobs),
        return_exceptions=True,
    )

    violations, usages = [], []
    for (name, _, _), result in zip(jobs, results):
        if isinstance(result, Exception):
            # A judge that cannot run must not silently pass the reply, but it
            # must not block the turn either: record it and let uncertainty decide.
            logger.warning("Checker %s failed: %s", name, result)
            violations.append(f"checker_unavailable:{name}")
            continue
        verdict, usage = result
        usages.append(usage)
        if verdict and verdict.problem:
            violations.append(f"{name}:{(verdict.offending or '')[:60]}")

    from app.services.brain.llm import combine_usage
    return violations, combine_usage(*usages)
