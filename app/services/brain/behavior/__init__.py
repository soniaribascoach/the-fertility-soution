"""The behavioral specification, loaded as persistent instructions.

Sonia's Operating Manual v1.0 is ~87k characters. Her instruction was explicit:

    "The AI loads these behavioral principles as persistent instructions, then
     dynamically retrieves only the relevant playbooks and knowledge for each
     conversation, rather than injecting the entire document into every DM."

So the manual is compiled, once, into two files rather than pasted in whole:

* `behavior/core.md` - who she is, what she never does, how she writes, what she
  would never send, and how she checks a reply before sending it. Always loaded.
  Drawn from Parts 1, 3 and 6 and Appendices A and B.
* `behavior/modes/<MODE>.md` - what this one reply is for. Only the routed mode
  is loaded. Drawn from Parts 2A and 2B.2.

Compression to roughly a tenth of the source is safe because the manual is
deliberately redundant - "answer before qualifying", "never re-ask" and "do not
force a question" each appear in five or more places. The work is deduplication,
not paraphrase; her non-negotiables are carried across close to verbatim.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Two categories of manual content must never become prompt text:

* **Decisions.** Part 2B.1 sections 6-10 - structural conditions, the tubal rule,
  the hard boundaries, the human-review list - live in `gates.py` as code, so
  "never qualify a grieving woman" is a property the tests prove rather than a
  sentence a model may or may not honour.
* **Facts.** Part 5 is the single source of truth for pricing, links, credentials
  and team, and lives in the `knowledge` table where Sonia edits it. Putting
  "16 years" in this file is how the running code ended up claiming 15 years in
  one place and "over 700 families" in another.

This layer is the prefix of every writer call and is byte-identical across every
turn in a mode, which is what makes provider prompt caching work. Anything
conversation-specific belongs in the user message, never here.
"""
import logging
from functools import lru_cache
from pathlib import Path

from app.services.brain.constants import ResponseMode

logger = logging.getLogger(__name__)

BEHAVIOR_DIR = Path(__file__).parent
CORE_PATH = BEHAVIOR_DIR / "core.md"
MODES_DIR = BEHAVIOR_DIR / "modes"

# Budget for core + the largest mode contract. This is paid on every single turn,
# so it is asserted in the tests rather than left to drift. Roughly 4 characters
# per token; exact enough for a ceiling. Spanish carries the addendum on top.
MAX_PROMPT_TOKENS = 1800
MAX_PROMPT_TOKENS_ES = 1900

_SPANISH_ADDENDUM = """

She writes in Spanish. Reply entirely in natural, warm, Latin-American-neutral Spanish, always "tu", never "usted". Do not mix in English and do not translate literally. Never open with "Gracias por compartir", "Te agradezco", "Aprecio tu honestidad", "Me alegra saber", "Que bueno escuchar", "Admiro". Links, phone numbers and price figures stay exactly as given."""


def approx_tokens(text: str) -> int:
    """Character-based estimate. Only ever used for a ceiling, never for billing."""
    return len(text) // 4


@lru_cache(maxsize=1)
def core() -> str:
    return CORE_PATH.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=len(ResponseMode))
def mode_contract(mode: ResponseMode) -> str:
    path = MODES_DIR / f"{mode.value}.md"
    if not path.exists():
        # A mode added without a contract must not silently fall back to a
        # generic prompt - that is how QUALIFY behaviour leaks into everything.
        raise FileNotFoundError(
            f"No behavior contract for mode {mode.value}: expected {path}"
        )
    return path.read_text(encoding="utf-8").strip()


def system_prompt(mode: ResponseMode, language: str = "en") -> str:
    """The persistent instruction block for one turn.

    Ordered core-then-mode on purpose: the two blocks are static, so this whole
    string is a cacheable prefix. Do not interpolate anything per-conversation.
    """
    parts = [core(), "# This reply", mode_contract(mode)]
    prompt = "\n\n".join(parts)
    if language == "es":
        prompt += _SPANISH_ADDENDUM
    return prompt


def missing_contracts() -> list[str]:
    """Modes with no contract file. Used by the tests and by a startup check."""
    return [m.value for m in ResponseMode if not (MODES_DIR / f"{m.value}.md").exists()]
