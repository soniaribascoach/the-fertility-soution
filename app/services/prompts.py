"""Assembles the system prompts from `prompts_simple/*.md` plus the editable knowledge base.

The layers are static text distilled from the Operating Manual. The only thing that varies per
turn is the knowledge base: `knowledge.md` carries `{{key}}` placeholders filled from the
`app_config` table, and `[[BLOCK:name]]` sections that are included only when this turn is allowed
to use them.

That gating is the whole safety model. A turn that must not invite a booking simply never has the
booking block rendered, so the model has no link to send. Nothing inspects the generated reply.
"""
import logging
import os
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

PROMPTS_DIR = "prompts_simple"
# The layered prompts these replaced. Kept on disk for reference; only the manual experiment reads
# from here now.
LEGACY_DIR = "prompts"

WRITE_LAYERS = ("write.md", "knowledge.md")
KNOWLEDGE_LAYER = "knowledge.md"
READ_LAYER = "read.md"
SAFETY_LAYER = "safety.md"
LANGUAGE_LAYER = "language.md"
TURN_LAYER = "turn.md"

_BLOCK_RE = re.compile(r"\[\[BLOCK:(?P<name>\w+)\]\](?P<body>.*?)\[\[/BLOCK\]\]", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_SECTION_RE = re.compile(r"^## (\w+)\s*$", re.MULTILINE)


@lru_cache(maxsize=None)
def _read_layer(filename: str, directory: str = PROMPTS_DIR) -> str:
    with open(os.path.join(directory, filename), "r", encoding="utf-8") as fh:
        return fh.read()


def reload_layers() -> None:
    """Drop the cached layer files so an edit on disk takes effect without a restart."""
    _read_layer.cache_clear()


def resolve_blocks(text: str, allowed: set[str]) -> str:
    """Keep `[[BLOCK:name]]` sections whose name is allowed, delete the rest."""
    def _sub(match: re.Match) -> str:
        return match.group("body") if match.group("name") in allowed else ""
    return _BLOCK_RE.sub(_sub, text)


def fill_placeholders(text: str, values: dict) -> str:
    """Replace `{{key}}` with its config value.

    An unknown or empty key collapses to nothing rather than leaving the literal braces in the
    prompt, a model shown `{{booking_link}}` will happily send that string to a lead.
    """
    def _sub(match: re.Match) -> str:
        return (values.get(match.group(1)) or "").strip()
    return _PLACEHOLDER_RE.sub(_sub, text)


def config_values(cfg: dict) -> dict:
    """The subset of `app_config` that prompts and examples may interpolate."""
    return {
        "booking_link": cfg.get("booking_link", ""),
        # Two links, two stages. `masterclass_link` is the registration page anyone may be
        # offered; `replay_link` is only rendered inside the post-booking block. `apply_link`
        # is not here on purpose: v2.0 §G gives the URL and never says which stage sends it.
        "masterclass_link": cfg.get("masterclass_link", ""),
        "replay_link": cfg.get("replay_link", ""),
        # So a conversation that opens with a CTA keyword can be shown in a few-shot exactly as the
        # lead received it, rather than as a paraphrase that drifts from what config actually sends.
        "cta_welcome_message": cfg.get("cta_welcome_message", ""),
        "price_range": cfg.get("price_range", ""),
        "years_experience": cfg.get("years_experience", ""),
        "babies_welcomed": cfg.get("babies_welcomed", ""),
    }


def build_write_prompt(cfg: dict, allowed_blocks: set[str]) -> str:
    """The static half of the WRITE call: identity, judgment, boundaries, voice, known facts."""
    values = config_values(cfg)
    if (cfg.get("write_prompt") or "").strip() == "manual":
        return _manual_write_prompt(values, allowed_blocks)
    parts = []
    for layer in WRITE_LAYERS:
        text = _read_layer(layer)
        if layer == KNOWLEDGE_LAYER:
            text = resolve_blocks(text, allowed_blocks)
        parts.append(fill_placeholders(text, values).strip())
    return "\n\n---\n\n".join(p for p in parts if p)


# Experiment: `write_prompt = manual` in config swaps layers 00 to 60 for the Operating Manual
# itself plus bare facts. The manual's URLs are replaced with markers, so the same gate still
# decides which links exist on a turn.
MANUAL_LAYER = "manual.md"

_FACT_KEYS = (
    ("Experience", "years_experience"),
    ("Babies welcomed", "babies_welcomed"),
)

_GATED_FACTS = (
    ("pricing", "Investment", "price_range"),
    ("booking", "Booking link (free consultation)", "booking_link"),
    ("post_booking", "Masterclass replay link (post-booking only)", "replay_link"),
    ("free_resource", "Masterclass registration link (free resource)", "masterclass_link"),
)


def _manual_write_prompt(values: dict, allowed_blocks: set[str]) -> str:
    facts = [
        (title, values.get(key)) for title, key in _FACT_KEYS
    ] + [
        (title, values.get(key)) for block, title, key in _GATED_FACTS if block in allowed_blocks
    ]
    body = "\n\n".join(f"## {title}\n{(value or '').strip()}" for title, value in facts if (value or "").strip())
    return "\n\n---\n\n".join((
        "You are Sonia Ribas, replying in her Instagram DMs. The Operating Manual below is how you "
        "behave. Reply with the message text only: plain text, first person, no markdown, blank "
        "lines between message bubbles.",
        _read_layer(MANUAL_LAYER, LEGACY_DIR).strip(),
        "# KNOWN FACTS\n\nCurrent facts and the links you may send on this turn. A link that is "
        "not listed here is one you may not send now.\n\n" + body,
    ))


def build_read_prompt() -> str:
    return _read_layer(READ_LAYER)


def build_safety_prompt() -> str:
    return _read_layer(SAFETY_LAYER)


def build_language_prompt() -> str:
    return _read_layer(LANGUAGE_LAYER)


def turn_notes() -> dict[str, str]:
    """The per-turn notes in `turn.md`, keyed by their `## name` heading.

    Each note is joined onto one line so it renders as a single bullet under THIS TURN. Text above
    the first heading is a comment for whoever edits the file and is never sent.
    """
    parts = _SECTION_RE.split(_read_layer(TURN_LAYER))
    return {
        name: " ".join(body.split())
        for name, body in zip(parts[1::2], parts[2::2])
    }
