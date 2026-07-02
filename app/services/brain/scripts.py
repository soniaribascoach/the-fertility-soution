"""Verbatim script registry — the single source of truth for outgoing text.

Every message here is taken from specs/sonia_feedback_spec.md (email is
authoritative over the PDF). Placeholders in {curly_braces} are resolved from
config at render time. This registry is the anti-hallucination guarantee:
~90% of what the bot says is rendered verbatim from here, never generated.

The ONLY generative action is Action.ASK_DISCOVERY (handled by the composer),
which intentionally has no template here.
"""
from app.services.brain.constants import Action

# --- Config-resolved placeholders (with safe defaults) -----------------------

_PLACEHOLDER_DEFAULTS = {
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "register_link": "https://www.thefertilitysolution.com/register",
    "watch_replay": "https://www.thefertilitysolution.com/watch-replay",
    "website": "https://www.soniaribas.com/",
    "ig_highlights": "https://www.instagram.com/stories/highlights/17936802155213950/",
    "natalia_phone": "+1 (415) 694-1799",
    "monika_phone": "+1 (647) 992-6383",
    "price_range": "$1,500 to $14,000",
}

# config key -> placeholder name (lets admins override any of the above)
_CONFIG_OVERRIDES = {
    "booking_link": "booking_link",
    "masterclass_register_link": "register_link",
    "masterclass_replay_link": "watch_replay",
    "website_link": "website",
    "ig_highlights_link": "ig_highlights",
    "natalia_phone": "natalia_phone",
    "monika_phone": "monika_phone",
    "price_range": "price_range",
}


def placeholders(cfg: dict | None = None) -> dict:
    """Resolve the placeholder map from config, falling back to defaults."""
    values = dict(_PLACEHOLDER_DEFAULTS)
    cfg = cfg or {}
    for cfg_key, name in _CONFIG_OVERRIDES.items():
        v = (cfg.get(cfg_key) or "").strip() if isinstance(cfg.get(cfg_key), str) else cfg.get(cfg_key)
        if v:
            values[name] = v
    return values


# --- The registry ------------------------------------------------------------

