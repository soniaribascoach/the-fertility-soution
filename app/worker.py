import asyncio
import copy
import logging
import random
import re

from app.db.database import AsyncSessionLocal
from app.repositories.config import get_all_config
from app.repositories.conversation import get_history, get_last_assistant_time, save_message
from app.repositories.pending_message import (
    get_locked_batch,
    get_users_ready_to_process,
    lock_batch,
    mark_batch_processed,
    release_stale_locks,
)
from app.repositories.user_state import (
    get_or_create_state,
    is_ai_paused,
    pause_ai,
    get_lead_state,
    save_lead_state,
)
from app.services.ai_pipeline import generate_reply, check_phase1
from app.services.brain import run_turn, HUMAN_REVIEW_TAG
from app.services.few_shots import get_few_shot_scenarios
from app.services.message_splitter import split_reply
from app.services.output_parser import parse_ai_output
from app.services.typing_delay import calculate_delay
from config import settings, DEFAULT_BRAIN

logger = logging.getLogger(__name__)

_processing_users: set[str] = set()
_MEDIA_URL_RE = re.compile(r"^https?://\S+$")
_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def _is_media_url(text: str) -> bool:
    return bool(_MEDIA_URL_RE.match(text))


def contains_email(texts) -> bool:
    return any(_EMAIL_RE.search(t or "") for t in texts)


async def _is_booking_email(db, ig_user_id: str, rows) -> bool:
    """The one message a paused-after-booking lead may still get a reply to.

    After the booking link the AI pauses on anything that is not "I booked" or an
    email. So a lead who says "ok thanks!" and only THEN sends her email would be
    skipped and the email lost forever. If she is paused for exactly that reason
    and the message carries an email, let the turn run so the brain captures it
    and confirms. Every other paused lead stays paused.
    """
    state = await get_or_create_state(db, ig_user_id)
    if state.pause_reason != "qualified_link_sent":
        return False
    return contains_email(r.content for r in rows)


async def start_worker(app_state) -> None:
    logger.info("Background worker starting")
    async with AsyncSessionLocal() as db:
        await release_stale_locks(db)

    while True:
        await asyncio.sleep(settings.worker_poll_interval)
        try:
            await _poll_once(app_state)
        except Exception:
            logger.exception("Worker poll error")


async def _poll_once(app_state) -> None:
    async with AsyncSessionLocal() as db:
        await release_stale_locks(db)
        ready = await get_users_ready_to_process(db, settings.debounce_seconds)

    for ig_user_id in ready:
        if ig_user_id not in _processing_users:
            _processing_users.add(ig_user_id)
            asyncio.create_task(_handle_conversation(ig_user_id, app_state))


