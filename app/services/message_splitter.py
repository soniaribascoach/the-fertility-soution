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
# A range, including the one that matters most here, "$1,500-$7,200".
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


# Spelled-out quantities, the second thing the model will not stop doing. Same reasoning as the
# dashes above and the same narrow licence: "Four years of that would flatten anyone" reads as
# composed, "4 years" reads as typed on a phone, and swapping one for the other cannot change a
# decision, cross a boundary or leak a link. Client review point 18.
#
# Only a number word directly in front of a unit is touched, so the quantity is unambiguous. That
# leaves "one of the things", "no one", "someone", "the first thing" and "a second opinion" alone
# without needing to list them, because none of them is a number followed by a unit.
_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
    "eighteen": "18", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
}
_UNITS = (
    "months?|years?|weeks?|days?|hours?|minutes?|cycles?|rounds?|losses|miscarriages|times|"
    "IUIs?|IVFs?|transfers?|embryos?|eggs?|kids?|children|sessions?|calls?"
)
# "one day" is someday and "one time" is once. Neither is a quantity, both match the shape.
_NOT_QUANTITIES = {"one day", "one time"}

_SPELLED = re.compile(rf"\b({'|'.join(_NUMBER_WORDS)})\s+({_UNITS})\b", re.IGNORECASE)


def use_digits(text: str) -> str:
    """Write quantities as digits, so a reply reads the way she types rather than the way it drafts.

    A hyphenated compound is left alone: "two-week wait" is the name of the thing, and the hyphen
    rule in CLAUDE.md protects compounds generally.
    """
    if not text:
        return text

    def replace(match: re.Match) -> str:
        if match.group(0).lower() in _NOT_QUANTITIES:
            return match.group(0)
        # The unit keeps whatever case it arrived in. A digit has no case to preserve.
        return f"{_NUMBER_WORDS[match.group(1).lower()]} {match.group(2)}"

    return _SPELLED.sub(replace, text)


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