SCRIPTS: dict[Action, str] = {
    # Priority qualification (Phase 3)
    Action.ASK_PRIORITY: (
        "On a scale of 1 to 10, how much of a priority is getting pregnant right now?"
    ),
    Action.PRIORITY_NOT_UNDERSTOOD: (
        "I see. I am a fertility coach with 15 years of experience and a proven track "
        "record with thousands of people around the world. I believe we can make progress "
        "together, and I would love to help you reach your goal. I typically work with "
        "clients who are fully committed to the process. Are you ready to give it your all?"
    ),
    Action.REENGAGE_LOW_PRIORITY: (
        "With 15 years of experience and a proven track record globally, I'm confident we "
        "can achieve progress together in your fertility journey. My approach is very "
        "effective with clients who are fully committed to the process. Are you ready to "
        "dedicate yourself to this journey?"
    ),
    Action.LOW_PRIORITY_INFO_GATHERING: (
        "My work is most effective for women and couples who are fully committed to making "
        "fertility a priority. Do you feel ready to really focus on this now, or are you "
        "more in the information-gathering stage?"
    ),
    Action.NURTURE_CLOSE: (
        "Thank you for being so honest with me. It sounds like the best next step for now is my "
        "free masterclass and resources, and when you feel ready to really focus on this, I'll "
        "be here for you.\n\n{register_link}"
    ),

    # Explain role (Phase 4)
    Action.EXPLAIN_ROLE: (
        "Just so it's clear, I'm a fertility coach, not a doctor or fertility clinic. "
        "I don't perform IVF, prescribe medication, or replace medical care.\n\n"
        "My work is a highly personalized, research-backed, holistic approach to fertility. "
        "I look at the full picture of what may be affecting your ability to conceive and "
        "what your body may need in order to feel safer, healthier, and more supported for "
        "pregnancy.\n\n"
        "Depending on the case, this can include things like nutrition, inflammation, "
        "hormones, egg and sperm quality, nervous system regulation, sleep, lifestyle, "
        "timing, stress, gut health, metabolic health, and much more. But it is not limited "
        "to those things, because every woman and every couple is different.\n\n"
        "That's why I like to understand your specific situation first before saying whether "
        "I may be able to help.\n\n"
        "Is that the kind of support you're looking for?"
    ),
    Action.EXPLAIN_ROLE_TFS_UPDATED: (
        "I am an online fertility coach helping women conceive naturally by helping them "
        "improve their overall health and fertility. Most of my clients have been told to do "
        "IUI or IVF. Some did random things, others told unexplained infertility, and many "
        "more. One of the things we'll do is to pinpoint what's making you not pregnant and "
        "work on a solution for that. This includes sessions and opening up about your "
        "journey. In the program, not only will we be working together, but also your "
        "partner. There's plenty of things we'll do, I'll be with you all throughout your "
        "journey. Is this something you're interested in?"
    ),
    Action.EXPLAIN_ROLE_TFS1: (
        "I am a fertility coach helping women conceive naturally by helping them improve "
        "their overall health and fertility. Is this something you're interested in?"
    ),
    Action.EXPLAIN_ROLE_TFS2: (
        "I am a holistic health coach and I combine lots of approaches including therapy to "
        "improve your health and fertility from every possible angle."
    ),
    Action.EXPLAIN_ROLE_TFS3: (
        "Absolutely, I completely understand wanting to know more about my approach and "
        "results. I have a strong track record of helping women like you achieve their dreams "
        "of becoming mothers.\n\n"
        "You can check out my website for client testimonials: {website}\n\n"
        "You can check my IG profile, it's loaded with testimonials: {ig_highlights}\n\n"
        "And watch my free masterclass to get a deeper understanding of my methods and case "
        "studies: {watch_replay}"
    ),

    Action.EXPLAIN_ROLE_CONFIRM: "Is that the kind of support you're looking for?",

    # Financial readiness (Phase 5)
    Action.FINANCIAL_CHECK: (
        "Just so you know, if we decide this is a good fit, this is a paid coaching program "
        "that requires time, energy, and financial commitment. Is that something you're open "
        "to if it feels aligned?"
    ),
    Action.FINANCIAL_DECLINE: (
        "Thank you for being honest with me. It may be better to start with the free "
        "masterclass and resources for now, and when you feel ready for deeper support, "
        "I'll be here.\n\n"
        "{register_link}"
    ),

    # Partner / decision-maker (Phase 6)
    Action.PARTNER_CHECK: (
        "Because fertility is usually a team decision, I strongly recommend that both "
        "partners join the call so everyone is aligned from the beginning. Are you doing "
        "this with a partner, or are you navigating this on your own?"
    ),
    Action.PARTNER_ASK_JOIN: "Would your partner be able to join you on the call?",
    Action.PARTNER_PUSHBACK: (
        "We will use this meeting to determine if we are a match to work together to help you "
        "get pregnant. Which is why we need all the decision-makers there. If your partner is "
        "a decision-maker, we need him there. If you are the only decision maker and you can "
        "make your own investment decisions in your pregnancy, you're welcome to come alone "
        "to the meeting, ready to make powerful decisions for you and your family."
    ),

    # Booking (Phase 7)
    Action.SEND_BOOKING: (
        "Based on what you shared, it sounds like it may be worth speaking with my team to "
        "see if and how I can help.\n\n"
        "Here's the link to book your call: {booking_link}\n\n"
        "Please choose a time when both decision makers can attend if your partner is part "
        "of the decision. If you're doing this on your own, of course you can come alone.\n\n"
        "Once you book, send me the email you used so we can confirm it on our end."
    ),
    Action.BOOKING_IS_IT_SONIA: (
        "The first call is with my team so we can understand your situation properly and see "
        "if this is the right fit. If we all decide we're a great match to work together, "
        "I will be your only coach inside the program and I'll be with you every step of the "
        "way."
    ),
    Action.BOOKING_CALL_PROCESS: (
        "The first session is all about getting to know each other, see where you are and "
        "if/how I can help you achieve your dreams.\n\n"
        "I am a fertility coach with a 70% success rate amongst thousands of couples around "
        "the world. My success is due to 2 factors: 1. my program is really effective. "
        "2. I am very selective.\n\n"
        "In the session I will tell you if I can change your life or not. If I can, I will "
        "give you options and give you all the info so you can make a fully informed decision "
        "on whether you want to work with me or not."
    ),
    Action.BOOKING_WHO_NATALIA: (
        "Your appointment is with my fantastic associate Natalia, you'll love her. When you "
        "join the program, I'll see you inside and personally hold your hand through the "
        "fertility coaching process."
    ),
    Action.BOOKING_WHO_MONIKA: (
        "Your appointment is with my amazing associate, Monika. Just like my clients, she's "
        "been on the same journey too. When you join the program, I'll see you inside and "
        "hold your hand through the fertility coaching process."
    ),

    # Post-booking (Phase 8)
    Action.POST_BOOKING_ASK_EMAIL: (
        "Can I have your email address so I can verify and make sure your schedule shows on "
        "our end?"
    ),
    Action.POST_BOOKING_CONFIRM_NATALIA: (
        "Great! You'll be speaking with my associate, Natalia! Please make sure to confirm "
        "via text message when you receive a text confirmation request from this number "
        "{natalia_phone}\n\n"
        "Before the call, it's very important to watch this short masterclass so you have a "
        "good sense of how I help my clients in your situation: {watch_replay}\n\n"
        "You'll also see some client case studies and it will ensure that you're fully "
        "informed before our call, deal?"
    ),
    Action.POST_BOOKING_CONFIRM_MONIKA: (
        "Great! You'll be speaking with my associate, Monika! Please make sure to confirm "
        "via text message when you receive a text confirmation request from this number "
        "{monika_phone}\n\n"
        "Before the call, it's very important to watch this short masterclass so you have a "
        "good sense of how I help my clients in your situation: {watch_replay}\n\n"
        "You'll also see some client case studies and it will ensure that you're fully "
        "informed before our call, deal?"
    ),

    # Advice / price / misc deflections
    Action.ADVICE_DEFLECT: (
        "I would be careful giving you generic advice without understanding your full "
        "situation, because fertility is very case-specific. The best next step would be to "
        "speak with my team so we can get to know you properly, understand what you've "
        "already tried, and see if and how I can help. Can I ask how long you've been trying "
        "and what you've already done so far?"
    ),
    Action.ADVICE_DEFLECT_LATE: (
        "I would be careful giving you generic advice without understanding your full "
        "situation, because fertility is very case-specific. The best next step is to speak "
        "with my team so we can look at your specific picture and see if and how I can help."
    ),
    Action.ADVICE_DEFLECT_PUSH: (
        "There are usually many factors involved, and it depends on your specific case. "
        "I usually look at the full picture, including things like nutrition, inflammation, "
        "lifestyle, hormones, stress, and much more, but I wouldn't want to assume what "
        "matters most for you without understanding your situation first. How long have you "
        "been trying, and what have you already tried so far?"
    ),
    Action.ADVICE_DEFLECT_PUSH_LATE: (
        "There are usually many factors involved, and it really depends on your specific "
        "case. I look at the full picture rather than any single symptom or lab, but the most "
        "useful next step is a conversation where we go through your situation properly."
    ),
    Action.PRICE_DEFLECT: (
        "It depends on the level of support someone needs, so I don't give a random number "
        "before understanding your situation. The first step is seeing if I can actually help "
        "and what kind of support would make sense for you. Can I ask how long you've been "
        "trying and what you've already done so far?"
    ),
    Action.PRICE_DEFLECT_LATE: (
        "It depends on the level of support someone needs, so I don't give a random number "
        "before understanding your situation. Let me make sure this is the right fit for you "
        "first, and we can go over everything from there."
    ),
    Action.PRICE_RANGE: (
        "Programs typically range from {price_range} depending on the level of support. "
        "What matters most is making sure this is the right support for your body and your "
        "situation."
    ),
    Action.PRICE_RANGE_FIRM: (
        "Like I mentioned, it really depends and lands in that {price_range} range. The best "
        "way to know what you would actually need is on the call, where we tailor everything "
        "to your situation."
    ),
    Action.PHONE_NUMBER_DEFLECT: (
        "I only take calls for confirmed appointments. If you want to speak to me or my team, "
        "you can schedule it by booking your call. Let me know if you want me to send the "
        "booking link."
    ),
    Action.MASTERCLASS_SEND: (
        "Hi sister! Thank you for showing interest in what I do. :) Here's the link. "
        "{register_link}\n\n"
        "Let me know what you think after watching this."
    ),
    Action.SOCIAL_PROOF: (
        "I've been doing this work for 16+ years and have helped welcome over 700 babies, "
        "so I'm very selective about making sure this is the right fit before inviting "
        "someone to a call."
    ),
    Action.PAYING_TWICE: (
        "There could potentially be some similar information but we offer a lot more than "
        "advice. We have customized-nutrition, private/group coaching sessions, a wide source "
        "of education resources, and a great community of like-minded women who support each "
        "other through this journey."
    ),
    Action.IVF_ONLY_OFFER: (
        "If IVF is the best path for you medically, I may still be able to help by optimizing "
        "your chances of success. I support the full picture of fertility and IVF preparation "
        "using a highly personalized, research-backed, holistic approach. Is that something "
        "you're interested in?"
    ),
    Action.TROUBLE_BOOKING: (
        "Sorry about that. Did you see any error message? Can you please send a screenshot so "
        "I can check on my end. You should receive an email confirmation after booking and be "
        "prompted on this page.\n\n"
        "If you didn't see this page, please redo the booking."
    ),
    Action.OLD_CONVO: (
        "Hi there! I see we have talked before. Would you like to schedule a Zoom meeting with "
        "one of my associates? Would love to help you get pregnant in 4-6 months! <3"
    ),
    Action.COLD_OUTREACH: (
        "Thanks for the follow! :) I appreciate it. Just wanted to know what brings you here. "
        "Are you on a journey to conceiving?"
    ),
    Action.NO_MONEY: (
        "Thank you for being honest, if you ever find yourself fully ready to commit to this, "
        "I'll be here for you."
    ),

    # Out-of-scope clarifying questions
    Action.ASK_BOTH_TUBES: "Are both tubes blocked, or only one?",
    Action.ASK_MENOPAUSE_REASON: (
        "Thank you for sharing that. Can I ask what's the reason you're no longer getting "
        "your period?"
    ),
    Action.ASK_MENOPAUSE_AGE: "I understand. And can I ask how old you are?",

    # Out-of-scope terminal messages (paired with human takeover)
    Action.OOS_BOTH_TUBES: (
        "If both tubes are fully blocked, coaching cannot make the egg pass through the "
        "tubes, and I would not position this as something coaching alone can solve. I'm not "
        "a fertility clinic and cannot perform IVF. In this case, I can only help if you are "
        "also pursuing IVF, because I can support you in optimizing your body, inflammation, "
        "hormones, egg quality, nutrition, nervous system, and IVF readiness to help improve "
        "your chances of success."
    ),
    Action.OOS_MENOPAUSE: (
        "Thank you for being transparent with me. Based on what you shared, this may be "
        "outside the scope of what I can help with through coaching. I'm really sorry, and "
        "I wish you all the best."
    ),
    Action.OOS_AGE_OVER_46: (
        "Thank you for sharing that with me. Because age can change what is realistically "
        "possible and what kind of support is appropriate, I want to review this carefully "
        "before pointing you in the wrong direction."
    ),
    Action.OOS_DEAF: (
        "Sorry but our meetings and program wouldn't be suitable for your needs. I'm very "
        "sorry for that. I wish you all the best."
    ),
    Action.OOS_LANGUAGE_BARRIER: (
        "Hi sister! I understand your situation. However, all my programs and meetings are "
        "conducted in English. Sorry about that."
    ),
}


