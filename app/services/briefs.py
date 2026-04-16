"""
Writer brief builders for the AI pipeline.

Each function returns a focused 15-20 line instruction string (writer_brief)
that tells the Writer Agent exactly what to do on a given turn.

Separated from orchestrator.py so the strategy engine (decision-making) and
the content templates (what to say) live in different modules.
"""

from __future__ import annotations

from app.services.router import RouteContext


# ── Bubble counts ─────────────────────────────────────────────────────────────

BUBBLE_COUNTS: dict[str, int] = {
    # Two beats — always two distinct thoughts that should not be merged
    "open": 2,              # greeting + opening question
    "open_context": 2,      # greeting + direct response to what she shared
    "empathize": 2,         # ack + soft invitation (two separate emotional beats)
    "empathize_qualify": 2, # ack (bubble 1) + question (bubble 2)
    "handle_pricing_deflect": 2,  # redirect + booking question
    "handle_pricing_reveal": 2,   # range + booking question
    "handle_pricing_redirect": 2, # acknowledge + redirect question
    "confirm_booking": 2,
    # Single message — quality gate enforces this strictly
    "qualify": 1,
    "synthesise": 1,
    "handle_objection": 1,
    "nurture": 1,
    "low_intent": 1,
    # Two warm bubbles — URL appended deterministically by pipeline (never writer-generated)
    "send_booking": 2,
}


# ── Turn-aware tone note ──────────────────────────────────────────────────────

def _turn_tone(turn_number: int) -> str:
    if turn_number <= 1:
        return "Turn focus: connection only. Acknowledge and invite more. No education, no clinical information."
    if turn_number <= 3:
        return "Turn focus: reflect and connect. A light reframe is fine now that connection is established."
    return "Turn focus: offer insight and gentle direction. The conversation should feel like it is going somewhere."


# ── Pattern context helper ────────────────────────────────────────────────────

def _pattern_context(route: RouteContext) -> str:
    """
    When a scenario pattern is matched, return a mandatory directive injected into
    the writer brief. The writer must reflect the core perspective — adapted naturally,
    never quoted verbatim.
    """
    if not route.matched_pattern:
        return ""
    label, text = route.matched_pattern
    return (
        f"\nMATCHED SCENARIO — {label}:\n"
        f"Your reply MUST reflect this perspective. Adapt the phrasing to feel natural and "
        f"specific to her situation — do not quote verbatim — but the core angle must come through clearly:\n"
        f"{text}\n"
    )


# ── Specificity anchor ───────────────────────────────────────────────────────

def _specificity_anchor(route: RouteContext) -> str:
    """
    Extracts concrete data points from known_facts and instructs the writer to
    anchor the reply to at least one of them. Prevents generic replies that could
    apply to any woman regardless of her specific situation.
    """
    if not route.known_facts:
        return ""
    facts = []
    for raw in route.known_facts.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        # Strip the "do not ask again" / "do NOT ask" tail — keep only the fact itself
        fact = raw.split(" — ")[0].strip()
        if fact:
            facts.append(fact)
    if not facts:
        return ""
    joined = "; ".join(facts)
    return (
        f"ANCHOR your reply to at least one of these specific facts she has shared: {joined}\n"
        "Reference her actual situation — not generic fertility commentary that could apply to anyone.\n"
    )


# ── Writer brief builders ─────────────────────────────────────────────────────

def brief_open(route: RouteContext) -> str:
    variant = route.opening_variant or ""
    return (
        "This is her very first message.\n"
        "Write 2 short bubbles:\n"
        "Bubble 1: A brief, warm one-liner greeting. Natural and human — not a corporate welcome.\n"
        "Bubble 2: Follow with this opening line (you may adapt the wording slightly, keep the spirit):\n"
        f'"{variant}"\n'
        "Do not stack a question on top of the opening line."
    )


def brief_open_context(route: RouteContext) -> str:
    return (
        "This is her very first message — and she has already shared something personal.\n"
        "Write 2 short bubbles:\n"
        "Bubble 1: A brief, warm one-liner greeting. One natural sentence.\n"
        "Bubble 2: Respond directly and specifically to what she shared. No generic opener.\n"
        "Add at least one of: a reframe, a small insight, or directional guidance.\n"
        "Connection before guidance. Guidance before education.\n"
        "If you include a question, it must be short and specific — something clinically relevant "
        "or about her situation. Never ask gut-feel or open-ended questions: "
        "no 'What's your gut saying?', no 'What feels right to you?', no 'What would you want to explore?'. "
        "If you cannot form a good specific question, make a statement instead."
    )


