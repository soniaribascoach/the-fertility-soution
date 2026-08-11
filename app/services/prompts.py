"""Assembles the system prompts from `prompts/*.md` plus the editable knowledge base.

The layers are static text distilled from the Operating Manual. The only thing that varies per
turn is the knowledge base: `50_knowledge.md` carries `{{key}}` placeholders filled from the
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

PROMPTS_DIR = "prompts"

# Order matters: identity before judgment before boundaries before voice.
WRITE_LAYERS = (
    "00_identity.md",
    "10_judgment.md",
    "20_boundaries.md",
    "30_operations.md",
    "40_voice.md",
    "50_knowledge.md",
    "60_contract.md",
)
READ_LAYER = "70_read.md"

_BLOCK_RE = re.compile(r"\[\[BLOCK:(?P<name>\w+)\]\](?P<body>.*?)\[\[/BLOCK\]\]", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


@lru_cache(maxsize=None)
def _read_layer(filename: str) -> str:
    with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as fh:
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
        "kb_about": cfg.get("kb_about", ""),
        "kb_program": cfg.get("kb_program", ""),
        "kb_pricing": cfg.get("kb_pricing", ""),
        "kb_boundaries": cfg.get("kb_boundaries", ""),
        "kb_team": cfg.get("kb_team", ""),
        "kb_faq": cfg.get("kb_faq", ""),
        "kb_free_resource": cfg.get("kb_free_resource", ""),
        "booking_link": cfg.get("booking_link", ""),
        "masterclass_link": cfg.get("masterclass_link", ""),
        "price_range": cfg.get("price_range", ""),
        "years_experience": cfg.get("years_experience", ""),
        "babies_welcomed": cfg.get("babies_welcomed", ""),
    }


def build_write_prompt(cfg: dict, allowed_blocks: set[str]) -> str:
    """The static half of the WRITE call: identity, judgment, boundaries, voice, known facts."""
    values = config_values(cfg)
    parts = []
    for layer in WRITE_LAYERS:
        text = _read_layer(layer)
        if layer == "50_knowledge.md":
            text = resolve_blocks(text, allowed_blocks)
        parts.append(fill_placeholders(text, values).strip())
    return "\n\n---\n\n".join(p for p in parts if p)


def build_read_prompt() -> str:
    return _read_layer(READ_LAYER)