# --- Banks (used by the controller + composer, not standalone messages) ------

# Phase 2 empathy variants, keyed by situation type the extractor detects.
EMPATHY_VARIANTS = {
    "hopeless": (
        "I'm really sorry you're going through this. It can be challenging, but you're not "
        "alone in this journey. I'm here to help."
    ),
    "neutral": "I admire how committed you are to this journey. Thanks for sharing.",
    "misfortune": (
        "I am sorry you're going through this. I understand how difficult it must have been "
        "but the fact that you're enduring these challenges tells me you're strong and "
        "resilient. Thank you for sharing."
    ),
}

# Phase 2 primary discovery questions, in order of relevance.
DISCOVERY_QUESTIONS = {
    "trying_duration": "How long have you been trying, and what have you already tried?",
    "age": "How old are you?",
    "treatment_path": "Are you trying naturally, doing IUI, doing IVF, or still deciding?",
    "done_testing": "Have you done any fertility testing yet?",
    "diagnosis": "Has a doctor given you any specific diagnosis?",
}

# Light, non-empathy acknowledgments (used when no specific empathy variant fits).
AFFIRMATIONS = [
    "Thank you for sharing that. That gives me a better picture.",
    "Got it, that helps.",
    "That makes sense.",
    "Thank you for being honest with me.",
]

