from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import conversation as conv_repo
from app.services.ai import (
    check_medical_blocklist,
    compute_score,
    generate_reply,
)
from app.services.manychat import ManyChatService
from openai import AsyncOpenAI


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
    2. Load history + prior tags
    3. Save user message
    4. Generate AI reply + compute new score from tags
    5. Apply tag changes to ManyChat
    6. Save assistant reply
    7. Send booking link or regular message
    """
    # 1. Medical blocklist — flag for human review, no reply sent
    if check_medical_blocklist(user_message, cfg):
        await conv_repo.save_message(db, instagram_user_id, "user", user_message)
        await conv_repo.save_message(db, instagram_user_id, "system", "[MEDICAL_FLAGGED]")
        await mc_svc.add_tag(instagram_user_id, "needs_human_review")
        return ""

    # 2. Load history + prior tags
    history = await conv_repo.get_history(db, instagram_user_id)
    prior_tags = await conv_repo.get_latest_tags(db, instagram_user_id)

    # 3. Save user message
    await conv_repo.save_message(db, instagram_user_id, "user", user_message)

    # 4. Generate AI reply
    clean_reply, new_tags, _ = await generate_reply(
        user_message=user_message,
        history=history,
        cfg=cfg,
        user_first_name=first_name,
        openai_client=openai_client,
    )

    new_score = compute_score(new_tags)

    # 5. Apply tag changes to ManyChat
    await mc_svc.update_contact_tags(instagram_user_id, prior_tags, new_tags)

    # 6. Save assistant reply with updated score and tags
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
            db, instagram_user_id, "assistant",
            clean_reply + " [BOOKING_SENT]",
            lead_score=new_score,
            contact_tags=new_tags,
        )
    else:
        await conv_repo.save_message(
            db, instagram_user_id, "assistant",
            clean_reply,
            lead_score=new_score,
            contact_tags=new_tags,
        )
        await mc_svc.send_text_message(instagram_user_id, clean_reply)

    return clean_reply
