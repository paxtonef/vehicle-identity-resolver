from __future__ import annotations

import pytest

from vir.domain.models import (
    VehicleCandidate,
    CanonicalVehicleIdentity,
    VehicleIdentityRequest,
    ManualIdentityInput,
    ConsentInput,
    Fuel,
    Engine,
)
from vir.domain.enums import FuelType
from vir.domain.contradictions import ContradictionEngine


@pytest.fixture
def engine():
    return ContradictionEngine()


def test_fuel_conflict_detected(engine: ContradictionEngine):
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=CanonicalVehicleIdentity(
                manufacturer="Peugeot",
                model="3008",
                fuel=Fuel(primary_type=FuelType.DIESEL),
            ),
            source_ids=["provider_a"],
            candidate_score=0.9,
        ),
    ]
    request = VehicleIdentityRequest(
        request_id="T-001",
        manual_identity=ManualIdentityInput(fuel_type="petrol"),
        consent=ConsentInput(external_lookup_allowed=False),
    )

    contradictions = engine.detect(candidates, request)
    assert len(contradictions) == 1
    assert contradictions[0].field_path == "fuel.primary_type"
    assert contradictions[0].severity == "high"


def test_no_conflict_when_values_match(engine: ContradictionEngine):
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=CanonicalVehicleIdentity(
                manufacturer="Renault",
                model="Clio",
                fuel=Fuel(primary_type=FuelType.DIESEL),
            ),
            source_ids=["provider_a"],
            candidate_score=0.9,
        ),
    ]
    request = VehicleIdentityRequest(
        request_id="T-002",
        manual_identity=ManualIdentityInput(fuel_type="diesel"),
        consent=ConsentInput(external_lookup_allowed=False),
    )

    contradictions = engine.detect(candidates, request)
    assert len(contradictions) == 0


def test_power_conflict_detected(engine: ContradictionEngine):
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=CanonicalVehicleIdentity(
                manufacturer="BMW",
                model="320",
                engine=Engine(power_kw=135),
            ),
            source_ids=["provider_a"],
            candidate_score=0.9,
        ),
        VehicleCandidate(
            candidate_id="C2",
            identity=CanonicalVehicleIdentity(
                manufacturer="BMW",
                model="320",
                engine=Engine(power_kw=120),
            ),
            source_ids=["provider_b"],
            candidate_score=0.8,
        ),
    ]
    request = VehicleIdentityRequest(
        request_id="T-003",
        consent=ConsentInput(external_lookup_allowed=False),
    )

    contradictions = engine.detect(candidates, request)
    power_conflicts = [c for c in contradictions if c.field_path == "engine.power_kw"]
    assert len(power_conflicts) == 1


# -- Provenance-aware rules --

def test_same_source_multiple_variants_is_ambiguity_not_contradiction(engine: ContradictionEngine):
    """One provider returning three engine variants must NOT be reported as a contradiction."""
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=CanonicalVehicleIdentity(
                manufacturer="Peugeot",
                model="308",
                engine=Engine(power_kw=81),
            ),
            source_ids=["provider-fr-registration"],
            candidate_score=0.8,
        ),
        VehicleCandidate(
            candidate_id="C2",
            identity=CanonicalVehicleIdentity(
                manufacturer="Peugeot",
                model="308",
                engine=Engine(power_kw=96),
            ),
            source_ids=["provider-fr-registration"],
            candidate_score=0.8,
        ),
        VehicleCandidate(
            candidate_id="C3",
            identity=CanonicalVehicleIdentity(
                manufacturer="Peugeot",
                model="308",
                engine=Engine(power_kw=73),
            ),
            source_ids=["provider-fr-registration"],
            candidate_score=0.8,
        ),
    ]
    request = VehicleIdentityRequest(
        request_id="T-004",
        consent=ConsentInput(external_lookup_allowed=False),
    )

    contradictions = engine.detect(candidates, request)
    power_conflicts = [c for c in contradictions if c.field_path == "engine.power_kw"]
    assert len(power_conflicts) == 0


def test_two_independent_sources_incompatible_power_is_contradiction(engine: ContradictionEngine):
    """Two independent providers asserting incompatible engine powers must be a contradiction."""
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=CanonicalVehicleIdentity(
                manufacturer="Renault",
                model="Clio",
                engine=Engine(power_kw=85),
            ),
            source_ids=["provider-fr-registration"],
            candidate_score=0.9,
        ),
        VehicleCandidate(
            candidate_id="C2",
            identity=CanonicalVehicleIdentity(
                manufacturer="Renault",
                model="Clio",
                engine=Engine(power_kw=66),
            ),
            source_ids=["vin-decoder-stub"],
            candidate_score=0.7,
        ),
    ]
    request = VehicleIdentityRequest(
        request_id="T-005",
        consent=ConsentInput(external_lookup_allowed=False),
    )

    contradictions = engine.detect(candidates, request)
    power_conflicts = [c for c in contradictions if c.field_path == "engine.power_kw"]
    assert len(power_conflicts) == 1
    source_ids_involved = {v.source_id for v in power_conflicts[0].values}
    assert source_ids_involved == {"provider-fr-registration", "vin-decoder-stub"}


def test_two_independent_sources_agreeing_is_not_a_contradiction(engine: ContradictionEngine):
    """Two independent providers asserting the same engine power must NOT be a contradiction."""
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=CanonicalVehicleIdentity(
                manufacturer="Renault",
                model="Clio",
                engine=Engine(power_kw=85),
            ),
            source_ids=["provider-fr-registration"],
            candidate_score=0.9,
        ),
        VehicleCandidate(
            candidate_id="C2",
            identity=CanonicalVehicleIdentity(
                manufacturer="Renault",
                model="Clio",
                engine=Engine(power_kw=85),
            ),
            source_ids=["vin-decoder-stub"],
            candidate_score=0.85,
        ),
    ]
    request = VehicleIdentityRequest(
        request_id="T-006",
        consent=ConsentInput(external_lookup_allowed=False),
    )

    contradictions = engine.detect(candidates, request)
    power_conflicts = [c for c in contradictions if c.field_path == "engine.power_kw"]
    assert len(power_conflicts) == 0