# Follow-up sequences (used by a follow-up scheduler, not the live turn flow).
FOLLOWUPS = {
    "confirm_booking_1": (
        "Hi sister! Just circling back to know if you've booked the call so I can send "
        "something over to you. I would love to hear back from you. Thanks! \U0001fa77"
    ),
    "book_call_1": (
        "Hi sister! Just circling around to know if you are still interested to continue your "
        "pregnancy journey so we can schedule our call and I can send something over to you. "
        "I would love to hear back from you. Thanks! \U0001fa77"
    ),
    "confirm_booking_2": (
        "Hi sister! I'm curious if you've already booked a call. Can I have your email address "
        "so I can verify and make sure your schedule shows on our end? :)"
    ),
    "book_call_2": (
        "Hi sister! Just sharing this good news to you from one of my clients. You can be the "
        "next one! Book your free consultation now! {booking_link}"
    ),
    "confirm_booking_3": (
        "Hi sister! If you still need help, please don't hesitate to reach out to us. :) "
        "Otherwise, take advantage of my masterclass replay. Hope that helps! {watch_replay}"
    ),
    "book_call_3": (
        "Hi sister! If you still need help, please don't hesitate to reach out to us. :) "
        "Otherwise, please visit my website at {website} or visit my IG bio for client wins "
        "and highlights! Hope that helps! :)"
    ),
}


# --- Renderer ----------------------------------------------------------------

def render(action: Action, cfg: dict | None = None) -> str:
    """Render a scripted action's verbatim text with config placeholders filled.

    Raises KeyError on an unknown action, and asserts no placeholder was left
    unfilled (so a typo'd template fails loudly in tests, never in production).
    """
    if action not in SCRIPTS:
        raise KeyError(f"No script template for action {action!r}")
    text = SCRIPTS[action].format(**placeholders(cfg))
    assert "{" not in text and "}" not in text, (
        f"Unfilled placeholder in rendered {action!r}: {text!r}"
    )
    return text


def render_followup(name: str, cfg: dict | None = None) -> str:
    """Render a follow-up sequence message by name."""
    if name not in FOLLOWUPS:
        raise KeyError(f"No follow-up named {name!r}")
    return FOLLOWUPS[name].format(**placeholders(cfg))
