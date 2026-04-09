from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import conversation as conv_repo
from app.repositories.conversation import has_sent_booking_ask
from app.services.ai import (
    check_human_takeover_triggers,
    check_medical_blocklist,
    compute_score,
    generate_reply,
)
from app.services.manychat import ManyChatService
from app.services.router import build_route_context
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
    # 1. Medical blocklist — flag for human review, send deflection only if configured
    if check_medical_blocklist(user_message, cfg):
        deflection_msg = cfg.get("medical_deflection", "").strip()
        await conv_repo.save_message(db, instagram_user_id, "user", user_message)
        await conv_repo.save_message(db, instagram_user_id, "system", "[MEDICAL_FLAGGED]")
        await mc_svc.add_tag(instagram_user_id, "needs_human_review")
        if deflection_msg:
            await mc_svc.send_text_message(instagram_user_id, deflection_msg)
        return deflection_msg

    # 1b. Human takeover triggers — hand off to team, no AI reply
    if check_human_takeover_triggers(user_message, cfg):
        await conv_repo.save_message(db, instagram_user_id, "user", user_message)
        await conv_repo.save_message(db, instagram_user_id, "system", "[TAKEOVER_FLAGGED]")
        await mc_svc.add_tag(instagram_user_id, "needs_human_review")
        handover_msg = (
            "Thank you for sharing that with me. I want to make sure you get the "
            "personal support you deserve — a member of our team will reach out to "
            "you directly very soon. \U0001f49b"
        )
        await mc_svc.send_text_message(instagram_user_id, handover_msg)
        return handover_msg

    # 2. Load history + prior tags + score
    history = await conv_repo.get_history(db, instagram_user_id)
    prior_tags = await conv_repo.get_latest_tags(db, instagram_user_id)
    prior_score = await conv_repo.get_latest_score(db, instagram_user_id)

    try:
        threshold = int(cfg.get("score_threshold", "70"))
    except (ValueError, TypeError):
        threshold = 70

    # 3. Build route context (deterministic signals + LLM classifier)
    already_sent  = await conv_repo.has_received_booking_link(db, instagram_user_id)
    already_asked = await has_sent_booking_ask(db, instagram_user_id)
    route = await build_route_context(
        user_message=user_message,
        history=history,
        cfg=cfg,
        prior_tags=prior_tags,
        current_score=prior_score,
        threshold=threshold,
        openai_client=openai_client,
        already_sent=already_sent,
        already_asked=already_asked,
    )

    # 4. Save user message
    await conv_repo.save_message(db, instagram_user_id, "user", user_message)

    # 5. Generate AI reply with targeted context
    result = await generate_reply(
        user_message=user_message,
        history=history,
        cfg=cfg,
        user_first_name=first_name,
        openai_client=openai_client,
        route=route,
    )
    clean_reply = result.reply
    new_tags    = result.tags
    new_score   = compute_score(new_tags)

    # 6. Apply tag changes to ManyChat
    await mc_svc.update_contact_tags(instagram_user_id, prior_tags, new_tags)

    # 7. Save assistant reply with updated score and tags
    ai_kwargs = dict(
        token_cost=result.cost,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        ai_model=result.model,
    )

    # Split reply into bubbles — each \n\n-separated chunk is sent as a separate message
    bubbles = [b.strip() for b in clean_reply.split("\n\n") if b.strip()]
    if not bubbles:
        bubbles = [clean_reply]

    if route.booking_fires_now:
        for bubble in bubbles:
            await mc_svc.send_text_message(instagram_user_id, bubble)
        await conv_repo.save_message(
            db, instagram_user_id, "assistant",
            clean_reply + " [BOOKING_SENT]",
            lead_score=new_score,
            contact_tags=new_tags,
            **ai_kwargs,
        )
    elif route.booking_ask_confirmation:
        for bubble in bubbles:
            await mc_svc.send_text_message(instagram_user_id, bubble)
        await conv_repo.save_message(
            db, instagram_user_id, "assistant",
            clean_reply + " [BOOKING_ASKED]",
            lead_score=new_score,
            contact_tags=new_tags,
            **ai_kwargs,
        )
    else:
        await conv_repo.save_message(
            db, instagram_user_id, "assistant",
            clean_reply,
            lead_score=new_score,
            contact_tags=new_tags,
            **ai_kwargs,
        )
        for bubble in bubbles:
            await mc_svc.send_text_message(instagram_user_id, bubble)

    return clean_reply
