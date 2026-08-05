from __future__ import annotations

import pytest

from vir.domain.models import (
    VehicleIdentityRequest,
    ManualIdentityInput,
    ConsentInput,
    RegistrationInput,
    ProviderVehicleRecord,
    CanonicalVehicleIdentity,
    VehicleCandidate,
    Production,
    Fuel,
    Engine,
    Transmission,
    Body,
)
from vir.domain.enums import FuelType, TransmissionType, BodyType, ConfidenceLevel
from vir.domain.confidence import ConfidenceEngine


@pytest.fixture
def engine():
    return ConfidenceEngine()


def test_vin_has_max_identifier_quality(engine: ConfidenceEngine):
    request = VehicleIdentityRequest(
        request_id="T-001",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    score = engine._score_identifier_quality(request)
    assert score == 1.0


def test_plate_has_medium_identifier_quality(engine: ConfidenceEngine):
    request = VehicleIdentityRequest(
        request_id="T-002",
        registration=RegistrationInput(registration_number="AB-123-CD", country_code="FR"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    score = engine._score_identifier_quality(request)
    assert score == 0.7


def test_manual_has_low_identifier_quality(engine: ConfidenceEngine):
    request = VehicleIdentityRequest(
        request_id="T-003",
        manual_identity=ManualIdentityInput(manufacturer="Peugeot", model="3008"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    score = engine._score_identifier_quality(request)
    assert score == 0.4


def test_confirmed_level_threshold(engine: ConfidenceEngine):
    request = VehicleIdentityRequest(
        request_id="T-004",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    records = [
        ProviderVehicleRecord(
            provider_record_id="R1",
            adapter_id="vin",
            normalized_candidate=CanonicalVehicleIdentity(
                manufacturer="Peugeot",
                model="3008",
                production=Production(year=2020),
                fuel=Fuel(primary_type=FuelType.DIESEL),
                engine=Engine(power_kw=96, displacement_cc=1499),
                transmission=Transmission(type=TransmissionType.AUTOMATIC),
                body=Body(type=BodyType.SUV),
            ),
            provider_confidence=0.9,
        ),
    ]
    candidates = [
        VehicleCandidate(
            candidate_id="C1",
            identity=records[0].normalized_candidate,
            source_ids=["vin"],
            candidate_score=0.95,
        ),
    ]
    confidence = engine.calculate(candidates, records, request, contradictions=[])
    assert confidence.score >= 0.90
    assert confidence.level == ConfidenceLevel.CONFIRMED


def test_high_severity_contradiction_penalizes(engine: ConfidenceEngine):
    from vir.domain.models import Contradiction, ContradictionValue

    request = VehicleIdentityRequest(
        request_id="T-005",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    records = []
    candidates = []
    contradictions = [
        Contradiction(
            contradiction_id="CONT-1",
            field_path="fuel.primary_type",
            values=[
                ContradictionValue(value="diesel", source_id="provider_a"),
                ContradictionValue(value="petrol", source_id="user"),
            ],
            severity="high",
        ),
    ]
    confidence = engine.calculate(candidates, records, request, contradictions)
    assert confidence.score < 0.75  # Penalized by high-severity contradiction
