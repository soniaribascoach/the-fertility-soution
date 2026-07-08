"""Extractor — LLM call #1. The LLM as a pure data processor.

Reads the recent conversation and the facts already known, and returns strict
structured JSON: slot deltas (only what the latest message explicitly reveals),
the lead's intent, an empathy situation-type, out-of-scope and human-takeover
signals. It NEVER produces user-facing text.

Uses OpenAI structured outputs (`chat.completions.parse`) at temperature 0 so
the output space is constrained to the schema and the model cannot free-form.
"""
import json
import logging
from typing import Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.services.brain.constants import Intent

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"
_PROMPT_TOKEN_COST = 0.00000015
_COMPLETION_TOKEN_COST = 0.0000006


class SlotDeltas(BaseModel):
    """Only fields the lead EXPLICITLY stated this turn are non-null."""
    trying_duration: Optional[str]
    age: Optional[int]
    treatment_path: Optional[Literal["natural", "iui", "ivf", "deciding"]]
    what_tried: Optional[str]
    done_testing: Optional[bool]
    diagnosis: Optional[Literal["none", "suspected", "confirmed"]]
    diagnosis_detail: Optional[str]
    priority_score: Optional[int]
    strong_readiness: Optional[bool]
    understands_role: Optional[bool]
    open_to_holistic: Optional[bool]
    financial_ready: Optional[bool]
    partner_status: Optional[Literal["couple", "solo", "donor", "single_by_choice"]]
    partner_is_decision_maker: Optional[bool]
    partner_can_join: Optional[bool]
    email_collected: Optional[str]
    tubes_blocked: Optional[Literal["none", "one", "both", "unspecified"]]
    no_period_reason: Optional[str]
    no_period_over_year: Optional[bool]
    ivf_interest: Optional[bool]


_INTENT_LITERAL = Literal[
    "shares_situation", "answers_question", "asks_price", "asks_advice",
    "asks_what_you_do", "asks_results_proof", "asks_phone", "asks_masterclass",
    "asks_is_it_sonia", "asks_call_process", "ready_to_book", "booked",
    "gives_email", "trouble_booking", "objection", "paying_twice",
    "blocked_tubes", "menopause_no_period", "ivf_only", "deaf",
    "is_this_ai", "angry_or_challenging", "distress", "not_ready_no_money",
    "other",
]


class Extraction(BaseModel):
    # Language of the lead's most recent message(s). "unclear" for short or
    # ambiguous turns so the controller keeps the sticky per-lead value.
    # FIRST on purpose: structured outputs generate fields in schema order, and
    # the raw-text language must be judged before the message is digested into
    # the (English) fields below. Placing it mid-schema destabilized the
    # takeover flag; placing it last misread French as Spanish.
    language: Literal["en", "es", "other", "unclear"]
    slot_deltas: SlotDeltas
    intent: _INTENT_LITERAL
    # For Phase-2 empathy variant selection.
    situation_type: Literal["hopeless", "neutral", "misfortune", "none"]
    # Hard out-of-scope signals the controller acts on.
    oos_signal: Literal[
        "none", "blocked_tubes", "menopause_no_period", "age_over_46", "deaf",
    ]
    # Soft human-takeover signal (angry, asks-if-AI, distress, etc.).
    takeover: bool
    takeover_reason: Optional[str]
    confidence: float


