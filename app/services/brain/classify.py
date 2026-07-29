"""Classifier - LLM call #1. Reads the message; decides nothing.

Replaces `extractor.py`. Two things are new and both exist to fix specific
failures Sonia reported:

* `intent` is now about WHY she is messaging, so a pregnancy announcement, a
  thank-you, and "I've decided to stop trying" can be routed away from the sales
  funnel instead of into it.
* `question_asked` carries her literal question forward, so downstream code can
  check that the reply actually answered it rather than deflecting to discovery.

Every fact must come with a verbatim `quote`, and `verify_evidence` checks in code
that the quote really appears in her message. A model that cannot quote cannot
claim - which is a stronger guarantee than the "CARDINAL RULE" instruction the old
extractor relied on, and it is what lets the hand-written over-inference patches go.
"""
import json
import logging
import re
from typing import Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.services.brain.constants import LeadIntent
from app.services.brain.llm import model_for, usage_of, with_retry

logger = logging.getLogger(__name__)


class SlotDeltas(BaseModel):
    """Only fields the lead EXPLICITLY stated this turn are non-null.

    Owned here rather than imported from `extractor.py` so that module can be
    deleted outright once the funnel brain is retired. `test_classify_schema`
    guards every field against SLOT_KEYS.
    """
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


# Discrete, defined buckets rather than a 0..1 float. gpt-4o-mini returns ~0.9
# for everything, including a contentless "ok" - the float carries no signal.
# Labelled categories with explicit definitions it can actually apply do.
Certainty = Literal["certain", "probable", "unsure"]


class Evidence(BaseModel):
    """The lead's own words backing one extracted fact."""
    slot: str
    quote: str
    certainty: Certainty


_INTENT_LITERAL = Literal[
    # Not a sales conversation
    "pregnancy_or_success", "gratitude", "grief_or_stopped_trying",
    "existing_client", "collaboration_or_technical",
    # She asked something
    "general_fertility_question", "asks_free_advice", "asks_about_program",
    "asks_results_proof", "asks_masterclass",
    # Objections
    "objection_price", "objection_partner", "objection_trust",
    "objection_fear_after_failure", "objection_paying_twice",
    # Qualification path
    "new_prospect", "answers_question", "warm_high_intent",
    "not_a_fit_signal", "ivf_only",
    # Post-booking
    "booked", "gives_email", "trouble_booking",
    # Escalate
    "is_this_ai", "angry_or_challenging", "distress",
    "other",
]


class Classification(BaseModel):
    # Language FIRST on purpose: structured outputs generate fields in schema
    # order, and the raw text must be judged before the message is digested into
    # the English fields below. Mid-schema destabilized the takeover flag; last
    # misread French as Spanish. Do not move it.
    language: Literal["en", "es", "other", "unclear"]

    # Why she is messaging. The routing decision depends on this above all else.
    intent: _INTENT_LITERAL
    intent_certainty: Certainty
    # A message can genuinely do two things ("congrats!" + a real question).
    secondary_intent: Optional[_INTENT_LITERAL]

    # Her literal question, copied word for word, so we can check we answered it.
    question_asked: Optional[str]

    slot_deltas: SlotDeltas
    # One entry per slot set this turn, quoting her own words.
    evidence: list[Evidence]

    # How much of her fertility situation is now on the table. "rich" ends
    # discovery outright, regardless of which named slots happen to be filled.
    situation_richness: Literal["none", "partial", "rich"]

    # For empathy variant selection (unchanged semantics).
    situation_type: Literal["hopeless", "neutral", "misfortune", "none"]
    # Hard out-of-scope signals; gates.oos_check consumes this.
    oos_signal: Literal[
        "none", "blocked_tubes", "menopause_no_period", "age_over_46", "deaf",
    ]

    # The message contains something the funnel has no answer for.
    off_script: bool
    takeover: bool
    takeover_reason: Optional[str]


