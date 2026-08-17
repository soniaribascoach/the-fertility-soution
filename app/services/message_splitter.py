import random
import re

# A dash used as punctuation, in any of the three forms a model produces: em, en, and a double
# hyphen. A single ASCII hyphen is never touched, so `whole-body` and `low-AMH` survive.
#
# Everything else in this codebase decides what the writer is *given* and nothing inspects what it
# produced. This is the one exception, and it is deliberate: an em dash in an Instagram DM is one
# of the clearest tells that a message was not typed by a person, five rounds of writing the rule
# into `40_voice.md` and `60_contract.md` have not reached zero, and swapping a dash for a comma
# cannot change a decision, cross a boundary or leak a link. It is typography, not judgment.
# Written as escapes rather than as the characters themselves so that the repo-wide check in
# CLAUDE.md keeps working: a grep for a dash in the source should stay silent, including here.
_EM, _EN = "\u2014", "\u2013"
_ANY_DASH = f"(?:[{_EM}{_EN}]|--)"

_DASH = re.compile(rf"[ \t]*{_ANY_DASH}[ \t]*")
# A range, including the one that matters most here, "$1,500-$14,000".
_DIGIT_DASH = re.compile(rf"(?<=\d)[ \t]*{_ANY_DASH}[ \t]*(?=[$€£]?\s?\d)")
_LEADING_DASH = re.compile(rf"(?m)^[ \t]*{_ANY_DASH}[ \t]*")


def strip_dashes(text: str) -> str:
    """Replace every dash used as punctuation, so no lead is ever sent one.

    A dash between digits is a range and becomes " to ". A dash opening a line is a bullet and is
    dropped. Everywhere else it is joining a clause to its qualifier, which is a comma, unless the
    clause already ends in punctuation, in which case the dash simply goes.
    """
    if not text:
        return text

    text = _DIGIT_DASH.sub(" to ", text)
    text = _LEADING_DASH.sub("", text)

    def replace(match: re.Match) -> str:
        before = text[:match.start()].rstrip()
        if not before or before[-1] in ",.;:!?":
            return " "
        return ", "

    text = _DASH.sub(replace, text)
    # A dash at the end of a line leaves a trailing comma with nothing after it. Only spaces and
    # tabs are eaten here: a newline holds the paragraph break that `split_reply` divides on.
    return re.sub(r"(?m),[ \t]*$", "", text)


def split_reply(text: str, max_chars: int = 600, natural: bool = True) -> list[str]:
    """Split text into IG-friendly chunks at paragraph boundaries.
    Chunks over max_chars are split further at the last sentence boundary before the limit.
    When natural=True, adjacent short paragraphs are randomly merged to vary rhythm."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if natural:
        paragraphs = _merge_naturally(paragraphs, max_chars)

    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            chunks.extend(_split_long(para, max_chars))
    return chunks if chunks else [text.strip()]


def _merge_naturally(paragraphs: list[str], max_chars: int) -> list[str]:
    """Randomly merge adjacent paragraphs (40% chance) if combined length fits."""
    if len(paragraphs) <= 1:
        return paragraphs

    merged: list[str] = []
    i = 0
    while i < len(paragraphs):
        if i + 1 < len(paragraphs):
            combined = paragraphs[i] + "\n" + paragraphs[i + 1]
            if len(combined) <= max_chars and random.random() < 0.40:
                merged.append(combined)
                i += 2
                continue
        merged.append(paragraphs[i])
        i += 1
    return merged


def _split_long(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    while len(text) > max_chars:
        boundary = max_chars
        match = re.search(r"[.!?]\s+", text[:max_chars])
        if match:
            boundary = match.end()
        parts.append(text[:boundary].strip())
        text = text[boundary:].strip()
    if text:
        parts.append(text)
    return parts
