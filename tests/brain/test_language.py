"""Language handling (live, real extractor + full run_turn).

English and Spanish are supported end-to-end; anything else gets SILENCE +
pause + review tag (never a decline the lead can't read). Deterministic
guarantees live in test_controller.py; these tests cover the LLM side:
does the extractor actually read Spanish and classify languages correctly.

NOTE: tests use French/German for the unsupported case, never Portuguese —
Portuguese/Spanish confusion is a known model weakness and would be flaky.

Run with: pytest -m live tests/brain/test_language.py
"""
import pytest

from app.services.brain import run_turn
from app.services.brain.constants import Action
from app.services.brain.extractor import extract

pytestmark = pytest.mark.live

CFG = {
    "phase1_cta_keywords": "AMH",
    "phase1_opening_message": "opener",
    "booking_link": "https://www.thefertilitysolution.com/free-call",
    "medical_blocklist": "", "human_takeover_triggers": "", "default_closer": "natalia",
}

UNSUPPORTED = [
    ("french", "Bonjour, j'essaie de tomber enceinte depuis deux ans, pouvez-vous m'aider ?"),
    ("german", "Hallo, ich versuche seit zwei Jahren schwanger zu werden, können Sie mir helfen?"),
]


@pytest.mark.parametrize("label,message", UNSUPPORTED, ids=[u[0] for u in UNSUPPORTED])
async def test_unsupported_language_gets_silence(openai_client, label, message):
    r = await run_turn(openai_client, [{"role": "user", "content": message}], CFG, None, ig_user_id=label)
    assert r.reply_text is None, f"{label!r} got a reply she can't read: {r.reply_text!r}"
    assert r.pause is True and r.add_tag is True
    assert r.action == Action.UNSUPPORTED_LANGUAGE.value


async def test_extractor_reads_spanish_slots(openai_client):
    # The extractor must pull facts out of Spanish text, not just flag the language.
    history = [{"role": "user", "content": "Hola! Llevamos 2 años intentando quedar embarazada y tengo 34 años."}]
    extraction, _ = await extract(openai_client, history, {})
    assert extraction.language == "es"
    assert extraction.slot_deltas.age == 34
    assert extraction.slot_deltas.trying_duration is not None


async def test_spanish_lead_stays_in_funnel(openai_client):
    # A Spanish lead is never treated as unsupported; her language slot is
    # recorded and the reply comes back in Spanish.
    history = [{"role": "user", "content": "Hola, llevo un año intentando quedar embarazada, necesito ayuda"}]
    r = await run_turn(openai_client, history, CFG, None, ig_user_id="es_lead")
    assert r.action != Action.UNSUPPORTED_LANGUAGE.value
    assert r.lead_state["slots"]["language"] == "es"
    assert _looks_spanish(r.reply_text), r.reply_text


# --- Spanish generation --------------------------------------------------------

BOOKING_URL = "thefertilitysolution.com/free-call"
PREP_URL = "thefertilitysolution.com/call-scheduled"

_ES_MARKERS = (" que ", " para ", " con ", " estás", " tu ", " te ", "¿", "años", " es ", " y ")
_EN_MARKERS = (" the ", " you ", " your ", " is ", " are ", " with ", " and ", " what ")


def _looks_spanish(text):
    """Cheap heuristic: Spanish stopwords present, English stopwords absent."""
    t = f" {(text or '').lower()} "
    es_hits = sum(m in t for m in _ES_MARKERS)
    en_hits = sum(m in t for m in _EN_MARKERS)
    return es_hits >= 2 and en_hits == 0


async def _say(client, history, lead_state, text, ig="es_funnel"):
    history.append({"role": "user", "content": text})
    result = await run_turn(client, history, CFG, lead_state, ig_user_id=ig)
    if result.reply_text:
        history.append({"role": "assistant", "content": result.reply_text})
    return result


