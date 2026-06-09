import asyncio
import logging
import random

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
from app.repositories.user_state import is_ai_paused, pause_ai
from app.services.ai_pipeline import generate_reply
from app.services.message_splitter import split_reply
from app.services.output_parser import parse_ai_output
from app.services.typing_delay import calculate_delay
from config import settings

logger = logging.getLogger(__name__)

_processing_users: set[str] = set()


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
            if await is_ai_paused(db, ig_user_id):
                logger.info("AI paused for user %s — skipping", ig_user_id)
                await mark_batch_processed(db, ig_user_id)
                return

            await lock_batch(db, ig_user_id)
            rows = await get_locked_batch(db, ig_user_id)
            if not rows:
                return

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

            raw_text, usage = await generate_reply(
                db=db,
                openai_client=app_state.openai_client,
                few_shot_scenarios=app_state.few_shot_scenarios,
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
