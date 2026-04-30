import random
import re


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