def brief_empathize() -> str:
    return (
        "She shared something heavy — a loss, a failed cycle, devastation, or hopelessness.\n"
        "Write exactly 2 bubbles.\n"
        "Bubble 1: Pure acknowledgment only. 1-2 sentences. Real, not scripted.\n"
        'No therapy phrases ("that must feel", "I appreciate you sharing", "what I\'m hearing is").\n'
        "Short and honest lands harder than long and elaborate.\n"
        "Bubble 2: One soft, open invitation to keep sharing. Not a qualifying question. Not advice.\n"
        '"I\'d love to hear more about where you\'re at." or "Tell me a bit more about what this has been like."\n\n'
        "No question. No mention of services, zoom sessions, or next steps. Not even hinted at."
    )


def brief_empathize_qualify(route: RouteContext, turn_number: int, empathize_streak: int = 0) -> str:
    question_line = (
        f'Bubble 2: Weave in naturally: "{route.question_for_dim}"\n'
        if route.question_for_dim
        else "Do NOT ask a question. Write one acknowledgment bubble only. Do not invent a question.\n"
    )
    pattern_line = _pattern_context(route)

    zoom_nudge = ""
    if empathize_streak >= 1 and route.matched_pattern:
        zoom_nudge = (
            "\nYou have already acknowledged what she is going through. Now begin to guide.\n"
            "After the question, you may add one gentle sentence planting the idea of the zoom session — "
            "e.g. 'This is exactly the kind of situation we look at in detail together.' "
            "Do NOT include a URL or ask her to confirm anything. Just let the idea land naturally.\n"
        )

    anchor_line = _specificity_anchor(route)
    return (
        "She's sharing something difficult but is still in a conversational mode.\n"
        "Write 2 bubbles:\n"
        "Bubble 1: Genuine acknowledgment. Warm but not over-the-top. 1-2 sentences.\n"
        "BANNED — do not use these phrases or close variants in bubble 1:\n"
        "  'That must feel', 'That frustration makes sense', 'That desire is so important',\n"
        "  'I can imagine how hard', 'I understand how you must be feeling',\n"
        "  'That sounds like a lot', 'I'm glad you reached out', 'I'm sorry to hear that'.\n"
        "Acknowledge by STATING what you observe concretely. Not by mirroring feelings back.\n"
        f"{question_line}"
        f"{anchor_line}"
        f"{pattern_line}"
        f"{zoom_nudge}"
        "Add at least one of: a reframe, a small insight, or directional guidance.\n"
        f"{_turn_tone(turn_number)}"
    )


def brief_qualify(route: RouteContext, turn_number: int) -> str:
    known = route.known_facts or "nothing specific yet"
    if route.question_for_dim:
        question_line = (
            f'End with this specific question: "{route.question_for_dim}"\n'
            "Never ask a vague open question ('how are you feeling?', 'what concerns you?'). "
            "Make it specific and clinically relevant.\n"
        )
    else:
        question_line = (
            "All key dimensions are already known — do NOT re-ask about timeline, diagnosis, or age.\n"
            "Instead: make one specific, expert observation linking her details together "
            "(her numbers, her timeline, her context). Show you've been listening.\n"
            "Then end with one forward-looking question that moves the conversation. Good options:\n"
            "  - What support or treatment has she actually tried so far?\n"
            "  - What is she most uncertain about right now?\n"
            "  - What does she feel hasn't been properly addressed?\n"
            "  - What has changed (or not changed) since her last cycle/test?\n"
            "Make the question specific to HER situation — not a generic 'how are you feeling?' or "
            "'what are your thoughts?'. It should feel like a natural expert follow-up, "
            "not a checklist item.\n"
        )
    authority_line = (
        f'Weave this in naturally (do not make it its own sentence — fold it into your observation): '
        f'"{route.authority_phrase}"\n'
        if route.authority_phrase
        else ""
    )
    pattern_line = _pattern_context(route)

    # After 2+ empathize turns: explicitly break the reflection loop
    streak_shift = ""
    if route.empathize_streak >= 2:
        streak_shift = (
            "IMPORTANT: You have acknowledged her emotional state for 2 turns already. "
            "Do NOT continue the empathy or reflection pattern. SHIFT NOW to expert guidance. "
            "Open with a concrete observation or expert insight — not with 'I understand', "
            "'I hear you', 'I can see', or any acknowledgment phrase.\n\n"
        )

    anchor_line = _specificity_anchor(route)
    return (
        f"{streak_shift}"
        "Write exactly 1 message. No blank lines. Everything in one paragraph.\n\n"
        "LEAD the conversation. Do not wait for her to bring things up.\n"
        "Make a specific observation based on what you know about her situation — something concrete "
        "and expert, not generic. React to the actual thing she just said.\n"
        f"What you already know — do NOT re-ask: {known}\n"
        f"{anchor_line}"
        f"{pattern_line}"
        f"{authority_line}"
        f"{question_line}"
        "Do NOT mention zoom sessions, booking, or next steps.\n"
        f"{_turn_tone(turn_number)}"
    )


