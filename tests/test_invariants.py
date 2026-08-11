"""Unit tests for vir.domain.invariants (P2.5 — Core Governance Closure).

These test the invariant functions directly, in isolation, with hand-crafted
inputs — complementary to tests/test_invariants_enforcement.py, which proves
the same invariants actually fire when wired into the real resolution
engine end to end.
"""
from __future__ import annotations

from vir.domain.enums import ResolutionStatus, ConfidenceLevel, FuelType
from vir.domain.invariants import (
    InvariantViolation,
    invariant_001_raw_never_overwrites_normalized,
    invariant_003_no_field_without_provenance,
    invariant_005_uncertainty_visible,
    invariant_006_source_attribution_preserved,
    invariant_007_ambiguous_not_confirmed,
    _populated_identity_field_paths,
)
from vir.domain.models import (
    VehicleIdentityResolution,
    CanonicalVehicleIdentity,
    Fuel,
    Confidence,
    FieldEvidence,
    SourceEvidence,
)

import pytest


def _resolution(**overrides) -> VehicleIdentityResolution:
    defaults = dict(
        request_id="TEST",
        resolution_id="VIR-RES-TEST",
        resolution_status=ResolutionStatus.RESOLVED,
        confidence=Confidence(score=0.5, level=ConfidenceLevel.MEDIUM),
        vehicle_identity=None,
        alternative_candidates=[],
        unresolved_fields=[],
        contradictions=[],
        clarification_questions=[],
        field_evidence=[],
        source_summary=[],
        limitations=[],
    )
    defaults.update(overrides)
    return VehicleIdentityResolution(**defaults)


# -- A: VIR-INV-001 (fixed in P2.5 — previously never raised) --------------

def test_invariant_001_raises_when_normalization_produced_nothing():
    with pytest.raises(InvariantViolation, match="no normalized counterpart"):
        invariant_001_raw_never_overwrites_normalized(raw="AB-123-CD", normalized=None)


def test_invariant_001_raises_when_normalized_is_blank():
    with pytest.raises(InvariantViolation):
        invariant_001_raw_never_overwrites_normalized(raw="AB-123-CD", normalized="   ")


def test_invariant_001_does_not_raise_for_successful_normalization():
    # Normal case: raw differs from normalized because normalization did its
    # job (uppercased, dashes fixed) — this must NOT be treated as a violation.
    invariant_001_raw_never_overwrites_normalized(raw=" ab 123 cd ", normalized="AB-123-CD")


def test_invariant_001_does_not_raise_when_raw_is_absent():
    invariant_001_raw_never_overwrites_normalized(raw=None, normalized=None)


# -- C: VIR-INV-003, generalized (P2.5) -------------------------------------

def test_populated_identity_field_paths_covers_more_than_six_fields():
    identity = CanonicalVehicleIdentity(
        manufacturer="Peugeot",
        model="3008",
        generation="II",
        fuel=Fuel(primary_type=FuelType.DIESEL),
    )
    paths = _populated_identity_field_paths(identity)
    assert "manufacturer" in paths
    assert "model" in paths
    assert "generation" in paths  # not one of the original 6 hardcoded fields
    assert "fuel.primary_type" in paths
    assert paths["fuel.primary_type"] == "diesel"  # enum unwrapped to its value


def test_invariant_003_raises_when_populated_field_has_no_evidence():
    identity = CanonicalVehicleIdentity(manufacturer="Peugeot", model="3008")
    resolution = _resolution(
        vehicle_identity=identity,
        field_evidence=[
            FieldEvidence(
                field_path="manufacturer",
                resolved_value="Peugeot",
                sources=[SourceEvidence(source_id="x", reported_value="Peugeot", reliability="high")],
            ),
            # "model" is populated on the identity but has no evidence entry — violation.
        ],
    )
    with pytest.raises(InvariantViolation, match="model"):
        invariant_003_no_field_without_provenance(resolution)


def test_invariant_003_does_not_raise_when_all_populated_fields_have_evidence():
    identity = CanonicalVehicleIdentity(manufacturer="Peugeot", model="3008")
    resolution = _resolution(
        vehicle_identity=identity,
        field_evidence=[
            FieldEvidence(
                field_path="manufacturer",
                resolved_value="Peugeot",
                sources=[SourceEvidence(source_id="x", reported_value="Peugeot", reliability="high")],
            ),
            FieldEvidence(
                field_path="model",
                resolved_value="3008",
                sources=[SourceEvidence(source_id="x", reported_value="3008", reliability="high")],
            ),
        ],
    )
    invariant_003_no_field_without_provenance(resolution)  # must not raise


def test_invariant_003_no_op_when_no_identity_resolved():
    resolution = _resolution(vehicle_identity=None, field_evidence=[])
    invariant_003_no_field_without_provenance(resolution)  # must not raise


# -- B: VIR-INV-005, 006, 007 (dormant -> wired in P2.5) --------------------

def test_invariant_005_raises_on_ambiguous_with_inflated_confidence():
    resolution = _resolution(
        resolution_status=ResolutionStatus.AMBIGUOUS,
        confidence=Confidence(score=0.85, level=ConfidenceLevel.HIGH),
    )
    with pytest.raises(InvariantViolation, match="inflated confidence"):
        invariant_005_uncertainty_visible(resolution)


def test_invariant_005_does_not_raise_on_ambiguous_with_low_confidence():
    resolution = _resolution(
        resolution_status=ResolutionStatus.AMBIGUOUS,
        confidence=Confidence(score=0.6, level=ConfidenceLevel.MEDIUM),
    )
    invariant_005_uncertainty_visible(resolution)  # must not raise


def test_invariant_006_raises_when_evidence_lacks_sources():
    evidence = [FieldEvidence(field_path="manufacturer", resolved_value="Peugeot", sources=[])]
    with pytest.raises(InvariantViolation, match="manufacturer"):
        invariant_006_source_attribution_preserved(evidence)


def test_invariant_006_does_not_raise_when_all_evidence_has_sources():
    evidence = [
        FieldEvidence(
            field_path="manufacturer",
            resolved_value="Peugeot",
            sources=[SourceEvidence(source_id="x", reported_value="Peugeot", reliability="high")],
        ),
    ]
    invariant_006_source_attribution_preserved(evidence)  # must not raise


def test_invariant_007_raises_when_ambiguous_is_marked_confirmed():
    resolution = _resolution(
        resolution_status=ResolutionStatus.AMBIGUOUS,
        confidence=Confidence(score=0.95, level=ConfidenceLevel.CONFIRMED),
    )
    with pytest.raises(InvariantViolation, match="cannot have confirmed confidence"):
        invariant_007_ambiguous_not_confirmed(resolution)


def test_invariant_007_does_not_raise_when_ambiguous_is_not_confirmed():
    resolution = _resolution(
        resolution_status=ResolutionStatus.AMBIGUOUS,
        confidence=Confidence(score=0.6, level=ConfidenceLevel.MEDIUM),
    )
    invariant_007_ambiguous_not_confirmed(resolution)  # must not raise
