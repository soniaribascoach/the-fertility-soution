"""Pure schema-consistency tests for the extractor (no LLM, no DB)."""
from typing import get_args

from app.services.brain.constants import Intent
from app.services.brain.extractor import _INTENT_LITERAL, SlotDeltas
from app.services.brain.constants import SLOT_KEYS


def test_intent_literal_matches_enum():
    # The extractor's Literal and the Intent enum must stay in lockstep.
    assert set(get_args(_INTENT_LITERAL)) == {i.value for i in Intent}


def test_slot_deltas_fields_are_known_slots():
    # Every field the extractor can fill must be a real lead-state slot.
    for field in SlotDeltas.model_fields:
        assert field in SLOT_KEYS, f"{field} is not in SLOT_KEYS"
