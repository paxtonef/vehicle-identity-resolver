"""Regression tests for P6.1 and P6.2 — two related invariants:

P6.1: "Clarification MUST preserve all previously accepted identification
inputs unless the user explicitly corrects them." (your framing)

P6.2 (generalized as a mapping-completeness contract, your framing):
"Each supported attribute must either traverse the whole chain
(Provider data -> normalized candidate -> resolution -> field evidence ->
API/Web output), or be explicitly rejected/ignored. It must not disappear
silently."

Both fixes are verified two ways in this file: a direct regression test
for the concrete bug found, AND a generalized contract test that would
catch a *different* field being dropped in the future, not just the two
fields found this session.
"""
from __future__ import annotations

import pytest

from vir.domain.models import (
    VehicleIdentityRequest,
    RegistrationInput,
    ManualIdentityInput,
    ConsentInput,
    ClarificationAnswer,
    ProviderVehicleRecord,
    CanonicalVehicleIdentity,
)
from vir.domain.resolution import ResolutionEngine
from vir.application.clarify_resolution import ClarifyResolutionUseCase
from vir.application.resolve_vehicle import ResolveVehicleUseCase
from vir.adapters.manual_adapter import ManualAdapter
from vir.adapters.registration_provider_adapter import FrenchRegistrationProviderAdapter
from vir.adapters.vin_decoder_adapter import VINDecoderAdapter
from vir.ports.vehicle_provider import VehicleDataProvider


def _providers():
    return [ManualAdapter(), FrenchRegistrationProviderAdapter(), VINDecoderAdapter()]


@pytest.fixture(autouse=True)
def _bypass_rgg_for_spy_provider(monkeypatch):
    """These tests exercise request->dispatch mapping logic, not runtime
    governance (P4) — bypass the RGG's external_services allowlist so the
    fake "spy" test provider below isn't blocked by default:deny. See
    tests/test_governance.py for RGG-specific coverage."""
    from vir.domain import resolution as resolution_module
    monkeypatch.setattr(resolution_module.RGG, "is_provider_permitted", lambda *a, **k: True)


# ============================================================================
# P6.1 — Clarification state integrity
# ============================================================================

