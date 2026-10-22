import pytest
from app.services.triage.evidence_provider import DDXPlusEvidenceProvider, ddxplus_provider


def test_ddxplus_provider_loaded():
    """Verify DDXPlus evidence provider indexes data accurately without disease conditions."""
    provider = ddxplus_provider
    evidences = provider.get_all_evidences()

    # DDXPlus benchmark contains 223 unique evidences
    assert len(evidences) == 223


def test_evidence_lookup():
    """Verify evidence retrieval and attribute access."""
    provider = ddxplus_provider
    ev = provider.get_evidence("E_91")  # Fever
    assert ev is not None
    assert "fever" in ev.get("question_en", "").lower()

    q_en = provider.get_evidence_question("E_91", lang="en")
    assert len(q_en) > 5

    name = provider.get_evidence_name("E_91")
    assert "fever" in name.lower()


def test_evidence_validation():
    """Verify validation of categorical and binary evidences."""
    provider = ddxplus_provider

    # Binary evidence
    valid, err = provider.validate_evidence("E_91", True)
    assert valid is True
    assert err is None

    # Invalid code
    valid_bad, err_bad = provider.validate_evidence("NON_EXISTENT_EVIDENCE_XYZ", True)
    assert valid_bad is False
    assert err_bad is not None


def test_parent_child_dependencies():
    """Verify parent/child evidence dependency satisfaction."""
    provider = ddxplus_provider

    # A root evidence has no parent and is always satisfied
    assert provider.is_dependency_satisfied("E_91", known_present={}, known_absent=[]) is True

    # If child has a parent, it is ineligible if parent is explicitly absent
    # Check any child evidence in the ontology
    child_map = provider._child_evidences
    if child_map:
        parent_code = next(iter(child_map.keys()))
        children = list(child_map[parent_code])
        if children:
            child = children[0]
            # Parent absent -> child is NOT satisfied
            assert provider.is_dependency_satisfied(child, known_present={}, known_absent=[parent_code]) is False
            # Parent present -> child IS satisfied
            assert provider.is_dependency_satisfied(child, known_present={parent_code: True}, known_absent=[]) is True