def brief_synthesise(route: RouteContext) -> str:
    known = route.known_facts or "what she has shared so far"
    pattern_line = _pattern_context(route)
    authority_line = (
        f'Weave this in naturally (fold into your synthesis, not a standalone sentence): '
        f'"{route.authority_phrase}"\n'
        if route.authority_phrase else ""
    )
    anchor_line = _specificity_anchor(route)
    return (
        "You have been listening carefully. Time to connect the dots and guide her forward.\n"
        f"What you know about her: {known}\n"
        f"{anchor_line}"
        f"{pattern_line}"
        f"{authority_line}\n"
        "Write exactly 1 message. No blank lines.\n"
        'Start with "Putting this together..." — link her data points into a coherent picture.\n'
        'Example: "Putting this together — 38, AMH 0.6, only 4 months in, and a doctor already '
        'pushing IVF — the picture here is actually about pace, not impossibility."\n'
        "This is Sonia showing she has been listening AND has a view, not just collecting data.\n"
        "End with one clear, forward-looking direction or a specific question about what she wants next.\n"
        "Do NOT end with a vague open question. End with something that moves the conversation forward."
    )


def brief_handle_pricing_deflect() -> str:
    return (
        "She asked about pricing. Write 2 bubbles.\n"
        "Bubble 1: Acknowledge warmly. Explain that programs vary depending on the level of support and personalisation needed.\n"
        "Position the zoom session as the place to understand her specific situation and find the right fit.\n"
        "CRITICAL: Do NOT mention any specific number, dollar amount, or price — not even a range. "
        "You do not have this information and any number you state will be wrong. "
        "Pricing is discussed in the zoom session only.\n"
        "Tone: open and grounded, not defensive or evasive.\n"
        'Bubble 2: Soft question: "Would that feel like a good next step for you?" or similar.'
    )


def _extract_price_range(cfg: dict) -> str:
    """Extract first price range from prompt_pricing config, or return fallback."""
    import re
    _re = re.compile(r"\$[\d,]+\s*(?:to|–|-)\s*\$[\d,]+", re.IGNORECASE)
    match = _re.search(cfg.get("prompt_pricing", ""))
    return match.group(0) if match else "varies depending on the level of support"


def brief_handle_pricing_reveal(cfg: dict) -> str:
    price_range = _extract_price_range(cfg)
    pricing_guidance = cfg.get("prompt_pricing", "").strip()
    extra = f"\nAdditional pricing context from the business (use as guidance):\n{pricing_guidance}\n" if pricing_guidance else ""
    return (
        "She's asking about price again and is clearly serious. Write 2 bubbles.\n"
        f"Bubble 1: Share the price range: {price_range}.\n"
        'Follow immediately with context: "but we first need to understand your specific situation '
        'before recommending anything — and to make sure we\'re the right fit."\n'
        "Tone: confident and open, not apologetic.\n"
        f"{extra}"
        "Bubble 2: Soft question — would she like to set up that zoom session?"
    )


def brief_handle_pricing_redirect() -> str:
    return (
        "She's asking about price again but isn't fully committed yet. Write 2 bubbles.\n"
        "Continue to redirect warmly to the zoom session — do not share the range yet.\n"
        "Bubble 1: Acknowledge the question. Explain that the right fit depends on her specific situation — "
        "we need to understand what she needs before recommending anything.\n"
        'Bubble 2: "Would it help to have a conversation about what that could look like for you?"'
    )


