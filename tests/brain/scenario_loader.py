"""Scenario fixtures - the client's reported failures, as executable cases.

Every case in `scenarios/` is something Sonia reported broken in her 2026-07-29
review. They are the contract with the client rather than developer-invented
scenarios, so they live as data she can read and correct, not as Python.

Each turn runs at one or two levels:

* **routing** (no LLM) - a `classify:` block stands in for the classifier, so
  the router's decision is provable for free. This is where "a grieving woman is
  never qualified" stops being a sentence in a prompt.
* **live** (real OpenAI) - the same file replayed through `run_turn_v2`, which
  additionally exercises the classifier, the writer and the checks.

A case that describes behaviour not built yet carries `status: xfail`. The
marker is strict, so the day the behaviour lands the suite fails and tells us to
delete the marker rather than quietly passing.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from app.services.brain.classify import Classification, SlotDeltas
from app.services.brain.constants import empty_lead_state

SCENARIO_DIR = Path(__file__).parent / "scenarios"


def _as_list(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


@dataclass
class Expect:
    """What this turn must be true of. Every field is optional."""
    mode: list[str] = field(default_factory=list)          # any one of these
    not_mode: list[str] = field(default_factory=list)
    silent: Optional[bool] = None
    pause: Optional[bool] = None
    no_question: bool = False
    has_question: bool = False
    no_link: bool = False
    no_booking_link: bool = False
    contains_any: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)
    max_chars: Optional[int] = None
    # QUALIFY only: the topic it is about to raise must not be one of these.
    # This is the "stop asking what she already told you" assertion.
    next_question_not: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, raw: Optional[dict]) -> "Expect":
        raw = raw or {}
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown expect keys: {sorted(unknown)}")
        return cls(
            mode=_as_list(raw.get("mode")),
            not_mode=_as_list(raw.get("not_mode")),
            silent=raw.get("silent"),
            pause=raw.get("pause"),
            no_question=bool(raw.get("no_question", False)),
            has_question=bool(raw.get("has_question", False)),
            no_link=bool(raw.get("no_link", False)),
            no_booking_link=bool(raw.get("no_booking_link", False)),
            contains_any=_as_list(raw.get("contains_any")),
            not_contains=_as_list(raw.get("not_contains")),
            max_chars=raw.get("max_chars"),
            next_question_not=_as_list(raw.get("next_question_not")),
        )


@dataclass
class Turn:
    lead: str
    sonia_before: Optional[str]
    classify: Optional[dict]
    set_slots: dict
    expect: Expect


@dataclass
class Scenario:
    id: str
    why: str                      # her words, so a failure explains itself
    source: str                   # where in her email this came from
    state: dict                   # overrides merged onto empty_lead_state
    turns: list[Turn]
    xfail: Optional[str]          # reason, when the behaviour is not built yet
    # Which runner the xfail applies to. A defect that depends on a model
    # inference can be provable against the router and still pass live whenever
    # the inference happens to fire, so the two runners disagree legitimately.
    xfail_scope: str              # "both" | "routing" | "live"
    path: str

    def xfails(self, scope: str) -> Optional[str]:
        if self.xfail and self.xfail_scope in ("both", scope):
            return self.xfail
        return None

    @property
    def routable(self) -> bool:
        """Can this run without the API? Only if every turn stubs the classifier."""
        return all(t.classify for t in self.turns)


def _parse_scenario(raw: dict, path: Path) -> Scenario:
    turns = []
    for t in raw["turns"]:
        turns.append(Turn(
            lead=t["lead"],
            sonia_before=t.get("sonia_before"),
            classify=t.get("classify"),
            set_slots=t.get("set_slots") or {},
            expect=Expect.parse(t.get("expect")),
        ))
    return Scenario(
        id=raw["id"],
        why=raw.get("why", ""),
        source=raw.get("source", ""),
        state=raw.get("state") or {},
        turns=turns,
        xfail=raw.get("xfail"),
        xfail_scope=raw.get("xfail_scope", "both"),
        path=path.name,
    )


def load_scenarios() -> list[Scenario]:
    out = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for raw in loaded:
            out.append(_parse_scenario(raw, path))
    ids = [s.id for s in out]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate scenario ids: {sorted(duplicates)}")
    return out


def build_state(scenario: Scenario) -> dict:
    """A lead state preloaded with whatever the scenario says is already known."""
    state = empty_lead_state()
    for section in ("slots", "flags", "counters"):
        for key, value in (scenario.state.get(section) or {}).items():
            if key not in state[section]:
                raise ValueError(f"{scenario.id}: unknown {section} key {key!r}")
            state[section][key] = value
    if "phase" in scenario.state:
        state["phase"] = scenario.state["phase"]
    return state


def apply_slots(state: dict, slots: dict, scenario_id: str = "") -> None:
    """Stand in for `turn.merge_facts` when running without the classifier."""
    for key, value in slots.items():
        if key not in state["slots"]:
            raise ValueError(f"{scenario_id}: unknown slot {key!r}")
        state["slots"][key] = value
    if state["slots"].get("trying_duration") or state["slots"].get("what_tried") \
            or state["slots"].get("treatment_path"):
        state["flags"]["situation_shared"] = True


_SLOT_DEFAULTS = {name: None for name in SlotDeltas.model_fields}


def stub_classification(spec: dict) -> Classification:
    """Build what the classifier would have returned, so the router can be
    tested for free. Only `intent` is required; everything else is a sane
    default, because a case should state the one thing it is about."""
    unknown = set(spec) - {
        "intent", "certainty", "language", "question", "richness", "situation",
        "oos", "takeover", "takeover_reason", "off_script", "secondary_intent",
        "slots",
    }
    if unknown:
        raise ValueError(f"unknown classify keys: {sorted(unknown)}")
    return Classification(
        language=spec.get("language", "en"),
        intent=spec["intent"],
        intent_certainty=spec.get("certainty", "certain"),
        secondary_intent=spec.get("secondary_intent"),
        question_asked=spec.get("question"),
        slot_deltas=SlotDeltas(**{**_SLOT_DEFAULTS, **(spec.get("slots") or {})}),
        evidence=[],
        situation_richness=spec.get("richness", "none"),
        situation_type=spec.get("situation", "none"),
        oos_signal=spec.get("oos", "none"),
        off_script=bool(spec.get("off_script", False)),
        takeover=bool(spec.get("takeover", False)),
        takeover_reason=spec.get("takeover_reason"),
    )


BOOKING_MARKERS = ("free-call", "/book", "calendly")


def check_text(reply: Optional[str], expect: Expect) -> list[str]:
    """Text-level assertions. Returns human-readable failures, empty if fine."""
    problems = []
    text = reply or ""
    low = text.casefold()

    if expect.no_question and "?" in text:
        problems.append(f"expected no question, got: {text!r}")
    if expect.has_question and "?" not in text:
        problems.append(f"expected a question, got: {text!r}")
    if expect.no_link and "http" in low:
        problems.append(f"expected no link, got: {text!r}")
    if expect.no_booking_link and any(m in low for m in BOOKING_MARKERS):
        problems.append(f"booking link leaked: {text!r}")
    if expect.contains_any and not any(c.casefold() in low for c in expect.contains_any):
        problems.append(f"expected one of {expect.contains_any} in: {text!r}")
    for banned in expect.not_contains:
        if banned.casefold() in low:
            problems.append(f"must not contain {banned!r}: {text!r}")
    if expect.max_chars is not None and len(text) > expect.max_chars:
        problems.append(f"{len(text)} chars > {expect.max_chars}: {text!r}")
    return problems
