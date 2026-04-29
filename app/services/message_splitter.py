import re


def split_reply(text: str, max_chars: int = 600) -> list[str]:
    """Split text into IG-friendly chunks at paragraph boundaries.
    Chunks over max_chars are split further at the last sentence boundary before the limit."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            chunks.extend(_split_long(para, max_chars))
    return chunks if chunks else [text.strip()]


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