async def _handle_conversation(ig_user_id: str, app_state) -> None:
    try:
        if settings.debounce_extra_seconds > 0:
            await asyncio.sleep(random.uniform(0, settings.debounce_extra_seconds))

        async with AsyncSessionLocal() as db:
            # The batch is read BEFORE the pause check: a lead paused right after
            # booking still gets her email captured (see _is_booking_email), and
            # that decision needs the message text.
            await lock_batch(db, ig_user_id)
            rows = await get_locked_batch(db, ig_user_id)
            if not rows:
                return

            if await is_ai_paused(db, ig_user_id):
                if not await _is_booking_email(db, ig_user_id, rows):
                    logger.info("AI paused for user %s — skipping", ig_user_id)
                    await mark_batch_processed(db, ig_user_id)
                    return
                logger.info("Paused lead %s sent a booking email — capturing it", ig_user_id)

            # Duplicate guard: skip if an assistant reply was already sent after these messages
            last_user_msg_time = max(r.received_at for r in rows).replace(tzinfo=None)
            last_reply_time = await get_last_assistant_time(db, ig_user_id)
            if last_reply_time and last_reply_time > last_user_msg_time:
                logger.info("Reply already sent for user %s — skipping duplicate", ig_user_id)
                await mark_batch_processed(db, ig_user_id)
                return

            manychat_contact_id = rows[-1].manychat_contact_id

            batch_texts = [r.content.lower() for r in rows]
            cfg = await get_all_config(db)

            # Behind a config flag for safe rollout:
            #   "routed" - intent classifier + router + knowledge (current work)
            #   "funnel" - the qualification-funnel brain
            #   anything else - the legacy monolith
            # Rollback is this one field in AppConfig, with no deploy.
            brain_version = (cfg.get("brain_version") or DEFAULT_BRAIN).strip().lower()
            if brain_version in ("funnel", "routed"):
                await _run_brain_turn(
                    db, ig_user_id, manychat_contact_id, cfg, app_state,
                    [r.content for r in rows], routed=(brain_version == "routed"),
                )
                await mark_batch_processed(db, ig_user_id)
                logger.info("Processed conversation (%s) for user %s",
                            brain_version, ig_user_id)
                return

            # Shadow mode is only meaningful for the two brains above; the legacy
            # monolith keeps no lead state to run the routed brain against.

            if any(_is_media_url(txt) for txt in batch_texts):
                logger.info("Media message detected (batch) for user %s", ig_user_id)
                await pause_ai(db, ig_user_id, "media_message")
                await mark_batch_processed(db, ig_user_id)
                await app_state.manychat_client.add_tag(manychat_contact_id, 86596410)
                return

            blocklist = [p.strip().lower() for p in cfg.get("medical_blocklist", "").split("\n") if p.strip()]
            if blocklist and any(any(phrase in txt for phrase in blocklist) for txt in batch_texts):
                deflection = cfg.get("medical_deflection", "").strip()
                logger.info("Medical blocklist triggered (batch) for user %s", ig_user_id)
                if deflection:
                    await app_state.manychat_client.send_message(manychat_contact_id, deflection)
                await pause_ai(db, ig_user_id, "medical_deflection")
                await mark_batch_processed(db, ig_user_id)
                await app_state.manychat_client.add_tag(manychat_contact_id, 86596410)
                return

            handover_triggers = [t.strip().lower() for t in cfg.get("human_takeover_triggers", "").split("\n") if t.strip()]
            if handover_triggers and any(any(trigger in txt for trigger in handover_triggers) for txt in batch_texts):
                logger.info("Human handover triggered (batch) for user %s", ig_user_id)
                await pause_ai(db, ig_user_id, "human_handover")
                await mark_batch_processed(db, ig_user_id)
                await app_state.manychat_client.add_tag(manychat_contact_id, 86596410)
                return

            history = await get_history(db, ig_user_id, limit=20)
            history_dicts = [{"role": r.role, "content": r.content} for r in history]

            # Phase 1 — CTA keyword bypass (first ever message only)
            opening = check_phase1(cfg, history_dicts)
            if opening:
                logger.info("Phase 1 CTA keyword triggered for user %s", ig_user_id)
                chunks = split_reply(opening)
                delay = calculate_delay(chunks[0], settings.max_typing_delay)
                await asyncio.sleep(delay)
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        await asyncio.sleep(calculate_delay(chunk, settings.max_typing_delay))
                    await app_state.manychat_client.send_message(manychat_contact_id, chunk)
                await save_message(db, ig_user_id, "assistant", opening)
                await mark_batch_processed(db, ig_user_id)
                return

            raw_text, usage = await generate_reply(
                db=db,
                openai_client=app_state.openai_client,
                few_shot_scenarios=get_few_shot_scenarios(app_state),
                ig_user_id=ig_user_id,
                messages=history_dicts,
                cfg=cfg,
            )

            parsed = parse_ai_output(raw_text)

            await save_message(
                db,
                ig_user_id,
                "assistant",
                raw_text,
                token_cost=usage.get("token_cost"),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                ai_model=usage.get("ai_model"),
            )

            if parsed.clean_text:
                chunks = split_reply(parsed.clean_text)
                delay = calculate_delay(chunks[0], settings.max_typing_delay)
                await asyncio.sleep(delay)
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        await asyncio.sleep(calculate_delay(chunk, settings.max_typing_delay))
                    await app_state.manychat_client.send_message(manychat_contact_id, chunk)

            await mark_batch_processed(db, ig_user_id)
            logger.info("Processed conversation for user %s", ig_user_id)

    except Exception:
        logger.exception("Error handling conversation for user %s", ig_user_id)
    finally:
        _processing_users.discard(ig_user_id)


