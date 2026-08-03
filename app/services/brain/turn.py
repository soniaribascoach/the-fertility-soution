"""The v2 turn: classify, route, retrieve, write, check.

Same entry-point contract as the funnel brain's `run_turn` - three callers and
five test modules depend on the signature and on `TurnResult` - so this can be
swapped in behind the `brain_version` flag with no changes upstream.

    0. safety gate        no LLM   (reused unchanged from the funnel brain)
    1. phase-1 CTA        no LLM   (reused unchanged)
    2. classify           LLM #1
    3. route              no LLM   <- QUALIFY is one mode among nine
    4. retrieve knowledge no LLM
    5. write              LLM #2
    6. code checks        no LLM
    7. veto panel         LLM #3   (conditional)
    8. uncertainty        no LLM   -> a person, if anything is off
"""
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.services.brain import checker, checks, scripts, uncertainty, writer
from app.services.brain import playbooks as pb
from app.services.brain import knowledge as kb
from app.services.brain.classify import classify, verify_evidence, verify_question
from app.services.brain.constants import (
    Action,
    Phase,
    ResponseMode,
    normalize_lead_state,
)
from app.services.brain.gates import booking_gate
from app.services.brain.llm import combine_usage
from app.services.brain.router import route
from app.services.brain import TurnResult, _check_phase1, _safety_gate, _trailing_user_texts

logger = logging.getLogger(__name__)

# Slots whose value, once established, must not be silently overwritten by a
# later contradictory reading. "She said 2 years, now she says 6 months" is a
# person's job, not a state update.
_STABLE_SLOTS = ("age", "trying_duration", "partner_status", "email_collected")


def merge_facts(state: dict, verified: dict) -> list[str]:
    """Apply verified facts; return the slots that contradicted what we knew."""
    contradictions = []
    for slot, value in verified.items():
        if slot not in state["slots"]:
            continue
        current = state["slots"].get(slot)
        if slot in _STABLE_SLOTS and current not in (None, "") and current != value:
            contradictions.append(slot)
            continue
        state["slots"][slot] = value

    s = state["slots"]
    if s.get("partner_status") is None and (
        s.get("partner_can_join") is not None
        or s.get("partner_is_decision_maker") is not None
    ):
        s["partner_status"] = "couple"
    if s.get("trying_duration") or s.get("what_tried") or s.get("treatment_path"):
        state["flags"]["situation_shared"] = True
    return contradictions


def _still_needed(state: dict) -> list[str]:
    from app.services.brain import gates
    s = state["slots"]
    needed = []
    if not gates._discovery_complete(s) and state["flags"].get("situation_rich") is not True:
        needed.append("her situation (how long trying, age, what she has tried)")
    if not gates._priority_ok(s):
        needed.append("how much of a priority pregnancy is right now")
    if not gates._role_ok(state):
        needed.append("that she wants this kind of support")
    if not gates._financial_ok(s):
        needed.append("that she is open to a paid programme")
    if not gates._partner_resolved(s):
        needed.append("whether a partner is involved")
    return needed


_DISCOVERY_ORDER = ["trying_duration", "age", "treatment_path", "done_testing", "diagnosis"]


_ASKED_MARKERS = {
    "how long she has been trying, and what she has already tried":
        ("how long have you been trying", "how long you have been trying",
         "cuanto tiempo llevan intentando"),
    "her age": ("how old are you", "cuantos anos tienes"),
    "whether she is trying naturally, doing IUI or IVF, or still deciding":
        ("trying naturally", "iui", "still deciding"),
    "whether she has had any fertility testing": ("fertility testing", "any testing"),
    "whether a doctor has given her a diagnosis": ("diagnosis",),
    "how much of a priority getting pregnant is for her right now":
        ("scale of 1 to 10", "top priority"),
    "whether this is the kind of support she is looking for":
        ("kind of support", "looking for"),
    "whether she is open to this being a paid programme, if it feels right":
        ("paid program", "paid coaching"),
    "whether she is doing this with a partner or on her own":
        ("with a partner", "on your own"),
    "whether her partner could join the call": ("join the call",),
}


