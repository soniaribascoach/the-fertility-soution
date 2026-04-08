from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.repositories import conversation as conv_repo
from app.repositories import simulation as sim_repo
from app.services.ai import (
    check_human_takeover_triggers,
    check_medical_blocklist,
    compute_score,
    generate_reply,
)
from app.services.router import build_route_context


async def simulate_contact(
    db: AsyncSession,
    openai_client: AsyncOpenAI,
    session_id: str,
    message: str,
    first_name: str | None,
    cfg: dict,
) -> dict:
    """
    Runs the full AI pipeline for a simulated conversation.
    Uses sim_{session_id} as instagram_user_id to isolate from real users.
    Never calls ManyChat or sends booking links.
    """
    sim_user_id = f"sim_{session_id}"

    # Medical blocklist check
    if check_medical_blocklist(message, cfg):
        deflection_msg = cfg.get("medical_deflection", "").strip()
        await conv_repo.save_message(db, sim_user_id, "user", message)
        await conv_repo.save_message(db, sim_user_id, "system", "[MEDICAL_FLAGGED]")
        await sim_repo.increment_message_count(db, session_id)
        return {
            "reply": deflection_msg,
            "tags": {}, "score": 0, "cost": 0.0,
            "prompt_tokens": 0, "completion_tokens": 0, "model": "",
            "blocked": True, "block_reason": "medical",
        }

    # Human takeover check
    if check_human_takeover_triggers(message, cfg):
        await conv_repo.save_message(db, sim_user_id, "user", message)
        await conv_repo.save_message(db, sim_user_id, "system", "[TAKEOVER_FLAGGED]")
        await sim_repo.increment_message_count(db, session_id)
        return {
            "reply": "[Takeover trigger detected — would hand off to human team in production]",
            "tags": {}, "score": 0, "cost": 0.0,
            "prompt_tokens": 0, "completion_tokens": 0, "model": "",
            "blocked": True, "block_reason": "takeover",
        }

    # Load history + prior state
    history = await conv_repo.get_history(db, sim_user_id)
    prior_tags  = await conv_repo.get_latest_tags(db, sim_user_id)
    prior_score = await conv_repo.get_latest_score(db, sim_user_id)

    try:
        threshold = int(cfg.get("score_threshold", "70"))
    except (ValueError, TypeError):
        threshold = 70

    already_sent = await conv_repo.has_received_booking_link(db, sim_user_id)

    # Build route context
    route = await build_route_context(
        user_message=message,
        history=history,
        cfg=cfg,
        prior_tags=prior_tags,
        current_score=prior_score,
        threshold=threshold,
        openai_client=openai_client,
        already_sent=already_sent,
    )

    # Save user message
    await conv_repo.save_message(db, sim_user_id, "user", message)

    # Generate AI reply with targeted context
    result = await generate_reply(
        user_message=message,
        history=history,
        cfg=cfg,
        user_first_name=first_name,
        openai_client=openai_client,
        route=route,
    )
    new_score = compute_score(result.tags)

    booking_link_fired = route.booking_fires_now
    booking_url = cfg.get("booking_link", "") if booking_link_fired else ""

    content_to_save = result.reply + " [BOOKING_SENT]" if booking_link_fired else result.reply
    await conv_repo.save_message(
        db, sim_user_id, "assistant", content_to_save,
        lead_score=new_score,
        contact_tags=result.tags,
        token_cost=result.cost,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        ai_model=result.model,
    )

    await sim_repo.increment_message_count(db, session_id)

    bubbles = [b.strip() for b in result.reply.split("\n\n") if b.strip()]

    return {
        "reply": result.reply,
        "bubbles": bubbles if bubbles else [result.reply],
        "tags": result.tags,
        "score": new_score,
        "cost": result.cost,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "model": result.model,
        "blocked": False,
        "block_reason": "",
        "booking_link_fired": booking_link_fired,
        "booking_url": booking_url,
    }
