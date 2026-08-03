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

from app.services.brain.llm import model_for, usage_of, with_retry

logger = logging.getLogger(__name__)


class Verdict(BaseModel):
    problem: bool          # true = something is wrong with this reply
    offending: Optional[str]


_FAITHFUL = """You check one reply for invented content.

You are given FACTS (what the lead told us), TRANSCRIPT, KNOWLEDGE (the only approved claims about fertility and about the coach's approach), and the REPLY.

Answer one question: does the REPLY state any fact about the lead, or any claim about fertility or about the coach's approach, that is NOT present in FACTS, TRANSCRIPT or KNOWLEDGE?

problem=true only for a genuine addition of unsupported content. Ordinary warmth, empathy, and rephrasing of the approved material are fine. Put the offending sentence in `offending`."""

_ANSWERED = """You check whether a reply answers a question.

You are given the QUESTION the lead asked and the REPLY.

Answer one question: does the REPLY leave her question unanswered - by deflecting it, changing the subject, or replying only with a question of its own?

problem=true means she did NOT get an answer. A brief but real answer is fine.

A NEGATIVE answer is still an answer. If she asked whether she should join, sign up for, or needs the programme, then a reply telling her she probably does NOT need it yet, and why, is a COMPLETE answer. Saying "most people in your situation conceive without help, so it would not be honest to sell you this" answers the question fully. Do NOT mark that as a deflection.

Judge whether she received an answer, not whether she received the answer she was hoping for.

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
            response_format=Verdict, temperature=0, max_tokens=150,
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