def already_asked(question: Optional[str], history: list[dict]) -> bool:
    """Has this topic already been put to her?

    The phase-1 opener asks about duration and what she has tried, so a lead who
    answers it partially sends us straight back to the same question. It still
    needs asking - but the writer has to reword it, or the repeat check rejects
    the reply and she gets silence instead.
    """
    if not question:
        return False
    markers = _ASKED_MARKERS.get(question)
    if not markers:
        return False
    said = " ".join(m.get("content", "") for m in history
                    if m.get("role") == "assistant").casefold()
    return any(marker in said for marker in markers)


def _next_question(state: dict) -> Optional[str]:
    """The one thing to ask on a QUALIFY turn, as a topic rather than a script.

    Handing over the approved sentence is what made every discovery message
    identical, so the writer gets the subject and phrases it itself.
    """
    from app.services.brain import gates
    s = state["slots"]
    if not gates._discovery_complete(s) and not state["flags"].get("situation_rich"):
        missing = next((k for k in _DISCOVERY_ORDER if not s.get(k)), "trying_duration")
        return {
            "trying_duration": "how long she has been trying, and what she has already tried",
            "age": "her age",
            "treatment_path": "whether she is trying naturally, doing IUI or IVF, or still deciding",
            "done_testing": "whether she has had any fertility testing",
            "diagnosis": "whether a doctor has given her a diagnosis",
        }[missing]
    if not gates._priority_ok(s):
        return "how much of a priority getting pregnant is for her right now"
    if not gates._role_ok(state):
        state["flags"]["explained_role"] = True
        return "whether this is the kind of support she is looking for"
    if not gates._financial_ok(s):
        return "whether she is open to this being a paid programme, if it feels right"
    if not gates._partner_resolved(s):
        if s.get("partner_status") is None:
            return "whether she is doing this with a partner or on her own"
        return "whether her partner could join the call"
    return None


