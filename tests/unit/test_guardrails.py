import pytest
from app.services.ai import check_medical_blocklist, MEDICAL_DEFLECTION


# --- Medical Blocklist Tests ---

def test_blocklist_triggers_on_medication_keyword(mock_cfg):
    assert check_medical_blocklist("Can I take metformin with this?", mock_cfg) is True


def test_blocklist_case_insensitive(mock_cfg):
    assert check_medical_blocklist("What about CLOMID dosage?", mock_cfg) is True


def test_blocklist_partial_word_safe(mock_cfg):
    # "IVF medications" contains "IVF medication" — should match
    assert check_medical_blocklist("Tell me about IVF medication schedules.", mock_cfg) is True


def test_blocklist_no_match(mock_cfg):
    assert check_medical_blocklist("I just want to understand my options.", mock_cfg) is False


def test_blocklist_empty_config():
    cfg = {"medical_blocklist": ""}
    assert check_medical_blocklist("metformin dosage", cfg) is False


def test_medical_deflection_is_compassionate():
    assert "healthcare provider" in MEDICAL_DEFLECTION.lower() or "medical" in MEDICAL_DEFLECTION.lower()
    assert len(MEDICAL_DEFLECTION) > 50
