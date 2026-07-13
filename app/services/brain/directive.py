"""TurnDirective — the contract between the deterministic Director and the Voice.

The controller (`decide`) still makes every hard decision (what to do next, when
booking/price is allowed, OOS/takeover). `build_directive` translates that single
Decision into a rich instruction the generative Voice can act on: the objective,
the facts to acknowledge, the agenda still to cover, the approved language as
guidance, and the hard permissions/requirements the validator will enforce.

"Pin only the sensitive language": out-of-scope declines are emitted verbatim
(generate=False); everything else is generated but constrained (allowed URLs,
price-figure gating, required substrings like the not-a-doctor disclaimer).
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.brain.constants import Action
from app.services.brain import scripts
from app.services.brain import controller as ctrl


@dataclass
class TurnDirective:
    mode: str
    action: Action                 # underlying deterministic action (also the fallback)
    generate: bool                 # True -> Voice writes it; False -> emit pinned verbatim
    objective: str                 # short instruction for the Voice
    reference_text: str            # approved language (guidance + verbatim fallback)
    known_facts: dict = field(default_factory=dict)
    still_needed: list = field(default_factory=list)
    must_include: list = field(default_factory=list)   # exact substrings required in output
    allow_urls: list = field(default_factory=list)     # URLs permitted this turn
    allow_price_figure: bool = False
    max_chars: int = 400               # length budget for the generated message
    pinned_text: Optional[str] = None  # exact text for non-generated modes (OOS)
    language: str = "en"               # en | es — the lead's sticky language
    # side effects (passthrough from the Decision)
    send_message: bool = True
    pause: bool = False
    pause_reason: Optional[str] = None
    add_tag: bool = False
    qualified: bool = False
    lead_state: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _ModeSpec:
    mode: str
    objective: str
    generate: bool = True
    url_names: tuple = ()          # placeholder names whose URLs are allowed/required
    require_urls: bool = False     # the allowed URLs must actually appear
    price: bool = False            # price figure allowed (and required)
    disclaimer: bool = False       # the not-a-doctor disclaimer must appear


_DISCLAIMER_KEY = "not a doctor"
_DISCLAIMER_KEY_ES = "no soy doctora"  # exact phrase in the ES EXPLAIN_ROLE script

# Per-action generation spec. Anything not listed uses a safe generic default.
_SPEC = {
    Action.ASK_DISCOVERY: _ModeSpec("DISCOVERY", "Acknowledge what she just shared, then ask the one discovery question you are given."),
    Action.ASK_BOTH_TUBES: _ModeSpec("DISCOVERY", "Gently ask whether both tubes are blocked or only one."),
    Action.ONE_TUBE_ACK: _ModeSpec("DISCOVERY", "Acknowledge that one blocked tube is different from both being blocked, then ask whether she is trying naturally, doing IUI, considering IVF, or still deciding."),
    Action.ASK_MENOPAUSE_REASON: _ModeSpec("DISCOVERY", "Gently ask the reason she is no longer getting her period."),
    Action.ASK_MENOPAUSE_AGE: _ModeSpec("DISCOVERY", "Gently ask her age."),

    Action.ASK_PRIORITY: _ModeSpec("QUALIFY_PRIORITY", "Ask, on a scale of 1 to 10, how much of a priority getting pregnant is right now."),
    Action.PRIORITY_NOT_UNDERSTOOD: _ModeSpec("QUALIFY_PRIORITY", "Reassure with your experience and ask if she is ready to fully commit."),
    Action.REENGAGE_LOW_PRIORITY: _ModeSpec("QUALIFY_PRIORITY", "Warmly re-engage: your approach works for committed clients; ask if she is ready to dedicate herself."),
    Action.LOW_PRIORITY_INFO_GATHERING: _ModeSpec("QUALIFY_PRIORITY", "Ask whether she is ready to focus on this now or is more in the information-gathering stage."),
    Action.NURTURE_CLOSE: _ModeSpec("FINANCIAL", "Warmly and briefly thank her for her honesty, suggest starting with the free masterclass for now, and let her know you're here when she's ready. Do not ask a question.", url_names=("register_link",), require_urls=True),

    Action.EXPLAIN_ROLE: _ModeSpec("EXPLAIN_ROLE", "Answer plainly what a fertility coach does, clarify you're not a doctor or clinic, and ask if that's the support she's looking for (see the substance guidance).", disclaimer=True),
    Action.EXPLAIN_ROLE_CONFIRM: _ModeSpec("EXPLAIN_ROLE", "Ask if that is the kind of support she is looking for."),
    Action.EXPLAIN_ROLE_TFS_UPDATED: _ModeSpec("EXPLAIN_ROLE", "Describe how you help women conceive naturally and ask if she is interested."),
    Action.EXPLAIN_ROLE_TFS1: _ModeSpec("EXPLAIN_ROLE", "Briefly describe that you help women conceive naturally and ask if she is interested."),
    Action.EXPLAIN_ROLE_TFS2: _ModeSpec("EXPLAIN_ROLE", "Describe your holistic, multi-approach method."),
    Action.EXPLAIN_ROLE_TFS3: _ModeSpec("EXPLAIN_ROLE", "Share that you have a strong track record and point her to your testimonials and masterclass.", url_names=("website", "ig_highlights", "watch_replay")),

    Action.FINANCIAL_CHECK: _ModeSpec("FINANCIAL", "Gently note it is a paid program and ask if she is open to that if it feels aligned."),
    Action.FINANCIAL_DECLINE: _ModeSpec("FINANCIAL", "Warmly suggest starting with the free masterclass for now.", url_names=("register_link",), require_urls=True),
    Action.NO_MONEY: _ModeSpec("FINANCIAL", "Warmly point her to the free masterclass as the best place to start right now, and include the link. Do NOT ask a question or invite her to keep chatting.", url_names=("register_link",), require_urls=True),

    Action.PARTNER_CHECK: _ModeSpec("PARTNER", "Note fertility is a team decision and ask if she is doing this with a partner or on her own."),
    Action.PARTNER_ASK_JOIN: _ModeSpec("PARTNER", "Ask whether her partner would be able to join the call."),
    Action.SOLO_NO_PARTNER_ACK: _ModeSpec("DISCOVERY", "Reassure her that since she is doing this on her own she would not need a partner on the call, then ask her current stage (trying naturally, IUI, preparing for IVF, or still deciding)."),
    Action.PARTNER_PUSHBACK: _ModeSpec("PARTNER", "Reassure her she can come alone IF she is the only decision maker, then ask directly whether she alone decides or her partner needs to be aligned too. Do not send or promise the booking link."),

    Action.SEND_BOOKING: _ModeSpec("BOOK", "Invite her to book the call and include the booking link; tell her to follow the next steps after booking so the call gets confirmed. Do NOT ask for her email.", url_names=("booking_link",), require_urls=True),
    Action.SEND_BOOKING_TOGETHER: _ModeSpec("BOOK", "Her partner shares the decision but cannot join. Warmly explain that you always encourage couples to attend the strategy call together because the strongest outcomes happen when both partners hear the same information and decide as a team, and say you hope she can pick a time when both can attend. Then reassure her that if it is truly impossible that is okay too, and you will make the best of the call. Then include the booking link. Do NOT withhold the link, do NOT guilt her, and do NOT ask for her email.", url_names=("booking_link",), require_urls=True),
    Action.BOOKING_IS_IT_SONIA: _ModeSpec("BOOK", "Explain the first call is with your team, and you will be her coach inside the program."),
    Action.BOOKING_CALL_PROCESS: _ModeSpec("BOOK", "Explain the first session is to get to know each other and see if you can help."),
    Action.BOOKING_WHO_NATALIA: _ModeSpec("BOOK", "Reassure her that her appointment is with your associate Natalia."),
    Action.BOOKING_WHO_MONIKA: _ModeSpec("BOOK", "Reassure her that her appointment is with your associate Monika."),

    Action.POST_BOOKING_ASK_EMAIL: _ModeSpec("POST_BOOK", "She says she booked. Warmly ask her to remind you of the email address she used to book, so you can check on your end that everything looks good. Share the prep page link so she gets the most out of the call. Tell her the team will text her the day before to confirm attendance, that she MUST reply to that text, and that the meeting is not confirmed if you do not hear back. Close by asking whether that all makes sense. Do NOT state that her booking IS confirmed or verified: you have not checked yet.", url_names=("prep_link",), require_urls=True),
    Action.POST_BOOKING_ACK: _ModeSpec("POST_BOOK", "Warmly thank her for the email and say you will check it on your end to make sure everything looks good. Do NOT claim the booking is confirmed or verified, and do NOT ask a question."),

    Action.PRICE_DEFLECT: _ModeSpec("DEFLECT_PRICE", "Explain price depends on the level of support so you do not give a number yet, and redirect to understanding her situation. Do NOT state any price."),
    Action.PRICE_DEFLECT_LATE: _ModeSpec("DEFLECT_PRICE", "Explain price depends on the level of support so you do not give a number yet, and redirect to fit. Do NOT state any price or re-ask facts she already shared."),
    Action.PRICE_RANGE: _ModeSpec("REVEAL_PRICE", "Share that programs typically range within the given figure, then redirect to fit.", price=True),
    Action.PRICE_RANGE_FIRM: _ModeSpec("REVEAL_PRICE", "Briefly restate the range and point out the exact fit is decided on the call.", price=True),

    Action.ADVICE_DEFLECT: _ModeSpec("DEFLECT_ADVICE", "Explain you would be careful giving generic advice without her full picture, and redirect to understanding her situation. Give NO medical advice."),
    Action.ADVICE_DEFLECT_LATE: _ModeSpec("DEFLECT_ADVICE", "Explain advice is case-specific and the best next step is speaking with your team. Give NO medical advice or re-ask known facts."),
    Action.ADVICE_DEFLECT_PUSH: _ModeSpec("DEFLECT_ADVICE", "Note many factors are involved and it depends on her case, then redirect to discovery. Give NO specific medical advice."),
    Action.ADVICE_DEFLECT_PUSH_LATE: _ModeSpec("DEFLECT_ADVICE", "Note it depends on her specific case and the most useful next step is a proper conversation. Give NO specific medical advice."),

    Action.SOCIAL_PROOF: _ModeSpec("MISC", "Briefly share your track record to build trust; be selective, not salesy."),
    Action.PAYING_TWICE: _ModeSpec("MISC", "Explain your program offers much more than advice (nutrition, coaching, community)."),
    Action.IVF_ONLY_OFFER: _ModeSpec("MISC", "If IVF is her medical path, validate it and NEVER suggest there are other options instead; offer to support her body before and during IVF, and ask if she is interested."),
    Action.PHONE_NUMBER_DEFLECT: _ModeSpec("MISC", "Explain you only take calls for confirmed appointments and can send the booking link when ready."),
    Action.MASTERCLASS_SEND: _ModeSpec("MISC", "Warmly share the masterclass link and ask what she thinks after watching.", url_names=("register_link",), require_urls=True),
    Action.TROUBLE_BOOKING: _ModeSpec("MISC", "Help troubleshoot the booking: ask about an error message or screenshot."),
    Action.OLD_CONVO: _ModeSpec("MISC", "Warmly reconnect and offer to schedule a call."),
    Action.COLD_OUTREACH: _ModeSpec("MISC", "Thank her for the follow and ask what brings her here."),

    # Out-of-scope declines are sensitive -> emitted verbatim (not generated).
    Action.OOS_BOTH_TUBES: _ModeSpec("OOS", "", generate=False),
    Action.OOS_MENOPAUSE: _ModeSpec("OOS", "", generate=False),
    Action.OOS_NO_PERIOD_12M: _ModeSpec("OOS", "", generate=False),
    Action.OOS_AGE_OVER_46: _ModeSpec("OOS", "", generate=False),
    Action.OOS_DEAF: _ModeSpec("OOS", "", generate=False),
}

_DEFAULT_SPEC = _ModeSpec("MISC", "Respond warmly and briefly, staying on the conversation's goal.")

# Actions whose approved content is legitimately multi-sentence.
_LONG_ACTIONS = {
    Action.EXPLAIN_ROLE_TFS_UPDATED, Action.EXPLAIN_ROLE_TFS3,
    Action.SEND_BOOKING, Action.SEND_BOOKING_TOGETHER,
    Action.POST_BOOKING_ASK_EMAIL, Action.BOOKING_CALL_PROCESS,
}

# Guidance overrides: use SHORT, varied key-points as the reference (instead of
# the long verbatim script) so the Voice writes a fresh, natural message. The
# full script remains the fallback. (reference_text, max_chars).
_GUIDANCE = {
    Action.EXPLAIN_ROLE: (
        "In a few short, plain sentences: a fertility coach helps her look at the full "
        "picture around her fertility and build a personalized plan to support her body "
        "before or during trying naturally, IUI, or IVF. Clarify you're not a doctor or "
        "clinic (no prescribing, no IVF, no replacing medical care). Your work can include "
        "things like nutrition, inflammation, hormones, egg and sperm quality, nervous "
        "system regulation, sleep, stress, gut health, metabolic health, timing, and "
        "lifestyle, depending on the person. End by asking if that's the kind of support "
        "she's looking for. Never pitch or re-ask whether she has considered a coach.",
        520,
    ),
    Action.ASK_PRIORITY: (
        "Ask how much of a priority getting pregnant is for her right now. VARY the phrasing "
        "between messages: sometimes a 1 to 10 scale, other times simply 'is getting pregnant "
        "your TOP priority right now?'. Do not always use the 1 to 10 format.",
        320,
    ),
    Action.FINANCIAL_CHECK: (
        "Gently let her know that IF you both decide it's a good fit, this is a paid coaching "
        "program (it takes time, energy and financial commitment), and ask if she's open to that "
        "if it feels aligned. Keep it light and low-pressure, and VARY your wording each time - "
        "do not reuse the same sentence.",
        320,
    ),
    Action.SEND_BOOKING: (
        "Warmly invite her to book the call and include the booking link (include the exact "
        "link). Do NOT ask for her email. Close by asking her to follow the next steps "
        "carefully after booking so the call gets confirmed. Tailor the timing note to HER "
        "situation using the facts you have: if she is solo / single / doing this alone, "
        "simply invite her and do NOT mention a partner or 'both of you'; only if she has a "
        "partner, ask her to pick a time when both decision makers can attend. Keep it concise.",
        500,
    ),
}

_FACT_KEYS = ("trying_duration", "age", "treatment_path", "what_tried", "done_testing",
              "diagnosis", "diagnosis_detail", "partner_status")


def _price_tokens(cfg: Optional[dict], language: str = "en") -> list:
    # must_include has to match the figures the language's script renders.
    key = "price_range_es" if language == "es" else "price_range"
    value = scripts.placeholders(cfg).get(key, "")
    return re.findall(r"\$[\d,]+", value)


def _still_needed(state: dict) -> list:
    s = state["slots"]
    needed = []
    if not ctrl._discovery_complete(s):
        needed.append("her situation (how long trying, age, what she has tried)")
    if not ctrl._priority_ok(s):
        needed.append("how much of a priority pregnancy is right now")
    if not ctrl._role_ok(state):
        needed.append("that she understands and wants the holistic coaching approach")
    if not ctrl._financial_ok(s):
        needed.append("that she is open to a paid program")
    if not ctrl._partner_resolved(s):
        needed.append("whether a partner or decision-maker is involved")
    return needed


def build_directive(decision, cfg: Optional[dict] = None, ig_user_id: str = "") -> TurnDirective:
    action = decision.action
    state = decision.lead_state
    language = state["slots"].get("language") or "en"

    # Human takeover (incl. unsupported language) sends nothing.
    if action in (Action.HUMAN_TAKEOVER, Action.UNSUPPORTED_LANGUAGE):
        return TurnDirective(
            mode="TAKEOVER", action=action, generate=False, objective="",
            reference_text="", pinned_text=None, send_message=False,
            pause=decision.pause, pause_reason=decision.pause_reason,
            add_tag=decision.add_tag, lead_state=state, language=language,
        )

    spec = _SPEC.get(action, _DEFAULT_SPEC)
    ph = scripts.placeholders(cfg)

    # Reference text: short guidance override, else the approved script (which
    # is also the fallback). Discovery's reference is the chosen next question.
    override = _GUIDANCE.get(action)
    if action == Action.ASK_DISCOVERY:
        brief = decision.composer_brief or {}
        reference_text = brief.get("next_question", "")
    elif override:
        reference_text = override[0]
    elif action in scripts.SCRIPTS:
        reference_text = scripts.render(action, cfg, language)
    else:
        reference_text = ""

    # Pinned / non-generated (OOS declines) — verbatim, in the lead's language.
    if not spec.generate:
        return TurnDirective(
            mode=spec.mode, action=action, generate=False, objective=spec.objective,
            reference_text=scripts.render(action, cfg, language) if action in scripts.SCRIPTS else "",
            pinned_text=scripts.render(action, cfg, language) if action in scripts.SCRIPTS else "",
            send_message=decision.send_message, pause=decision.pause,
            pause_reason=decision.pause_reason, add_tag=decision.add_tag,
            qualified=decision.qualified, lead_state=state, language=language,
        )

    allow_urls = [ph[name] for name in spec.url_names if ph.get(name)]
    must_include = list(allow_urls) if spec.require_urls else []
    if spec.price:
        must_include += _price_tokens(cfg, language)

    known_facts = {k: state["slots"][k] for k in _FACT_KEYS if state["slots"].get(k)}
    if action == Action.ASK_DISCOVERY and decision.composer_brief:
        known_facts = decision.composer_brief.get("facts_to_reflect", known_facts)

    # Multi-fact turns (Sonia v1.1): before the priority question, reflect back
    # what she just shared in one sentence so she knows she was heard.
    objective = spec.objective
    reflect_first = (action == Action.ASK_PRIORITY
                     and len((getattr(decision, "meta", None) or {}).get("new_facts", [])) >= 2)
    if reflect_first:
        objective = ("She just shared several new details at once. First reflect them back "
                     "briefly in one sentence so she knows you got them, then: " + objective)

    max_chars = override[1] if override else (900 if action in _LONG_ACTIONS else 400)
    if reflect_first:
        max_chars += 120  # room for the reflection sentence
    if language == "es":
        max_chars = int(max_chars * 1.2)  # Spanish runs ~15-20% longer

    disclaimer_key = _DISCLAIMER_KEY_ES if language == "es" else _DISCLAIMER_KEY
    return TurnDirective(
        mode=spec.mode, action=action, generate=True, objective=objective,
        reference_text=reference_text, known_facts=known_facts,
        still_needed=_still_needed(state), must_include=must_include,
        allow_urls=allow_urls, allow_price_figure=spec.price,
        max_chars=max_chars,
        pinned_text=(disclaimer_key if spec.disclaimer else None),
        send_message=decision.send_message, pause=decision.pause,
        pause_reason=decision.pause_reason, add_tag=decision.add_tag,
        qualified=decision.qualified, lead_state=state, language=language,
    )
