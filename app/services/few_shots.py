import os
import re


def parse_few_shot(text: str, label: str) -> list[dict]:
    """Parse a User:/Sonia: dialogue into OpenAI message pairs."""
    messages = []
    # Split on turn boundaries, keeping the speaker prefix
    parts = re.split(r'\n(?=User:|Sonia:)', text.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("User:"):
            content = part[len("User:"):].strip()
            if not messages:
                content = f"[EXAMPLE: {label}]\n{content}"
            messages.append({"role": "user", "content": content})
        elif part.startswith("Sonia:"):
            content = part[len("Sonia:"):].strip()
            messages.append({"role": "assistant", "content": content})
    return messages


def load_few_shots(directory: str) -> list[dict]:
    """Load all scenario files and return a flat list of message pairs."""
    skip = {"about.md"}
    all_messages: list[dict] = []

    scenario_files = sorted(
        f for f in os.listdir(directory)
        if f not in skip and not f.startswith(".")
    )

    for filename in scenario_files:
        path = os.path.join(directory, filename)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        all_messages.extend(parse_few_shot(text, label=filename))

    return all_messages