def brief_handle_objection(route: RouteContext) -> str:
    label, text = route.matched_objection  # type: ignore[misc]
    return (
        f"She's expressing a concern: {label}.\n"
        "Use this approach (adapt naturally, never copy verbatim):\n"
        f"{text}\n\n"
        "Write 1 message. Address her concern directly — don't dance around it.\n"
        "Come with a specific reframe or insight that shifts the perspective.\n"
        "Be confident. You have seen this concern many times."
    )


def brief_low_intent() -> str:
    return (
        "She hasn't shared anything personal yet — she seems to be browsing or unsure what this is.\n"
        "Write 1 bubble:\n"
        "Gently ask what brought her here personally before going any further.\n"
        "Do NOT describe services. Do NOT pitch the program. Do NOT ask qualifying questions.\n"
        '"Of course — what\'s been going on for you lately?" or "What brought you here today?"'
    )


def brief_nurture(route: RouteContext, turn_number: int) -> str:
    known = route.known_facts or "nothing specific yet"
    cta = f'Weave this in naturally: "{route.cta_line}"\n' if route.cta_line else ""
    question_line = (
        f'End with: "{route.question_for_dim}"\n'
        if route.question_for_dim
        else "End with one specific question about whether she'd want to explore a zoom session together.\n"
    )
    authority_line = (
        f'Weave this in naturally (fold into your observation, not a standalone sentence): '
        f'"{route.authority_phrase}"\n'
        if route.authority_phrase else ""
    )
    pattern_line = _pattern_context(route)
    anchor_line = _specificity_anchor(route)
    return (
        "Her engagement is high. Move the conversation toward a zoom session — don't just observe, guide.\n"
        "Write exactly 1 message. No blank lines.\n"
        "Make a specific observation about her situation, then introduce the zoom session as the "
        "obvious next step — not as a pitch, but as what a person in her position would naturally do.\n"
        f"{anchor_line}"
        f"{pattern_line}"
        f"{cta}"
        f"{authority_line}"
        f"What you already know: {known}\n"
        f"{question_line}"
        f"{_turn_tone(turn_number)}"
    )


def brief_confirm_booking(route: RouteContext) -> str:
    cta = f'Wording inspiration: "{route.cta_line}"\n' if route.cta_line else ""
    return (
        "Now is the right moment to invite her into a zoom session. Be direct — this is the natural next step.\n"
        "Write 2 short bubbles:\n"
        "Bubble 1: One specific sentence connecting what she's shared to why a zoom session makes sense "
        "for HER situation. Not generic — grounded in her actual details.\n"
        "Bubble 2: The invitation. Decisive language — 'the best next step IS a zoom session', not 'could be'.\n"
        f"{cta}"
        "End with one clear question: 'Does that feel right?' or 'Would you want to set that up?'\n\n"
        "Do NOT include a URL. Do NOT say 'someone will reach out' or 'I'll send details'. "
        "Do NOT imply any delay or manual step.\n"
        "CRITICAL — NEVER ask any scheduling question. These are all forbidden:\n"
        "  'When would be a good time for you?'\n"
        "  'What time suits you?'\n"
        "  'Morning or afternoon?'\n"
        "  'When are you free?'\n"
        "  'What day works for you?'\n"
        "The booking link handles ALL scheduling. Your only job is to ask if she is ready."
    )


def brief_send_booking(route: RouteContext) -> str:
    return (
        "She confirmed she wants a zoom session. Write exactly 2 short bubbles — "
        "the booking link is added automatically after bubble 2, do not write it yourself.\n"
        "Tone: warm, human, trust-building. She has made a decision — honour it. No selling, no recapping.\n\n"
        "Bubble 1: A short, warm acknowledgment that she's taking this step. "
        "One or two sentences. Express genuine excitement or warmth — not generic ('Great!', 'Wonderful!') "
        "but real, like a person who genuinely looks forward to speaking with her. "
        "A :) is fine here if it fits naturally.\n"
        "Bubble 2: One sentence — forward-looking, not a pitch. "
        "Something like what you'll do together, or what she can expect. Keep it simple and human.\n\n"
        "Do NOT write a URL, a link, or 'You can grab a time here'. The link is added automatically.\n"
        "Do NOT ask about scheduling — not 'when works?', not 'what time?', nothing about availability.\n"
        "Do NOT summarise her situation, repeat her details, or list what the program covers. "
        "She already knows. This moment is about trust, not persuasion.\n"
        "Do NOT say 'someone will reach out', 'I'll send details', or anything implying a delay."
    )
