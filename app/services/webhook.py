import asyncio
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import conversation as conv_repo
from app.repositories.conversation import has_sent_booking_ask, has_price_been_deflected
from app.services.ai import (
    check_human_takeover_triggers,
    check_medical_blocklist,
    compute_score,
    generate_reply,
)
from app.services.manychat import ManyChatService
from app.services.orchestrator import build_turn_directive
from app.services.router import build_route_context
from openai import AsyncOpenAI


def _bubble_delay(text: str) -> float:
    """
    Simulate human typing speed: delay before sending each bubble based on word count.
    Short: 2-3s  |  Medium: 4-6s  |  Long: 6-8s  — with ±randomisation.
    """
    words = len(text.split())
    if words < 15:
        return 2.5 + random.uniform(-0.5, 0.5)
    if words < 30:
        return 5.0 + random.uniform(-1.0, 1.0)
    return 7.0 + random.uniform(-1.5, 1.5)


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
    1. Safety gate (medical blocklist / human takeover)
    2. Load history + prior state
    3. Route context → turn directive
    4. Save user message
    5. Generate reply (writer + tagger + quality gate in parallel)
    6. Apply tag changes to ManyChat
    7. Persist assistant reply
    8. Send bubbles with human-like delays
    """
    # 1a. Medical blocklist — flag for human review, send deflection only if configured
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

    # 2. Load history + prior state
    history = await conv_repo.get_history(db, instagram_user_id)
    prior_tags   = await conv_repo.get_latest_tags(db, instagram_user_id)
    prior_score  = await conv_repo.get_latest_score(db, instagram_user_id)

    try:
        threshold = int(cfg.get("score_threshold", "70"))
    except (ValueError, TypeError):
        threshold = 70

    already_sent    = await conv_repo.has_received_booking_link(db, instagram_user_id)
    already_asked   = await has_sent_booking_ask(db, instagram_user_id)
    price_deflected = await has_price_been_deflected(db, instagram_user_id)

    # 3. Route context + turn directive
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
        price_already_deflected=price_deflected,
    )

    turn_number = sum(1 for t in history if t.role == "assistant")
    directive = build_turn_directive(route, cfg, turn_number)

    # 4. Save user message
    await conv_repo.save_message(db, instagram_user_id, "user", user_message)

    # 5. Generate AI reply (writer + tagger + quality gate)
    result = await generate_reply(
        user_message=user_message,
        history=history,
        cfg=cfg,
        user_first_name=first_name,
        openai_client=openai_client,
        directive=directive,
        prior_tags=prior_tags,
        user_id=instagram_user_id,
    )
    clean_reply = result.reply
    new_tags    = result.tags
    new_score   = compute_score(new_tags)
    # Score floor — never let the score decrease across turns
    new_score   = max(new_score, prior_score or 0)

    # 6. Apply tag changes to ManyChat
    await mc_svc.update_contact_tags(instagram_user_id, prior_tags, new_tags)

    # 7. Persist assistant reply with state flags
    ai_kwargs = dict(
        token_cost=result.cost,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        ai_model=result.model,
    )

    if directive.booking_fires_now:
        flag = " [BOOKING_SENT]"
    elif directive.booking_ask_confirmation:
        flag = " [BOOKING_ASKED]"
    elif directive.mark_price_deflected:
        flag = " [PRICE_DEFLECTED]"
    elif directive.goal in ("empathize", "empathize_qualify"):
        flag = " [EMPATHIZE]"
    else:
        flag = ""

    await conv_repo.save_message(
        db, instagram_user_id, "assistant",
        clean_reply + flag,
        lead_score=new_score,
        contact_tags=new_tags,
        **ai_kwargs,
    )

    # 8. Send bubbles with human-like typing delays
    bubbles = [b.strip() for b in clean_reply.split("\n\n") if b.strip()]
    if not bubbles:
        bubbles = [clean_reply]

    for bubble in bubbles:
        delay = _bubble_delay(bubble)
        await asyncio.sleep(delay)
        await mc_svc.send_text_message(instagram_user_id, bubble)

    return clean_reply
