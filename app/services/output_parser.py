import re
from dataclasses import dataclass

_MARKERS = [
    r"\[HUMAN_HANDOVER\]",
    r"\[BOOKING_SENT\]",
    r"\[BOOKING_ASKED\]",
    r"\[PRICE_DEFLECTED\]",
]


@dataclass
class ParsedOutput:
    clean_text: str
    is_handover: bool
    is_booking_sent: bool
    is_booking_asked: bool
    is_price_deflected: bool


def parse_ai_output(raw: str) -> ParsedOutput:
    is_handover = bool(re.search(r"\[HUMAN_HANDOVER\]", raw))
    is_booking_sent = bool(re.search(r"\[BOOKING_SENT\]", raw))
    is_booking_asked = bool(re.search(r"\[BOOKING_ASKED\]", raw))
    is_price_deflected = bool(re.search(r"\[PRICE_DEFLECTED\]", raw))

    clean = raw
    for pattern in _MARKERS:
        clean = re.sub(pattern, "", clean)
    clean = clean.strip()

    if is_handover:
        clean = ""

    return ParsedOutput(
        clean_text=clean,
        is_handover=is_handover,
        is_booking_sent=is_booking_sent,
        is_booking_asked=is_booking_asked,
        is_price_deflected=is_price_deflected,
    )