_SYSTEM = """You are a silent data-extraction component inside a fertility-coaching DM assistant. You DO NOT talk to the user. You read the conversation and output ONLY structured data matching the schema.

CARDINAL RULE: Only set a slot field if the LEAD explicitly stated it in their own words. If they did not state it, leave it null. NEVER infer, assume, guess, or carry over. When unsure, use null. It is always better to return null than to invent a value.

Field guidance:
- language: the language of the LEAD's MOST RECENT message(s) only. "en" when clearly English; "es" when clearly Spanish; "other" ONLY when the message is clearly in a language that is neither English nor Spanish (e.g. French, Portuguese, German, Italian - be careful, French and Portuguese are NOT Spanish, they are "other"). Use "unclear" for very short or ambiguous messages that could be any language: bare numbers, emojis, "ok", "yes", "si", "no", a name, or a lone keyword.
- slot_deltas: facts from the lead's MOST RECENT message(s), extracted the same way whatever language she writes in. Fields already listed under KNOWN SO FAR are context only; do not re-populate them unless the lead restated or changed them this turn.
  - trying_duration: how long they have been trying (their words, e.g. "2 years").
  - age: their age in years, only if a number is stated.
  - treatment_path: natural | iui | ivf | deciding — only if clearly indicated.
  - what_tried: what they have already tried (their words).
  - done_testing: true only if they say they have done fertility testing; false only if they say they have not.
  - diagnosis: none | suspected | confirmed. diagnosis_detail: the named condition if any.
  - priority_score: the 1-10 number ONLY if they give one in response to the priority question.
  - strong_readiness: true only if they clearly express strong commitment/readiness without a number.
  - understands_role: true when she affirms she wants this support, OR when she states in her own words that she understands this is coaching and not medical care (e.g. "I understand this is coaching, not medical care", "I know you're not a doctor").
  - open_to_holistic: true when she affirms she wants this support or that it is what she is looking for. This includes indirect yeses like "yes I need guidance", "that's exactly what I need", "I need someone to guide me", "yes I want help", or a simple "yes" / "yeah" right after being asked whether this is the kind of support she wants OR whether she has considered working with a fertility coach. Merely stating she understands what coaching is does NOT set open_to_holistic.
  - financial_ready: true ONLY when she explicitly affirms she is open to a PAID program / to investing / to the financial commitment - typically right after being told it is a paid program, or if she says she can afford it. Do NOT set it true from general enthusiasm about the coaching (e.g. "yes, count me in", "I'm ready", "sign me up") - that is about the coaching, not the money, and the financial question is a separate step. false when she clearly cannot afford it, declines, or wants only free help.
  - partner_status: couple | solo | donor | single_by_choice. If the lead says the decision is their partner's, or that they need to ask/consult their partner / husband / wife / spouse, set partner_status=couple. If she says she is doing this alone / on her own / by herself / single mom by choice / using donor sperm, set partner_status to solo (or single_by_choice / donor). A phrase like "no, doing this alone" is a SOLO answer, NOT a refusal to pay - do not classify it as not_ready_no_money.
  - partner_is_decision_maker: true if the lead indicates their partner makes or shares the decision (e.g. "I'll have to ask my partner", "it's my partner's decision"). false ONLY when she explicitly states she is the only decision maker / decides alone. NEVER infer false from the partner being unwilling or unable to join the call ("he doesn't want to join" says nothing about who decides). partner_can_join: only if stated.
  - email_collected: an email address if they provide one.
  - tubes_blocked: set ONLY from her explicit words. "both" requires an explicit count word like both / the two / ambas ("both my tubes are blocked" -> both). "one" when she says one tube. "unspecified" when she mentions blocked tubes WITHOUT saying whether it is one or both ("my tubes are blocked", "my doctor said my tubes are blocked" -> unspecified; the bot will ask which). "none" only if she says her tubes are clear/open.
  - no_period_reason: their stated reason for not menstruating, if discussing that.
  - no_period_over_year: true ONLY if she states she has not had a period for 12 months or more (e.g. "no period in 14 months", "over a year", "two years without a period"). null if the gap is shorter, unstated, or she just mentions irregular periods.
  - ivf_interest: true ONLY when she accepts the offer of IVF-preparation/optimization support (a yes AFTER being offered help alongside IVF). NEVER set it just because a doctor recommended IVF or said IVF is her only option - that is a fact about her treatment path, not an acceptance.
- intent: classify the LEAD's most recent message (one label). Use ivf_only when she says a doctor told her IVF is her only/best/last option or that she can only conceive through IVF (also set treatment_path="ivf"; do NOT set ivf_interest from this). Use not_ready_no_money when the lead clearly cannot afford it, has no money, has a very tight budget, wants only free help, or is not ready to commit at all. If she says her budget is tight / she can't afford it AND also asks the price in the same message, still classify it as not_ready_no_money (the affordability concern dominates). Do NOT use not_ready_no_money for "I need to ask/consult my partner" or "it's my partner's decision" - classify those as answers_question and set partner_status=couple and partner_is_decision_maker=true.
- situation_type (for empathy): "hopeless" for age worries, PCOS, tube issues, or feeling hopeless/broken; "misfortune" for miscarriage, loss, failed IVF/IUI, chemical pregnancy; "neutral" for sharing steps with a positive/neutral tone; "none" when there is no emotional content to acknowledge.
- oos_signal: "blocked_tubes" if they mention blocked tubes; "menopause_no_period" if menopausal or no period for a long time; "age_over_46" if their stated age is over 46; "deaf"; else "none".
- takeover: true if the lead is angry/challenging, asks whether this is AI/a bot, asks for medical advice that needs a diagnosis or treatment, expresses suicidal thoughts or severe distress, gives contradictory information, demands to speak to Sonia directly before qualifying, or asks for exceptions / special treatment / to bypass the process (e.g. "can you make an exception for me", "can you bend your rules", "can I skip the call/questions"). ALSO true if the lead is confused or frustrated with the conversation itself (e.g. "I already told you", "how do I tell you this", "you're not listening", "what do you mean") or the conversation is clearly going in circles. Put a short phrase in takeover_reason; otherwise null. NOTE: mild emotional venting such as "it's been hard", "I'm discouraged", "I'm exhausted", or "this is stressful" is NOT severe distress and NOT a takeover; classify it as answers_question with situation_type "hopeless", and leave priority_score null unless she actually gives a number.
- confidence: 0..1 confidence in the intent label."""


