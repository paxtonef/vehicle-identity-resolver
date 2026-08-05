from __future__ import annotations

import pytest

from vir.domain.models import (
    VehicleIdentityRequest,
    ManualIdentityInput,
    ConsentInput,
    RegistrationInput,
)
from vir.domain.enums import ResolutionStatus, ConfidenceLevel
from vir.application.resolve_vehicle import ResolveVehicleUseCase
from vir.adapters.manual_adapter import ManualAdapter
from vir.adapters.registration_provider_adapter import FrenchRegistrationProviderAdapter
from vir.adapters.vin_decoder_adapter import VINDecoderAdapter


def _providers():
    return [
        ManualAdapter(),
        FrenchRegistrationProviderAdapter(),
        VINDecoderAdapter(),
    ]


# -- Scenario 1: Exact VIN resolution --
@pytest.mark.asyncio
async def test_exact_vin_resolution():
    request = VehicleIdentityRequest(
        request_id="TEST-001",
        vin="VF3XXXXXXXXXXXXXX",  # Valid format, stub will decode WMI
        consent=ConsentInput(external_lookup_allowed=True),
    )
    use_case = ResolveVehicleUseCase(providers=_providers())
    result = await use_case.execute(request)

    assert result.resolution_status == ResolutionStatus.RESOLVED
    assert result.confidence.level in (ConfidenceLevel.CONFIRMED, ConfidenceLevel.HIGH)
    assert len(result.contradictions) == 0
    assert result.vehicle_identity is not None
    assert result.vehicle_identity.manufacturer == "Peugeot"


# -- Scenario 2: Plate produces several motorisations --
@pytest.mark.asyncio
async def test_ambiguous_plate_multiple_engines():
    request = VehicleIdentityRequest(
        request_id="TEST-002",
        registration=RegistrationInput(registration_number="AM-BIG-01", country_code="FR"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    use_case = ResolveVehicleUseCase(providers=_providers())
    result = await use_case.execute(request)

    assert result.resolution_status == ResolutionStatus.AMBIGUOUS
    assert len(result.clarification_questions) >= 1


# -- Scenario 3: User and provider fuel conflict --
@pytest.mark.asyncio
async def test_user_provider_fuel_conflict():
    request = VehicleIdentityRequest(
        request_id="TEST-003",
        registration=RegistrationInput(registration_number="AB-123-CD", country_code="FR"),
        manual_identity=ManualIdentityInput(fuel_type="petrol"),  # Provider says diesel
        consent=ConsentInput(external_lookup_allowed=True),
    )
    use_case = ResolveVehicleUseCase(providers=_providers())
    result = await use_case.execute(request)

    assert result.resolution_status == ResolutionStatus.CONTRADICTORY
    assert any(c.field_path == "fuel.primary_type" for c in result.contradictions)


# -- Scenario 4: Provider unavailable (simulate by no-matching input) --
@pytest.mark.asyncio
async def test_provider_unavailable_no_fabrication():
    request = VehicleIdentityRequest(
        request_id="TEST-004",
        registration=RegistrationInput(registration_number="ZZ-999-ZZ", country_code="FR"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    use_case = ResolveVehicleUseCase(providers=_providers())
    result = await use_case.execute(request)

    assert result.resolution_status in (
        ResolutionStatus.PROVIDER_UNAVAILABLE,
        ResolutionStatus.INSUFFICIENT_DATA,
        ResolutionStatus.PROVISIONALLY_RESOLVED,
    )
    # No fabricated fields
    if result.vehicle_identity:
        assert all(v is None or v == "" for v in [
            result.vehicle_identity.engine.commercial_name,
            result.vehicle_identity.engine.engine_code,
        ])


# -- Scenario 5: Privacy - owner name must not appear --
@pytest.mark.asyncio
async def test_privacy_no_owner_data():
    request = VehicleIdentityRequest(
        request_id="TEST-005",
        registration=RegistrationInput(registration_number="AB-123-CD", country_code="FR"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    use_case = ResolveVehicleUseCase(providers=_providers())
    result = await use_case.execute(request)

    dump = result.model_dump_json().lower()
    forbidden = ["owner_name", "owner_address", "owner_phone", "owner_email"]
    for term in forbidden:
        assert term not in dump, f"Privacy leak: {term} found in output"


# -- Handoff contract --
@pytest.mark.asyncio
async def test_downstream_handoff():
    from vir.application.build_handoff import HandoffBuilder

    request = VehicleIdentityRequest(
        request_id="TEST-006",
        registration=RegistrationInput(registration_number="AB-123-CD", country_code="FR"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    use_case = ResolveVehicleUseCase(providers=_providers())
    result = await use_case.execute(request)

    handoff = HandoffBuilder.build_diagnostic_context(result)
    assert handoff.resolution_id == result.resolution_id
    assert handoff.identity_status == result.resolution_status
    assert "exact_engine_code_known" in handoff.diagnostic_constraints
    assert "confidence_score" in handoff.diagnostic_constraints