@pytest.mark.asyncio
async def test_clarification_preserves_registration_number():
    """The concrete bug: a clarification on a registration-based ambiguous
    resolution previously lost the registration number entirely, falling
    back to a manual-only re-resolution."""
    request = VehicleIdentityRequest(
        request_id="P6-1-TEST",
        registration=RegistrationInput(registration_number="AM-BIG-01", country_code="FR"),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    resolve_use_case = ResolveVehicleUseCase(providers=_providers())
    original_resolution = await resolve_use_case.execute(request)
    assert original_resolution.resolution_status.value == "ambiguous"

    clarify_use_case = ClarifyResolutionUseCase(providers=_providers())
    enriched_request, new_resolution = await clarify_use_case.execute(
        request,
        original_resolution,
        [ClarificationAnswer(question_id="VIR-Q-001", value=81)],
    )

    # The invariant, checked directly on the request that was re-resolved:
    assert enriched_request.registration.registration_number == "AM-BIG-01"
    assert enriched_request.registration.country_code == "FR"

    # And observable in the actual re-resolution output: the FR registration
    # provider was queried again (not silently dropped to manual-only).
    assert any(
        s.source_id == "provider-fr-registration" for s in new_resolution.source_summary
    )


@pytest.mark.asyncio
async def test_clarification_preserves_vin_when_answering_a_different_question():
    """A clarification answering the power question must not lose a VIN
    that was already part of the original request."""
    request = VehicleIdentityRequest(
        request_id="P6-1-VIN-TEST",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    resolve_use_case = ResolveVehicleUseCase(providers=_providers())
    original_resolution = await resolve_use_case.execute(request)

    clarify_use_case = ClarifyResolutionUseCase(providers=_providers())
    enriched_request, _ = await clarify_use_case.execute(
        request, original_resolution, []  # no answers at all
    )
    assert enriched_request.vin == "VF3XXXXXXXXXXXXXX"


@pytest.mark.asyncio
async def test_clarification_preserves_manual_fields_already_confirmed():
    request = VehicleIdentityRequest(
        request_id="P6-1-MANUAL-TEST",
        manual_identity=ManualIdentityInput(manufacturer="Renault", model="Clio", production_year=2019),
        consent=ConsentInput(external_lookup_allowed=True),
    )
    resolve_use_case = ResolveVehicleUseCase(providers=_providers())
    original_resolution = await resolve_use_case.execute(request)

    clarify_use_case = ClarifyResolutionUseCase(providers=_providers())
    enriched_request, _ = await clarify_use_case.execute(request, original_resolution, [])
    assert enriched_request.manual_identity.manufacturer == "Renault"
    assert enriched_request.manual_identity.model == "Clio"
    assert enriched_request.manual_identity.production_year == 2019


def test_apply_answers_uses_target_field_not_hardcoded_question_id():
    """Generalization check: _apply_answers resolves target_field from the
    resolution's own clarification_questions, so it isn't limited to the
    two question_id strings the current engine happens to generate."""
    from vir.domain.models import VehicleIdentityResolution, Confidence, ClarificationQuestion
    from vir.domain.enums import ResolutionStatus, ConfidenceLevel, QuestionType

    use_case = ClarifyResolutionUseCase(providers=_providers())
    request = VehicleIdentityRequest(
        request_id="X",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    resolution = VehicleIdentityResolution(
        request_id="X",
        resolution_id="Y",
        resolution_status=ResolutionStatus.PROVISIONALLY_RESOLVED,
        confidence=Confidence(score=0.5, level=ConfidenceLevel.MEDIUM),
        clarification_questions=[
            ClarificationQuestion(
                question_id="SOME-OTHER-ID",  # deliberately not VIR-Q-001/VIR-Q-VIN
                target_field="engine.power_kw",
                reason="test",
                question_type=QuestionType.TEXT,
                prompt="test",
            ),
        ],
    )
    enriched = use_case._apply_answers(
        request, resolution, [ClarificationAnswer(question_id="SOME-OTHER-ID", value=100)]
    )
    assert enriched.manual_identity.engine_power_kw == 100.0


# ============================================================================
# P6.2 — Mapping completeness contract
# ============================================================================

@pytest.mark.asyncio
async def test_dispatch_forwards_all_manual_identity_fields():
    """The concrete bug: engine_displacement_cc, engine_power_kw, and
    transmission_type were populated on the request but never reached
    ManualAdapter."""
    from vir.domain.enums import FuelType, TransmissionType

    captured_kwargs = {}

    class _SpyProvider(VehicleDataProvider):
        adapter_id = "spy"
        supported_countries: list[str] = []
        supported_identifier_types = ["manual"]

        async def resolve_registration(self, number, country):
            raise NotImplementedError

        async def decode_vin(self, vin):
            raise NotImplementedError

        async def retrieve_vehicle_configuration(self, **kwargs):
            captured_kwargs.update(kwargs)
            return [ProviderVehicleRecord(
                provider_record_id="SPY-1",
                adapter_id=self.adapter_id,
                normalized_candidate=CanonicalVehicleIdentity(manufacturer=kwargs.get("manufacturer")),
                provider_confidence=0.5,
            )]

    request = VehicleIdentityRequest(
        request_id="P6-2-TEST",
        manual_identity=ManualIdentityInput(
            manufacturer="Peugeot",
            model="308",
            production_year=2018,
            fuel_type="petrol",
            engine_displacement_cc=1600,
            engine_power_kw=96.0,
            transmission_type="manual",
        ),
        consent=ConsentInput(external_lookup_allowed=True),
    )

    engine = ResolutionEngine(providers=[_SpyProvider()])
    await engine._query_providers(request)

    assert captured_kwargs.get("engine_displacement_cc") == 1600
    assert captured_kwargs.get("engine_power_kw") == 96.0
    assert captured_kwargs.get("transmission_type") == "manual"


@pytest.mark.asyncio
async def test_mapping_completeness_every_manual_identity_field_is_forwarded():
    """Generalized contract test (your framing): every field
    ManualIdentityInput declares must appear in the kwargs _dispatch sends
    to retrieve_vehicle_configuration. This is not a hardcoded list of the
    3 fields fixed this session — it introspects ManualIdentityInput's
    actual field set, so adding a new field there without also forwarding
    it in _dispatch fails this test, not silently disappears in production."""
    captured_kwargs = {}

    class _SpyProvider(VehicleDataProvider):
        adapter_id = "spy"
        supported_countries: list[str] = []
        supported_identifier_types = ["manual"]

        async def resolve_registration(self, number, country):
            raise NotImplementedError

        async def decode_vin(self, vin):
            raise NotImplementedError

        async def retrieve_vehicle_configuration(self, **kwargs):
            captured_kwargs.update(kwargs)
            return []

    # Populate every field on ManualIdentityInput with a non-None value.
    field_values = {
        "manufacturer": "TestMake",
        "model": "TestModel",
        "production_year": 2020,
        "fuel_type": "diesel",
        "engine_displacement_cc": 2000,
        "engine_power_kw": 110.0,
        "transmission_type": "automatic",
    }
    assert set(field_values.keys()) == set(ManualIdentityInput.model_fields.keys()), (
        "This test's field_values must be updated to cover every field on "
        "ManualIdentityInput — a new field was added to the model without "
        "updating this completeness check."
    )

    request = VehicleIdentityRequest(
        request_id="COMPLETENESS-TEST",
        manual_identity=ManualIdentityInput(**field_values),
        consent=ConsentInput(external_lookup_allowed=True),
    )

    engine = ResolutionEngine(providers=[_SpyProvider()])
    await engine._query_providers(request)

    # The kwarg name for production_year is "year" in the provider contract
    # (ManualAdapter.retrieve_vehicle_configuration reads kwargs["year"]) —
    # every OTHER field name matches its ManualIdentityInput name directly.
    expected_kwarg_names = {
        "manufacturer", "model", "year", "fuel_type",
        "engine_displacement_cc", "engine_power_kw", "transmission_type",
    }
    missing = expected_kwarg_names - captured_kwargs.keys()
    assert not missing, f"_dispatch failed to forward: {missing}"
    for name, value in field_values.items():
        kwarg_name = "year" if name == "production_year" else name
        assert captured_kwargs[kwarg_name] == value, (
            f"{name} was forwarded but with the wrong value: "
            f"expected {value!r}, got {captured_kwargs[kwarg_name]!r}"
        )
