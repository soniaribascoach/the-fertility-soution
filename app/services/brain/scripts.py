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
    "price_range_es": "$1,500 a $14,000",
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
    "price_range_es": "price_range_es",
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

    # Explain role (Phase 4) — Sonia's v1.1 wording: answer what a coach DOES.
    Action.EXPLAIN_ROLE: (
        "A fertility coach helps you look at the full picture around your fertility and "
        "build a personalized plan to support your body before or during trying naturally, "
        "IUI, or IVF.\n\n"
        "I'm not a doctor or clinic, so I don't prescribe medication, perform IVF, or "
        "replace medical care.\n\n"
        "My work can include things like nutrition, inflammation, hormones, egg and sperm "
        "quality, nervous system regulation, sleep, stress, gut health, metabolic health, "
        "timing, and lifestyle, depending on the person.\n\n"
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
        "Once you book, please follow the next steps carefully so we can make sure your "
        "call is confirmed."
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
}


# --- Spanish registry ---------------------------------------------------------
# Same actions and placeholders as SCRIPTS, in warm, Latin-American-neutral
# Spanish (informal "tu"). Covers every action the controller can reach; dormant
# actions (POST_BOOKING_*, BOOKING_WHO_*, unreferenced explain-role variants,
# OLD_CONVO, COLD_OUTREACH) intentionally fall back to English via render().
# DRAFT copy: pending client (Sonia) review before go-live.