_SYSTEM = """You are a silent classification component inside a fertility-coaching DM assistant. You DO NOT talk to the user. You read the conversation and output ONLY structured data matching the schema.

CARDINAL RULE: only record a fact the LEAD explicitly stated in her own words, and quote those words. If you cannot quote her saying it, leave the field null. NEVER infer, assume, guess, or carry over. Null is always better than a guess.

## intent - WHY she is messaging. This is the most important field; the whole reply depends on it.

FIRST, read Sonia's previous turn in the transcript. A short message resolves against the question it follows: "yes", "no", "ok", "sure", "si", "maybe", or a bare number immediately after Sonia asked something is answers_question, and it is CERTAIN, not unsure. Only treat a short message as unsure when there is no preceding question it could be answering.

Not a sales conversation (these must never be qualified):
- pregnancy_or_success: she is pregnant, has given birth, or shares good news / a success story.
- gratitude: she is thanking you or praising your content, with no question and no request.
- grief_or_stopped_trying: she has decided to stop trying, is done, or is expressing deep grief or exhaustion about ending the journey. NOT ordinary venting about how hard it is.
- existing_client: she is already enrolled in the program or references being a client.
- collaboration_or_technical: a business, press, podcast, affiliate or technical/account matter.

She asked something:
- asks_free_advice: she asks what SHE specifically should take, do, or follow - a supplement, a dose, a protocol, a diet, a plan. Check this one FIRST: a request for a personal recommendation is asks_free_advice even though it is also a fertility question. "What supplements should I take for low AMH?" is asks_free_advice, not general_fertility_question.
- general_fertility_question: a real question about fertility, her body, or whether something could help, that is NOT a request for a personal recommendation (e.g. "can anything realistically make a difference in the 6 weeks before IVF?", "does stress actually affect egg quality?").
- asks_about_program: what you do, what the call is like, who runs it, your phone number, how it works.
- asks_results_proof: does it work, do you have testimonials, success rates.
- asks_masterclass: she asks for the masterclass, the free training, or a replay.

Objections - these are four different conversations, do not collapse them:
- objection_price: cost, affordability, budget, "how much", "too expensive", cannot afford.
- objection_partner: her partner is hesitant, unconvinced, does not believe in coaching, or must approve.
- objection_trust: scepticism about you, your credentials, or whether coaching is legitimate.
- objection_fear_after_failure: fear, exhaustion or hopelessness specifically after failed IVF/IUI cycles or losses.
- objection_paying_twice: she is already paying a clinic or another practitioner.

Qualification path:
- new_prospect: a first message opening a fertility conversation with no question attached.
- answers_question: she is responding to something Sonia asked. This is the DEFAULT whenever her message follows a question from Sonia and no more specific label above clearly applies. It covers bare answers - a number, an age, a date, "yes", "no", "not yet", "still deciding". Prefer this over "other" every time there is a question in front of it.
- warm_high_intent: she actively asks to move forward - asks for the link, asks how to start or sign up, or says she wants to book a call. Simply AGREEING with something Sonia asked ("yes", "that's exactly what I need", "sounds good") is answers_question, NOT warm_high_intent. She has to reach for the next step herself.
- not_a_fit_signal: SHE says she is probably not right for this - "I don't think I need this yet", "I'm probably too early for something like this". Do NOT judge her fitness yourself from her age or how long she has been trying; that assessment is made in code from the facts you extract. Only use this label when she raises it herself.
- ivf_only: a doctor told her IVF is her only or best option, or she can only conceive via IVF.

After booking:
- booked: she says she HAS scheduled the call, any phrasing or tense ("booked!", "all set for Thursday", "ya agende").
- gives_email: the message is or contains her email address.
- trouble_booking: she tried to book and something went wrong.

Straight to a human:
- is_this_ai: she asks whether this is a bot or automated.
- angry_or_challenging: hostile, accusatory, or challenging you.
- distress: severe distress or any mention of self-harm.

- other: none of the above.

If a message does two things, put the dominant purpose in intent and the other in secondary_intent. A congratulation plus a question is pregnancy_or_success + general_fertility_question.

## intent_certainty - be strict with yourself here
- certain: the message says plainly why she is writing.
- probable: the label fits, but a reasonable person could pick another.
- unsure: you genuinely cannot tell. Use this when the message carries no purpose of its own AND nothing in the transcript resolves it - a bare "ok", "hmm", a lone emoji, a single word or a name arriving with no question in front of it. If Sonia asked a question on the previous turn, the message is an answer and you are NOT unsure.
An "unsure" reading routes the conversation to a human. That is the correct outcome when you cannot tell, so never mark unsure just to be safe on a clear message, and never claim certain to look decisive.

## evidence certainty
Same three labels, for how sure you are that the quote really establishes the fact.

## question_asked
If she asked a question, copy it VERBATIM. Otherwise null. Do not paraphrase, do not invent a question she did not ask.

## situation_richness
- rich: she has described her fertility situation with real substance - several treatments or interventions named, or a clear history. Someone who says "4 failed IVF cycles, changed my diet, took supplements, worked with three practitioners" is rich. Asking her what else she has tried would be insulting.
- partial: some detail, but her situation is still mostly unknown.
- none: nothing about her situation yet.

## slot_deltas + evidence
For every slot you set, add ONE evidence entry: the slot name, a VERBATIM quote from her message containing that fact, and your certainty. Copy the quote exactly - it is checked against her real message and a fact whose quote does not appear is discarded.
- trying_duration: how long they have been trying, her words.
- age: age in years, only if a number is stated.
- treatment_path: natural | iui | ivf | deciding, only if clearly indicated.
- what_tried: what she has already tried, her words.
- done_testing: true only if she says she has done fertility testing; false only if she says she has not.
- diagnosis: none | suspected | confirmed. diagnosis_detail: the named condition.
- priority_score: the 1-10 number ONLY if she gives one in response to the priority question.
- strong_readiness: true when she shows clear commitment WITHOUT a number. An active, dated treatment plan counts ("preparing for IVF in September", "starting my next cycle in March") - a woman with a concrete plan has already answered how much of a priority this is.
- understands_role: true when she affirms she wants this support, or states she understands this is coaching, not medical care.
- open_to_holistic: true when she affirms she wants this support. IMPORTANT: if Sonia's previous turn asked whether this is the kind of support she is looking for, or whether she has considered working with a fertility coach, then ANY affirmative reply sets this true - including a bare "yes", "yeah", "si", "definitely", "that's exactly what I need", "yes I need guidance". Quote her affirmative word as the evidence. Merely understanding what coaching is does NOT set it.
- financial_ready: true ONLY on explicit openness to a PAID program, typically right after being told it is paid. General enthusiasm ("count me in", "I'm ready") is about the coaching, not the money - do NOT set it. false when she clearly cannot afford it or wants only free help.
- partner_status: couple | solo | donor | single_by_choice. "I'll ask my partner" -> couple. "doing this alone" -> solo, and that is a SOLO answer, never a money refusal.
- partner_is_decision_maker: about the PARTNER, not her. true when he decides or must agree. false when she states SHE alone decides. NEVER infer it from him being unable or unwilling to join a call -> null.
- partner_can_join: only if stated.
- email_collected: an email address if she gives one.
- tubes_blocked: from her explicit words only. "both" needs an explicit count word ("both my tubes"). "one" for one tube. "unspecified" when she mentions blocked tubes without saying how many. "none" only if she says they are clear.
- no_period_reason: her stated reason for not menstruating.
- no_period_over_year: true ONLY if she states 12 months or more without a period.
- ivf_interest: true ONLY when she accepts an offer of IVF-preparation support. NEVER from a doctor recommending IVF.

## language
The LEAD's most recent message(s) only. "en" clearly English; "es" clearly Spanish; "other" ONLY when clearly neither (French, Portuguese, German and Italian are "other", NOT Spanish); "unclear" for bare numbers, emojis, "ok", "yes", "si", a name, or a lone keyword.

## situation_type
"hopeless" for age worries, PCOS, tube issues, or feeling hopeless/broken; "misfortune" for miscarriage, loss, failed IVF/IUI; "neutral" for sharing steps with a positive or neutral tone; "none" when there is no emotional content.

## oos_signal
"blocked_tubes" if she mentions blocked tubes; "menopause_no_period" if menopausal or a long absence of periods; "age_over_46" if her stated age is over 46; "deaf"; else "none".

## off_script
true when the message contains something this fertility-qualification flow has no sensible answer for - an unrelated topic, an unusual request, or a situation none of the intents above really fits. It routes to a human rather than to a guess.

## takeover
true if she asks for medical advice needing a diagnosis, gives contradictory information, demands to speak to Sonia directly before qualifying, asks to skip the process or for an exception, or is confused or frustrated with the conversation itself ("I already told you", "you're not listening"). Put a short phrase in takeover_reason, else null.
NOTE: mild venting ("it's been hard", "I'm discouraged", "I'm exhausted", "this is stressful") is NOT distress and NOT takeover. Classify it as answers_question with situation_type "hopeless" and leave priority_score null."""