def _format_transcript(history: list[dict]) -> str:
    lines = []
    for m in history:
        role = m.get("role")
        who = "Lead" if role == "user" else "Sonia"
        lines.append(f"{who}: {m.get('content', '')}")
    return "\n".join(lines)


async def extract(
    openai_client: AsyncOpenAI,
    history: list[dict],
    current_slots: dict,
    *,
    model: str = _MODEL,
) -> tuple[Extraction, dict]:
    """Return (Extraction, usage). Raises if the model refuses or returns nothing."""
    known = {k: v for k, v in (current_slots or {}).items() if v is not None}
    transcript = _format_transcript(history[-8:])
    user_content = (
        f"KNOWN SO FAR (context only, do not re-extract):\n{json.dumps(known)}\n\n"
        f"CONVERSATION (most recent last):\n{transcript}\n\n"
        "Extract structured data from the LEAD's most recent message(s)."
    )

    completion = await openai_client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_format=Extraction,
        temperature=0,
    )

    msg = completion.choices[0].message
    if getattr(msg, "refusal", None):
        raise ValueError(f"Extractor refused: {msg.refusal}")
    result = msg.parsed
    if result is None:
        raise ValueError("Extractor returned no parsed output")

    usage = _usage(completion, model)
    return result, usage


def _usage(completion, model: str) -> dict:
    u = completion.usage
    prompt_tokens = getattr(u, "prompt_tokens", 0) or 0
    completion_tokens = getattr(u, "completion_tokens", 0) or 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_cost": prompt_tokens * _PROMPT_TOKEN_COST + completion_tokens * _COMPLETION_TOKEN_COST,
        "ai_model": model,
    }


def non_null_deltas(deltas: SlotDeltas) -> dict:
    """The subset of slot deltas the lead actually stated this turn."""
    return {k: v for k, v in deltas.model_dump().items() if v is not None}