async def run_turn_v2(
    openai_client: AsyncOpenAI,
    history: list[dict],
    cfg: dict,
    lead_state: Optional[dict] = None,
    *,
    ig_user_id: str = "",
    new_texts: Optional[list[str]] = None,
    knowledge_entries: Optional[list] = None,
    playbook_entries: Optional[list] = None,
    recent_openings: Optional[list[str]] = None,
) -> TurnResult:
    state = normalize_lead_state(lead_state)
    recent = list(new_texts) if new_texts is not None else _trailing_user_texts(history)

    # 0) Safety gate, unchanged. Scans only the new batch so a resumed lead does
    # not re-trip on a message a human already handled.
    gated = _safety_gate(cfg, recent, state)
    if gated is not None:
        return gated

    # 1) Phase-1 CTA keyword, unchanged.
    opener = _check_phase1(cfg, history)
    if opener:
        state["phase"] = Phase.DISCOVERY.value
        return TurnResult(reply_text=opener, lead_state=state,
                          action=Action.PHASE1_OPENING.value)

    if not recent:
        return TurnResult(reply_text=None, lead_state=state, action="NOOP")

    # 2) Classify.
    classification, usage_classify = await classify(
        openai_client, history, state["slots"], cfg=cfg
    )
    evidence = verify_evidence(classification, recent)
    # Drop a question the model paraphrased or invented from a statement: a
    # phantom question makes the `answered` judge veto a perfectly good reply.
    classification.question_asked = verify_question(classification, recent)
    contradictions = merge_facts(state, evidence.verified)
    if classification.situation_richness == "rich":
        # Complaint 2: a woman who has described four IVF cycles and years of
        # interventions has finished discovery, whatever named slots are empty.
        state["flags"]["situation_rich"] = True

    gate_before = booking_gate(state)

    # 3) Route.
    r = route(state, classification, cfg)
    state = r.lead_state
    mode = r.mode

    if contradictions:
        logger.info("Contradiction on %s for %s", contradictions, ig_user_id)

    def trace(**extra) -> dict:
        """The turn's reasoning, for `brain_turns` and the shadow diff."""
        base = {
            "intent": classification.intent,
            "intent_certainty": classification.intent_certainty,
            "secondary_intent": classification.secondary_intent,
            "stage": r.stage.value,
            "mode": mode.value,
            "reason": r.reason,
            "question_asked": r.question_asked,
            "situation_richness": classification.situation_richness,
            "off_script": classification.off_script,
            "fabricated_slots": evidence.fabricated,
            "unevidenced_slots": evidence.unevidenced,
            "contradictions": contradictions,
        }
        base.update(extra)
        return base

    # A handoff says nothing, except where an approved decline is pinned.
    if mode is ResponseMode.HANDOFF:
        text = None
        if r.pinned_action is not None:
            text = scripts.render(r.pinned_action, cfg, state["slots"].get("language") or "en")
        return TurnResult(
            reply_text=text, lead_state=state, pause=r.pause, pause_reason=r.pause_reason,
            add_tag=r.add_tag, qualified=r.qualified, action=r.mode.value,
            usage=usage_classify, trace=trace(),
        )

    # Post-booking turns keep their approved wording verbatim.
    if r.funnel_action in (Action.POST_BOOKING_ASK_EMAIL, Action.POST_BOOKING_ACK):
        text = scripts.render(r.funnel_action, cfg, state["slots"].get("language") or "en")
        return TurnResult(
            reply_text=text, lead_state=state, pause=r.pause, pause_reason=r.pause_reason,
            add_tag=r.add_tag, qualified=r.qualified, action=r.funnel_action.value,
            usage=usage_classify, trace=trace(),
        )

    # 4) Retrieve the substance this turn is allowed to use.
    language = state["slots"].get("language") or "en"
    entries = knowledge_entries if knowledge_entries is not None else []
    retrieved = kb.select(
        entries, mode=mode, intent=r.intent, text=" ".join(recent), language=language
    )
    knowledge_texts = [e.content for e in retrieved]

    # The playbook for this exact situation. None is a normal outcome: the mode
    # contract alone is a complete instruction, and a wrong playbook is worse
    # than no playbook.
    playbook = pb.select(
        playbook_entries or [], mode=mode, intent=r.intent, stage=r.stage,
        text=" ".join(recent), language=language,
    )

    spec = writer.MODE_SPECS[mode]
    allow_urls = writer.allowed_urls(spec, cfg)
    known_facts = {k: v for k, v in state["slots"].items()
                   if v is not None and k not in ("language", "closer_assigned")}

    next_q = _next_question(state) if mode is ResponseMode.QUALIFY else None
    winput = writer.WriterInput(
        mode=mode, known_facts=known_facts, knowledge=retrieved,
        question_asked=r.question_asked, still_needed=_still_needed(state),
        next_question=next_q, already_asked=already_asked(next_q, history),
        language=language, stance=writer.stance_for(history), allow_urls=allow_urls,
        playbook=playbook, ig_user_id=ig_user_id,
        max_chars=writer.energy_max_chars(spec, recent),
    )

    # 5) Write, 6) check, regenerate once at temperature 0 if the code checks fail.
    draft, usage_write = await writer.generate(openai_client, history, winput, cfg=cfg)
    result = checks.run_all(
        draft.bubbles, mode=mode, allow_urls=allow_urls, allow_price=False,
        history=history, lead_texts=recent, knowledge_texts=knowledge_texts,
        known_facts=known_facts, recent_openings=recent_openings,
        language=language,
    )
    regenerated = False
    if not result.ok:
        logger.info("Draft failed checks %s; regenerating", result.violations)
        regenerated = True
        draft2, usage_write2 = await writer.generate(
            openai_client, history, winput, cfg=cfg, temperature=0.0
        )
        usage_write = combine_usage(usage_write, usage_write2)
        result2 = checks.run_all(
            draft2.bubbles, mode=mode, allow_urls=allow_urls, allow_price=False,
            history=history, lead_texts=recent, knowledge_texts=knowledge_texts,
            known_facts=known_facts, recent_openings=recent_openings,
            language=language,
        )
        # Keep whichever attempt is safer, so the violations we report always
        # describe the text we are holding. If the retry traded a soft problem
        # for a hard one, the first draft was better.
        if not result2.hard or result.hard:
            draft, result = draft2, result2

    # 7) Veto panel, only when something already looks off.
    checker_violations, usage_check = [], {}
    if uncertainty.should_check(
        intent_certainty=classification.intent_certainty,
        off_script=classification.off_script, writer_unsure=draft.unsure,
        code_violations=result.violations,
        gate_just_opened=(mode is ResponseMode.BOOK),
        question_asked=r.question_asked,
    ):
        checker_violations, usage_check = await checker.check(
            openai_client, draft.bubbles, history=history, known_facts=known_facts,
            knowledge_texts=knowledge_texts, question_asked=r.question_asked,
            gate_passed=gate_before, cfg=cfg,
        )

    # 8) One score, one threshold.
    u = uncertainty.score_turn(
        intent_certainty=classification.intent_certainty,
        off_script=classification.off_script, fabricated_slots=evidence.fabricated,
        contradictions=contradictions, writer_unsure=draft.unsure,
        code_violations=result.violations, checker_violations=checker_violations,
        # Only a HARD violation surviving both attempts justifies silence. A
        # reply that merely repeats a question or keeps an em-dash is worth far
        # more to the lead than nothing at all.
        regenerated=regenerated, still_failing=bool(result.hard),
        repeat_count=state["counters"].get("repeat_count", 0),
    )
    usage = combine_usage(usage_classify, usage_write, usage_check)
    violations = result.violations + checker_violations + [f"uncertainty={u.score}"]
    turn_trace = trace(
        knowledge_ids=[e.id for e in retrieved if e.id is not None],
        knowledge_topics=[e.topic for e in retrieved],
        playbook=playbook.slug if playbook else None,
        max_chars=winput.max_chars,
        stance=winput.stance,
        bubbles=draft.bubbles,
        writer_unsure=draft.unsure,
        writer_unsure_reason=draft.unsure_reason,
        regenerated=regenerated,
        code_violations=result.violations,
        checker_violations=checker_violations,
        uncertainty_score=u.score,
        uncertainty_signals=u.signals,
        threshold=uncertainty.threshold_from(cfg),
    )

    if u.over(uncertainty.threshold_from(cfg)):
        # Say nothing rather than send something we do not trust.
        logger.info("Uncertainty %s (%s) -> human for %s", u.score, u.signals, ig_user_id)
        state["phase"] = Phase.TAKEOVER.value
        state["flags"]["takeover_reason"] = "uncertain"
        if mode is ResponseMode.BOOK:
            state["flags"]["booking_sent"] = False  # the link never went out
        return TurnResult(
            reply_text=None, lead_state=state, pause=True, pause_reason="uncertain",
            add_tag=True, action=f"{mode.value}_ABORTED", usage=usage,
            violations=violations + u.signals,
            # The suppressed draft is kept in the trace: an aborted turn is the
            # most useful thing to review, and it is invisible otherwise.
            trace=dict(turn_trace, aborted=True, suppressed_reply="\n\n".join(draft.bubbles)),
        )

    return TurnResult(
        reply_text="\n\n".join(draft.bubbles), lead_state=state, pause=r.pause,
        pause_reason=r.pause_reason, add_tag=r.add_tag, qualified=r.qualified,
        action=mode.value, usage=usage, violations=violations, trace=turn_trace,
    )
