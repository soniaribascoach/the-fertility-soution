import logging
import os
import re

logger = logging.getLogger(__name__)

_SKIP = {"about.md", "price_objection"}

ALWAYS_INCLUDE = {"tried_everything", "infertility"}

SCENARIO_PATTERNS: dict[str, str] = {
    "low_amh":                r"\b(amh|anti.{0,10}mullerian|egg.{0,5}reserve|egg.{0,5}quality)\b",
    "pcos":                   r"\b(pcos|polycystic)\b",
    "ivf_failed":             r"\b(ivf|in.{0,5}vitro|failed.{0,5}cycle|failed.{0,5}round|ivf.{0,5}trauma)\b",
    "miscarriage":            r"\b(miscarr|pregnancy.{0,5}loss|chemical.{0,5}preg|recurrent.{0,5}loss)\b",
    "partner_hesitation":     r"\b(husband|partner|spouse|financial|afford|together|decide)\b",
    "doing_everything_right": r"\b(organic|supplement|track.{0,10}ovul|doing.{0,5}everything|everything.{0,5}right)\b",
    "secondary_infertility":  r"\b(second.{0,10}preg|already.{0,10}child|had.{0,10}child|secondary.{0,5}infert)\b",
    "male_factor":            r"\b(sperm|morphology|motility|semen|male.{0,5}factor|husband.{0,20}result)\b",
    "donor_eggs":             r"\b(donor.{0,5}egg|egg.{0,5}donor)\b",
    "body_failing":           r"\b(hopeless|give.{0,5}up|broken|nothing.{0,5}works?|traumat|body.{0,5}fail|can.{0,5}t.{0,5}take)\b",
    "not_urgent":             r"\b(just.{0,5}start|few.{0,5}months?|haven.{0,5}t.{0,5}tried.{0,5}long|proactive)\b",
    "waiting_for_tests":      r"\b(waiting|test.{0,5}result|results?.{0,10}week|panel.{0,10}week)\b",
    "non_english_lead":       r"[^\x00-\x7F]{4,}|hola|necesito|embarazada",
    "credentials":            r"\b(certified|qualified|different.{0,20}coach|what.{0,10}makes.{0,10}differ)\b",
    "direct_call":            r"\b(speak.{0,10}sonia|talk.{0,10}sonia|sonia.{0,10}herself|directly.{0,10}you)\b",
}


def parse_few_shot(text: str, label: str) -> list[dict]:
    """Parse a User:/Sonia: dialogue into OpenAI message pairs."""
    messages = []
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


def load_few_shot_scenarios(directory: str) -> dict[str, list[dict]]:
    """Load all scenario files and return a dict keyed by scenario name."""
    scenarios: dict[str, list[dict]] = {}
    for filename in sorted(f for f in os.listdir(directory) if f not in _SKIP and not f.startswith(".")):
        path = os.path.join(directory, filename)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        scenarios[filename] = parse_few_shot(text, label=filename)
    logger.info("Loaded %d few-shot scenarios: %s", len(scenarios), sorted(scenarios))
    return scenarios


def get_few_shot_scenarios(app_state, directory: str = "few_shots") -> dict[str, list[dict]]:
    """Lazy accessor for the LEGACY brain's few-shots.

    The funnel brain doesn't use these, so they are no longer loaded at app
    boot. On the first legacy-path call (brain_version=legacy) they are loaded
    once and cached on app.state; the admin few-shots editor refreshes the
    same cache on save/rollback.
    """
    cached = getattr(app_state, "few_shot_scenarios", None)
    if cached is None:
        cached = load_few_shot_scenarios(directory)
        app_state.few_shot_scenarios = cached
    return cached


def select_few_shots(
    scenarios: dict[str, list[dict]],
    conversation_text: str,
    max_dynamic: int = 3,
) -> list[dict]:
    """Return relevant few-shot messages for this conversation (dynamic + universal)."""
    dynamic: list[str] = []
    for name, pattern in SCENARIO_PATTERNS.items():
        if name in scenarios and name not in ALWAYS_INCLUDE:
            if re.search(pattern, conversation_text, re.IGNORECASE):
                dynamic.append(name)
                if len(dynamic) >= max_dynamic:
                    break

    selected = dynamic + [n for n in ALWAYS_INCLUDE if n in scenarios]
    logger.debug("select_few_shots matched=%s always=%s", dynamic, list(ALWAYS_INCLUDE))

    result: list[dict] = []
    for name in selected:
        result.extend(scenarios[name])
    return result


def load_few_shots(directory: str) -> list[dict]:
    """Legacy flat loader — kept for backward compatibility."""
    scenarios = load_few_shot_scenarios(directory)
    result: list[dict] = []
    for msgs in scenarios.values():
        result.extend(msgs)
    return result
