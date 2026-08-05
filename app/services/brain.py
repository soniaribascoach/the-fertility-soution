"""The brain: one turn in, one reply out. Nothing is implemented yet.

This file is deliberately the entire contract between the app and whatever
reasons about a conversation. The app around it - webhook, batching, ManyChat,
storage, admin - is unchanged and working; everything that decided what to SAY
was deleted with the v14 routed brain (`git show v14-final` to read it).

Until `run_turn` is written the bot stays silent: it returns no reply and takes
no side effects, which is the safe failure for a live DM. It does NOT pause the
lead or tag her, so nothing is destroyed while the new brain is being built.

Two things the app needs from any implementation:

  * a `TurnResult`, whose fields ARE the side effects the worker applies -
    reply, pause, tag, and the lead state to persist;
  * `lead_state`, an arbitrary JSON dict owned entirely by the brain. The app
    stores and returns it and never looks inside. Its shape is the new brain's
    to define; nothing outside this file has an opinion about it.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ManyChat tag applied whenever a turn needs a human. Set in their dashboard.
HUMAN_REVIEW_TAG = 86596410


@dataclass
class TurnResult:
    """What one turn produced, and what the worker should do about it."""
    reply_text: Optional[str] = None      # None means say nothing
    lead_state: dict = field(default_factory=dict)
    pause: bool = False                   # stop the AI; a human takes over
    pause_reason: Optional[str] = None
    add_tag: bool = False                 # flag her in ManyChat
    qualified: bool = False               # tag as qualified rather than review
    action: Optional[str] = None          # short label for the log
    usage: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)
    trace: dict = field(default_factory=dict)


async def run_turn(
    openai_client: AsyncOpenAI,
    history: list[dict],
    cfg: dict,
    lead_state: Optional[dict] = None,
    *,
    ig_user_id: str = "",
    new_texts: Optional[list[str]] = None,
) -> TurnResult:
    """Read the conversation, decide the reply.

    `history` is the whole conversation as `{"role": "user"|"assistant",
    "content": str}`, oldest first. `new_texts` is the batch of messages she just
    sent (they are already the tail of `history`). `cfg` is the `app_config`
    table as a flat dict - links, CTA keywords, blocklists.
    """
    logger.warning("run_turn is not implemented; staying silent for %s", ig_user_id)
    return TurnResult(lead_state=lead_state or {}, action="NOT_IMPLEMENTED")
