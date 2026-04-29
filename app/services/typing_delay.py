import random


def calculate_delay(text: str, max_delay: float = 45.0) -> float:
    word_count = len(text.split())
    base = word_count * 0.4
    jitter = random.uniform(0.8, 1.2)
    return min(base * jitter, max_delay)