SCRIPTS_ES: dict[Action, str] = {
    # Priority qualification (Phase 3)
    Action.ASK_PRIORITY: (
        "En una escala del 1 al 10, ¿qué tan prioritario es para ti quedar embarazada en "
        "este momento?"
    ),
    Action.REENGAGE_LOW_PRIORITY: (
        "Con 15 años de experiencia y resultados comprobados en todo el mundo, confío en que "
        "podemos lograr avances juntas en tu camino a la maternidad. Mi método es muy "
        "efectivo con clientas que se comprometen de lleno con el proceso. ¿Estás lista para "
        "dedicarte a este camino?"
    ),
    Action.LOW_PRIORITY_INFO_GATHERING: (
        "Mi trabajo es más efectivo con mujeres y parejas que están totalmente comprometidas "
        "a hacer de la fertilidad una prioridad. ¿Sientes que estás lista para enfocarte en "
        "esto ahora, o estás más en una etapa de buscar información?"
    ),
    Action.NURTURE_CLOSE: (
        "Gracias por ser tan honesta conmigo. Parece que el mejor paso por ahora es mi "
        "masterclass gratuita y mis recursos, y cuando te sientas lista para enfocarte de "
        "verdad en esto, aquí estaré para ti.\n\n{register_link}"
    ),

    # Explain role (Phase 4) — Sonia's v1.1 wording: answer what a coach DOES.
    Action.EXPLAIN_ROLE: (
        "Un coach de fertilidad te ayuda a mirar el panorama completo de tu fertilidad y a "
        "crear un plan personalizado para apoyar a tu cuerpo antes o durante la búsqueda "
        "natural, la IUI o la FIV.\n\n"
        "Yo no soy doctora ni una clínica, así que no receto medicamentos, no realizo FIV "
        "ni reemplazo la atención médica.\n\n"
        "Mi trabajo puede incluir cosas como nutrición, inflamación, hormonas, calidad de "
        "óvulos y esperma, regulación del sistema nervioso, sueño, estrés, salud intestinal, "
        "salud metabólica, tiempos y estilo de vida, según cada persona.\n\n"
        "¿Es ese el tipo de apoyo que estás buscando?"
    ),
    Action.EXPLAIN_ROLE_TFS3: (
        "Claro, entiendo perfectamente que quieras saber más sobre mi método y mis "
        "resultados. Tengo una sólida trayectoria ayudando a mujeres como tú a lograr su "
        "sueño de ser madres.\n\n"
        "Puedes ver testimonios de clientas en mi sitio web: {website}\n\n"
        "También puedes revisar mi perfil de IG, está lleno de testimonios: {ig_highlights}\n\n"
        "Y mira mi masterclass gratuita para entender mejor mis métodos y ver casos reales: "
        "{watch_replay}"
    ),
    Action.EXPLAIN_ROLE_CONFIRM: "¿Es ese el tipo de apoyo que estás buscando?",

    # Financial readiness (Phase 5)
    Action.FINANCIAL_CHECK: (
        "Para que lo sepas, si decidimos que encajamos bien, este es un programa de coaching "
        "pago que requiere tiempo, energía y compromiso económico. ¿Es algo a lo que estarías "
        "abierta si sientes que es lo correcto para ti?"
    ),
    Action.FINANCIAL_DECLINE: (
        "Gracias por ser honesta conmigo. Quizás sea mejor empezar por ahora con la "
        "masterclass gratuita y mis recursos, y cuando te sientas lista para un apoyo más "
        "profundo, aquí estaré.\n\n"
        "{register_link}"
    ),

    # Partner / decision-maker (Phase 6)
    Action.PARTNER_CHECK: (
        "Como la fertilidad suele ser una decisión de equipo, recomiendo mucho que ambos "
        "estén en la llamada para que todos estemos alineados desde el principio. ¿Estás en "
        "esto con tu pareja, o lo estás llevando por tu cuenta?"
    ),
    Action.PARTNER_ASK_JOIN: "¿Tu pareja podría acompañarte en la llamada?",
    Action.PARTNER_PUSHBACK: (
        "Usaremos esta reunión para ver si somos un buen equipo para trabajar juntas y "
        "ayudarte a quedar embarazada. Por eso necesitamos que estén todas las personas que "
        "toman la decisión. Si tu pareja decide contigo, lo necesitamos ahí. Si tú eres la "
        "única que toma la decisión y puedes decidir sobre esta inversión en tu embarazo, "
        "eres bienvenida a venir sola, lista para tomar decisiones poderosas para ti y tu "
        "familia."
    ),

    # Booking (Phase 7)
    Action.SEND_BOOKING: (
        "Por lo que me cuentas, creo que vale la pena que hables con mi equipo para ver si "
        "puedo ayudarte y cómo.\n\n"
        "Aquí tienes el enlace para agendar tu llamada: {booking_link}\n\n"
        "Por favor elige un horario en el que puedan estar ambos si tu pareja es parte de la "
        "decisión. Si estás en esto por tu cuenta, por supuesto puedes venir sola.\n\n"
        "Cuando agendes, por favor sigue los siguientes pasos con atención para que podamos "
        "confirmar tu llamada."
    ),
    Action.BOOKING_IS_IT_SONIA: (
        "La primera llamada es con mi equipo, para entender bien tu situación y ver si esto "
        "es lo indicado para ti. Si todas decidimos que somos un gran equipo para trabajar "
        "juntas, yo seré tu única coach dentro del programa y estaré contigo en cada paso "
        "del camino."
    ),
    Action.BOOKING_CALL_PROCESS: (
        "La primera sesión es para conocernos, ver dónde estás y si puedo ayudarte a lograr "
        "tu sueño y cómo.\n\n"
        "Soy coach de fertilidad con un 70% de éxito entre miles de parejas en todo el "
        "mundo. Mi éxito se debe a 2 factores: 1. mi programa es realmente efectivo. "
        "2. soy muy selectiva.\n\n"
        "En la sesión te diré si puedo cambiar tu vida o no. Si puedo, te daré opciones y "
        "toda la información para que tomes una decisión totalmente informada sobre si "
        "quieres trabajar conmigo o no."
    ),

    # Advice / price / misc deflections
    Action.ADVICE_DEFLECT: (
        "Sería muy cuidadosa dándote consejos genéricos sin entender tu situación completa, "
        "porque la fertilidad depende mucho de cada caso. El mejor siguiente paso sería "
        "hablar con mi equipo para conocerte bien, entender qué has intentado y ver si puedo "
        "ayudarte y cómo. ¿Puedo preguntarte cuánto tiempo llevan intentando y qué han hecho "
        "hasta ahora?"
    ),
    Action.ADVICE_DEFLECT_LATE: (
        "Sería muy cuidadosa dándote consejos genéricos sin entender tu situación completa, "
        "porque la fertilidad depende mucho de cada caso. El mejor siguiente paso es hablar "
        "con mi equipo para revisar tu caso específico y ver si puedo ayudarte y cómo."
    ),
    Action.ADVICE_DEFLECT_PUSH: (
        "Normalmente hay muchos factores involucrados y depende de tu caso específico. Yo "
        "miro el panorama completo, incluyendo nutrición, inflamación, estilo de vida, "
        "hormonas, estrés y mucho más, pero no querría asumir qué es lo más importante para "
        "ti sin entender primero tu situación. ¿Cuánto tiempo llevan intentando y qué han "
        "probado hasta ahora?"
    ),
    Action.ADVICE_DEFLECT_PUSH_LATE: (
        "Normalmente hay muchos factores involucrados y realmente depende de tu caso "
        "específico. Miro el panorama completo en lugar de un solo síntoma o análisis, pero "
        "el paso más útil es una conversación donde revisemos tu situación como corresponde."
    ),
    Action.PRICE_DEFLECT: (
        "Depende del nivel de apoyo que cada persona necesita, así que no doy un número al "
        "azar antes de entender tu situación. El primer paso es ver si realmente puedo "
        "ayudarte y qué tipo de apoyo tendría sentido para ti. ¿Puedo preguntarte cuánto "
        "tiempo llevan intentando y qué han hecho hasta ahora?"
    ),
    Action.PRICE_DEFLECT_LATE: (
        "Depende del nivel de apoyo que cada persona necesita, así que no doy un número al "
        "azar antes de entender tu situación. Déjame asegurarme primero de que esto es lo "
        "indicado para ti, y de ahí revisamos todo lo demás."
    ),
    Action.PRICE_RANGE: (
        "Los programas normalmente van de {price_range_es} según el nivel de apoyo. Lo más "
        "importante es asegurarnos de que este sea el apoyo correcto para tu cuerpo y tu "
        "situación."
    ),
    Action.PRICE_RANGE_FIRM: (
        "Como te comenté, realmente depende y está dentro de ese rango de {price_range_es}. "
        "La mejor forma de saber qué necesitarías es en la llamada, donde adaptamos todo a "
        "tu situación."
    ),
    Action.PHONE_NUMBER_DEFLECT: (
        "Solo tomo llamadas para citas confirmadas. Si quieres hablar conmigo o con mi "
        "equipo, puedes agendarlo reservando tu llamada. Avísame si quieres que te envíe el "
        "enlace para agendar."
    ),
    Action.MASTERCLASS_SEND: (
        "¡Hola hermosa! Gracias por tu interés en lo que hago. :) Aquí tienes el enlace. "
        "{register_link}\n\n"
        "Cuéntame qué te pareció después de verla."
    ),
    Action.SOCIAL_PROOF: (
        "Llevo más de 16 años haciendo este trabajo y he ayudado a dar la bienvenida a más "
        "de 700 bebés, así que soy muy selectiva para asegurarme de que esto sea lo indicado "
        "antes de invitar a alguien a una llamada."
    ),
    Action.PAYING_TWICE: (
        "Podría haber algo de información parecida, pero ofrecemos mucho más que consejos. "
        "Tenemos nutrición personalizada, sesiones de coaching privadas y grupales, una "
        "amplia fuente de recursos educativos y una gran comunidad de mujeres con tu misma "
        "meta que se apoyan entre sí durante este camino."
    ),
    Action.IVF_ONLY_OFFER: (
        "Si la FIV es el mejor camino para ti médicamente, aún puedo ayudarte optimizando "
        "tus probabilidades de éxito. Acompaño el panorama completo de la fertilidad y la "
        "preparación para la FIV con un enfoque holístico, altamente personalizado y "
        "respaldado por la investigación. ¿Es algo que te interesa?"
    ),
    Action.TROUBLE_BOOKING: (
        "Lo siento. ¿Viste algún mensaje de error? ¿Puedes enviarme una captura de pantalla "
        "para revisarlo de mi lado? Deberías recibir un correo de confirmación después de "
        "agendar y ver la página de confirmación.\n\n"
        "Si no viste esa página, por favor vuelve a agendar."
    ),
    Action.NO_MONEY: (
        "Gracias por ser honesta. Si en algún momento te sientes totalmente lista para "
        "comprometerte con esto, aquí estaré para ti."
    ),

    # Out-of-scope clarifying questions
    Action.ASK_BOTH_TUBES: "¿Están bloqueadas ambas trompas, o solo una?",
    Action.ASK_MENOPAUSE_REASON: (
        "Gracias por contarme. ¿Puedo preguntarte cuál es la razón por la que ya no te llega "
        "el periodo?"
    ),
    Action.ASK_MENOPAUSE_AGE: "Entiendo. ¿Y puedo preguntarte cuántos años tienes?",

    # Out-of-scope terminal messages (paired with human takeover)
    Action.OOS_BOTH_TUBES: (
        "Si ambas trompas están completamente bloqueadas, el coaching no puede hacer que el "
        "óvulo pase por las trompas, y no lo presentaría como algo que el coaching por sí "
        "solo pueda resolver. No soy una clínica de fertilidad y no realizo FIV. En este "
        "caso, solo puedo ayudarte si también estás haciendo FIV, porque puedo apoyarte "
        "optimizando tu cuerpo, la inflamación, las hormonas, la calidad de tus óvulos, la "
        "nutrición, tu sistema nervioso y tu preparación para la FIV, para mejorar tus "
        "probabilidades de éxito."
    ),
    Action.OOS_MENOPAUSE: (
        "Gracias por ser tan transparente conmigo. Por lo que me cuentas, esto puede estar "
        "fuera del alcance de lo que puedo ayudar a través del coaching. Lo siento mucho y "
        "te deseo lo mejor."
    ),
    Action.OOS_AGE_OVER_46: (
        "Gracias por contármelo. Como la edad puede cambiar lo que es realista y qué tipo de "
        "apoyo es apropiado, quiero revisar esto con cuidado antes de orientarte en una "
        "dirección equivocada."
    ),
    Action.OOS_DEAF: (
        "Lo siento, pero nuestras reuniones y nuestro programa no serían adecuados para lo "
        "que necesitas. Lo lamento mucho y te deseo lo mejor."
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

# Spanish counterparts of the banks above (same keys/order). DRAFT copy,
# pending client review.
EMPATHY_VARIANTS_ES = {
    "hopeless": (
        "Siento mucho que estés pasando por esto. Puede ser muy difícil, pero no estás sola "
        "en este camino. Estoy aquí para ayudarte."
    ),
    "neutral": "Admiro lo comprometida que estás con este camino. Gracias por contarme.",
    "misfortune": (
        "Siento mucho que estés pasando por esto. Entiendo lo difícil que debe haber sido, "
        "pero el hecho de que sigas adelante a pesar de estos desafíos me dice que eres "
        "fuerte y resiliente. Gracias por contarme."
    ),
}

DISCOVERY_QUESTIONS_ES = {
    "trying_duration": "¿Cuánto tiempo llevan intentando y qué han probado hasta ahora?",
    "age": "¿Cuántos años tienes?",
    "treatment_path": "¿Están intentando de forma natural, haciendo IIU, FIV, o todavía lo están decidiendo?",
    "done_testing": "¿Ya se han hecho estudios de fertilidad?",
    "diagnosis": "¿Algún doctor les ha dado un diagnóstico específico?",
}

AFFIRMATIONS_ES = [
    "Gracias por contarme. Eso me da un mejor panorama.",
    "Entendido, eso me ayuda.",
    "Tiene sentido.",
    "Gracias por ser honesta conmigo.",
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

def render(action: Action, cfg: dict | None = None, language: str = "en") -> str:
    """Render a scripted action's verbatim text with config placeholders filled.

    `language="es"` renders the Spanish template, falling back to English for
    actions without a Spanish version (dormant ones). Raises KeyError on an
    unknown action, and asserts no placeholder was left unfilled (so a typo'd
    template fails loudly in tests, never in production).
    """
    registry = SCRIPTS_ES if language == "es" else SCRIPTS
    template = registry.get(action) or SCRIPTS.get(action)
    if template is None:
        raise KeyError(f"No script template for action {action!r}")
    text = template.format(**placeholders(cfg))
    assert "{" not in text and "}" not in text, (
        f"Unfilled placeholder in rendered {action!r}: {text!r}"
    )
    return text


def render_followup(name: str, cfg: dict | None = None) -> str:
    """Render a follow-up sequence message by name."""
    if name not in FOLLOWUPS:
        raise KeyError(f"No follow-up named {name!r}")
    return FOLLOWUPS[name].format(**placeholders(cfg))