async def _send_bubbles(app_state, manychat_contact_id: str, text: str) -> None:
    chunks = split_reply(text)
    await asyncio.sleep(calculate_delay(chunks[0], settings.max_typing_delay))
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(calculate_delay(chunk, settings.max_typing_delay))
        await app_state.manychat_client.send_message(manychat_contact_id, chunk)


async def _run_brain_turn(db, ig_user_id, manychat_contact_id, cfg, app_state,
                          batch_texts, *, routed: bool = False) -> None:
    """Run a brain for one batch and apply its side effects.

    Both brains share this function because they share `TurnResult`; only the
    turn implementation and the knowledge lookup differ.
    """
    from app.repositories.brain_turn import save_turn

    history = await get_history(db, ig_user_id, limit=20)
    history_dicts = [{"role": r.role, "content": r.content} for r in history]
    lead_state = await get_lead_state(db, ig_user_id)
    lead_message = "\n".join(batch_texts)

    if routed:
        result = await _routed_turn(db, app_state, history_dicts, cfg, lead_state,
                                    ig_user_id, batch_texts)
    else:
        result = await run_turn(
            app_state.openai_client, history_dicts, cfg, lead_state,
            ig_user_id=ig_user_id, new_texts=batch_texts,
        )

    await save_turn(db, ig_user_id, brain_version="routed" if routed else "funnel",
                    result=result, lead_message=lead_message)

    await save_lead_state(db, ig_user_id, result.lead_state)

    if result.reply_text:
        await save_message(
            db, ig_user_id, "assistant", result.reply_text,
            token_cost=result.usage.get("token_cost"),
            prompt_tokens=result.usage.get("prompt_tokens"),
            completion_tokens=result.usage.get("completion_tokens"),
            ai_model=result.usage.get("ai_model"),
        )
        await _send_bubbles(app_state, manychat_contact_id, result.reply_text)

    if result.pause:
        await pause_ai(db, ig_user_id, result.pause_reason or "human_handover")
    if result.add_tag:
        tag_id = HUMAN_REVIEW_TAG
        if result.qualified:
            qtag = (cfg.get("qualified_tag_id") or "").strip()
            tag_id = int(qtag) if qtag.isdigit() else HUMAN_REVIEW_TAG
        await app_state.manychat_client.add_tag(manychat_contact_id, tag_id)

    logger.info(
        "Brain turn for %s: action=%s phase=%s pause=%s violations=%s",
        ig_user_id, result.action, result.lead_state.get("phase"), result.pause,
        result.violations,
    )

    # Shadow: run the routed brain on the same input WITHOUT sending, so its
    # tone and handoff rate can be reviewed against real traffic before the flag
    # is flipped. Deliberately last and fully isolated - a shadow failure must
    # never affect the lead who already got her reply.
    if not routed and _flag(cfg, "brain_shadow_enabled"):
        try:
            shadow = await _routed_turn(
                db, app_state, history_dicts, cfg, lead_state, ig_user_id, batch_texts,
            )
            await save_turn(
                db, ig_user_id, brain_version="routed", result=shadow, shadow=True,
                lead_message=lead_message, live_reply=result.reply_text or "",
            )
        except Exception:
            logger.exception("Shadow turn failed for %s", ig_user_id)


def _flag(cfg: dict, key: str) -> bool:
    return (cfg.get(key) or "").strip().lower() in ("1", "true", "yes", "on")


async def _routed_turn(db, app_state, history_dicts, cfg, lead_state, ig_user_id, batch_texts):
    """Run the routed brain. Shared by the live path and shadow mode so the two
    can never drift apart."""
    from app.repositories.knowledge import get_active_knowledge
    from app.services.brain.turn import run_turn_v2

    return await run_turn_v2(
        app_state.openai_client, history_dicts, cfg,
        # Shadow must not mutate the lead's real state, and `run_turn_v2` writes
        # into what it is handed, so it gets a copy.
        copy.deepcopy(lead_state),
        ig_user_id=ig_user_id, new_texts=batch_texts,
        knowledge_entries=await get_active_knowledge(db),
    )
