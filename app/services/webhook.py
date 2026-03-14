from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import conversation as conv_repo
from app.services.ai import (
    MEDICAL_DEFLECTION,
    check_medical_blocklist,
    generate_reply,
)
from app.services.manychat import ManyChatService
from openai import AsyncOpenAI


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


async def handle_contact(
    instagram_user_id: str,
    user_message: str,
    first_name: str | None,
    db: AsyncSession,
    cfg: dict,
    openai_client: AsyncOpenAI,
    mc_svc: ManyChatService,
) -> str:
    """
    Orchestrates the full contact flow:
    1. Medical blocklist check
    2. Load history + prior score
    3. Save user message
    4. Generate AI reply + compute new score
    5. Save assistant reply
    6. Send booking link or regular message
    """
    # 1. Medical blocklist — static deflection, no AI call
    if check_medical_blocklist(user_message, cfg):
        await conv_repo.save_message(db, instagram_user_id, "user", user_message)
        await conv_repo.save_message(db, instagram_user_id, "assistant", MEDICAL_DEFLECTION)
        await mc_svc.send_text_message(instagram_user_id, MEDICAL_DEFLECTION)
        return MEDICAL_DEFLECTION

    # 2. Load history + prior score
    history = await conv_repo.get_history(db, instagram_user_id)
    prior_score = await conv_repo.get_latest_score(db, instagram_user_id)

    # 3. Save user message
    await conv_repo.save_message(db, instagram_user_id, "user", user_message)

    # 4. Generate AI reply
    clean_reply, delta = await generate_reply(
        user_message=user_message,
        history=history,
        cfg=cfg,
        user_first_name=first_name,
        openai_client=openai_client,
    )

    new_score = _clamp(prior_score + delta)

    # 5. Save assistant reply with updated score
    try:
        threshold = int(cfg.get("score_threshold", "70"))
    except (ValueError, TypeError):
        threshold = 70

    already_sent = await conv_repo.has_received_booking_link(db, instagram_user_id)

    if new_score >= threshold and not already_sent:
        booking_url = cfg.get("booking_link", "")
        await mc_svc.send_booking_link(instagram_user_id, booking_url, first_name)
        # Mark that the booking link was sent by appending a marker to the stored content
        await conv_repo.save_message(
            db, instagram_user_id, "assistant", clean_reply + " [BOOKING_SENT]", new_score
        )
    else:
        await conv_repo.save_message(db, instagram_user_id, "assistant", clean_reply, new_score)
        await mc_svc.send_text_message(instagram_user_id, clean_reply)

    return clean_reply
