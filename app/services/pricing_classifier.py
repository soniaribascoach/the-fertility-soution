import re

_PRICE_TERMS = [
    # Direct price/cost words
    r'\bpric(?:e|es|ing|ed)\b',
    r'\bcost(?:s|ing|ly)?\b',
    r'\bfee(?:s)?\b',
    r'\bcharge(?:s|d|ing)?\b',
    r'\brate(?:s)?\b',

    # Payment and financial
    r'\bpay(?:ing|ment|ments|able)?\b',
    r'\binvest(?:ment|ments|ing)?\b',
    r'\bafford(?:able|ability|ing)?\b',
    r'\bunaffordable\b',
    r'\bfinanci(?:al|ally|es)\b',
    r'\bdollar(?:s)?\b',
    r'\$',
    r'\binstall?ment\b',
    r'\bmonthly\b',
    r'\bannual\b',
    r'\bupfront\b',
    r'\bdiscount\b',
    r'\bpromo(?:tion|tional)?\b',
    r'\brefund\b',
    r'\bsubscription\b',

    # Value / comparative
    r'\bexpensive\b',
    r'\bcheap\b',
    r'\bbudget\b',
    r'\bworth it\b',
    r'\bworth the\b',
    r'\bvalue for\b',

    # Common price-question phrases
    r'\bhow much\b',
    r'\bballpark\b',
    r'\bquote\b',
    r'\bestimate\b',
    r'\bpackage(?:s)?\b',
    r'\btotal (?:cost|price)\b',
    r'\boverall cost\b',
    r'\bprogram (?:cost|price)\b',
    r"\bwhat'?s (?:the (?:cost|price|fee)|it cost)\b",
    r'\bwhat (?:does|would) it cost\b',
    r'\bwhat do you charge\b',
    r'\bgive me a (?:number|figure|ballpark)\b',
    r'\bmoney\b',
]

_PRICE_RE = re.compile('|'.join(_PRICE_TERMS), re.IGNORECASE)


def classify_price_asks(messages: list[dict]) -> int:
    """Count user messages containing a price-related term, capped at 2."""
    count = sum(
        1 for msg in messages
        if msg.get("role") == "user" and _PRICE_RE.search(msg["content"])
    )
    return min(count, 2)