async def test_spanish_full_funnel_books_only_when_qualified(openai_client):
    history = []
    state = None

    turns = [
        "Hola! Tengo 38 años, llevamos 2 años intentando y un ciclo de FIV que no funcionó",
        "Sinceramente es un 9, es mi prioridad número uno ahora mismo",
        "Sí, ese enfoque holístico y personalizado es exactamente lo que estoy buscando",
        "Sí, entiendo que es un programa pago y estoy abierta a invertir si es lo correcto",
        "Estoy haciendo esto sola, como madre soltera por elección",
    ]

    booked_turn = None
    for i, msg in enumerate(turns, start=1):
        r = await _say(openai_client, history, state, msg)
        state = r.lead_state
        assert state["slots"]["language"] == "es", f"language flipped on turn {i}"
        if r.action == Action.SEND_BOOKING.value:
            booked_turn = i
            assert BOOKING_URL in r.reply_text
            assert _looks_spanish(r.reply_text.replace(BOOKING_URL, "")), r.reply_text
            break
        assert BOOKING_URL not in (r.reply_text or ""), f"link leaked on turn {i}: {r.reply_text}"
        assert _looks_spanish(r.reply_text), f"non-Spanish reply on turn {i}: {r.reply_text!r}"

    assert booked_turn is not None, f"never booked; phase={state['phase']}, slots={state['slots']}"
    assert state["flags"]["booking_sent"] is True

    # Post-booking must stay Spanish. These scripts were dormant until v1.2 and
    # render() falls back to English for any action missing a Spanish twin, so a
    # missing translation would silently ship English to a Spanish lead.
    r = await _say(openai_client, history, state, "¡Ya agendé la llamada para el martes!")
    state = r.lead_state
    assert r.action == Action.POST_BOOKING_ASK_EMAIL.value, f"got {r.action}: {r.reply_text}"
    assert PREP_URL in r.reply_text, f"prep page missing: {r.reply_text}"
    assert _looks_spanish(r.reply_text.replace(PREP_URL, "")), r.reply_text

    r = await _say(openai_client, history, state, "sara.jimenez@gmail.com")
    assert r.action == Action.POST_BOOKING_ACK.value, f"got {r.action}: {r.reply_text}"
    assert _looks_spanish(r.reply_text), r.reply_text
    assert r.pause_reason == "booked_pending_verification"


async def test_language_switch_mid_conversation_sticks(openai_client):
    history = []
    r1 = await _say(openai_client, history, None,
                    "Hi, we've been trying for a year and I'm not sure what to do next",
                    ig="switcher")
    assert r1.lead_state["slots"]["language"] == "en"

    r2 = await _say(openai_client, history, r1.lead_state,
                    "perdón, ¿podemos seguir en español? me siento más cómoda así",
                    ig="switcher")
    assert r2.lead_state["slots"]["language"] == "es"
    assert _looks_spanish(r2.reply_text), r2.reply_text

    # A short ambiguous turn must not flip the sticky language back.
    r3 = await _say(openai_client, history, r2.lead_state, "ok", ig="switcher")
    assert r3.lead_state["slots"]["language"] == "es"
    if r3.reply_text:
        assert _looks_spanish(r3.reply_text), r3.reply_text


async def test_english_cta_then_spanish_reply_switches_funnel(openai_client):
    # There are no Spanish CTA keywords: a lead comes in via an English
    # campaign keyword, then reveals her language with her first real message.
    history = []
    r1 = await _say(openai_client, history, None, "AMH", ig="es_after_cta")
    assert r1.action == Action.PHASE1_OPENING.value
    assert r1.lead_state["slots"]["language"] is None  # keyword carries no signal

    r2 = await _say(openai_client, history, r1.lead_state,
                    "Hola! Llevamos un año intentando quedar embarazada y nada todavía",
                    ig="es_after_cta")
    assert r2.lead_state["slots"]["language"] == "es"
    assert _looks_spanish(r2.reply_text), r2.reply_text


async def test_spanish_oos_decline_is_verbatim_spanish(openai_client):
    from app.services.brain import scripts

    history = [{"role": "user", "content":
                "Hola, tengo 49 años y quiero quedar embarazada, ¿me puedes ayudar?"}]
    r = await run_turn(openai_client, history, CFG, None, ig_user_id="es_oos")
    assert r.action == Action.OOS_AGE_OVER_46.value
    assert r.pause is True
    assert r.reply_text == scripts.render(Action.OOS_AGE_OVER_46, CFG, "es")