def _format_transcript(history: list[dict]) -> str:
    lines = []
    for m in history:
        who = "Lead" if m.get("role") == "user" else "Sonia"
        lines.append(f"{who}: {m.get('content', '')}")
    return "\n".join(lines)


_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Fold whitespace and case so a quote matches despite formatting drift."""
    return _WS_RE.sub(" ", (text or "")).strip().casefold()


def verify_evidence(
    classification: Classification, lead_texts: list[str]
) -> tuple[dict, list[str]]:
    """Keep only the facts whose quote really appears in what she wrote.

    Returns `(verified_deltas, rejected_slots)`. A model that fabricates or
    paraphrases a quote loses the fact - which is the whole point of asking for
    one. Slots with no evidence entry at all are also dropped: if it were really
    stated, there would be something to quote.
    """
    haystack = _norm(" ".join(lead_texts))
    quoted: dict[str, str] = {}
    for ev in classification.evidence:
        if not _norm(ev.quote) or _norm(ev.quote) not in haystack:
            logger.info("Unverifiable evidence for %s: %r", ev.slot, ev.quote)
            continue
        if ev.certainty == "unsure":
            # She may have said it, but the model would not stand behind it.
            # A doubtful fact must not silently gate a booking.
            logger.info("Discarding unsure evidence for %s: %r", ev.slot, ev.quote)
            continue
        quoted[ev.slot] = ev.certainty

    verified, rejected = {}, []
    for slot, value in classification.slot_deltas.model_dump().items():
        if value is None:
            continue
        if slot in quoted:
            verified[slot] = value
        else:
            rejected.append(slot)
    if rejected:
        logger.info("Dropped unevidenced slots: %s", rejected)
    return verified, rejected


async def classify(
    openai_client: AsyncOpenAI,
    history: list[dict],
    current_slots: dict,
    *,
    cfg: Optional[dict] = None,
    model: Optional[str] = None,
) -> tuple[Classification, dict]:
    """Return (Classification, usage). Raises if the model refuses or returns nothing."""
    model = model or model_for("classifier", cfg)
    known = {k: v for k, v in (current_slots or {}).items() if v is not None}
    transcript = _format_transcript(history[-8:])
    user_content = (
        f"KNOWN SO FAR (context only, do not re-extract):\n{json.dumps(known)}\n\n"
        f"CONVERSATION (most recent last):\n{transcript}\n\n"
        "Classify the LEAD's most recent message(s)."
    )

    async def _call():
        return await openai_client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_content},
            ],
            response_format=Classification,
            temperature=0,
        )

    completion = await with_retry(_call, what="classifier")

    msg = completion.choices[0].message
    if getattr(msg, "refusal", None):
        raise ValueError(f"Classifier refused: {msg.refusal}")
    result = msg.parsed
    if result is None:
        raise ValueError("Classifier returned no parsed output")

    return result, usage_of(completion, model, "classifier")
