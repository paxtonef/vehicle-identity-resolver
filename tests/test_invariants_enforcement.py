"""Integration tests proving core invariants are actually enforced end to end
through ResolutionEngine.resolve() — not just correct in isolation (see
tests/test_invariants.py for the isolated unit tests).

Context (P2.5 — Core Governance Closure): before this closure, only
invariant_004 was wired into the engine. invariant_005/006/007 existed with
correct logic but were never called, and invariant_001 never raised even in
its own described violation case. This file proves the wiring has real
teeth against realistic engine behavior, not just against hand-crafted
InvariantViolation calls.
"""
from __future__ import annotations

import pytest

from vir.domain.enums import ResolutionStatus, ConfidenceLevel, FuelType, TransmissionType
from vir.domain.errors import VIRBaseError
from vir.domain.invariants import InvariantViolation
from vir.domain.models import (
    VehicleIdentityRequest,
    ConsentInput,
    ProviderVehicleRecord,
    CanonicalVehicleIdentity,
    Production,
    Fuel,
    Engine,
    Transmission,
    FieldProvenance,
)
from vir.domain.resolution import ResolutionEngine
from vir.ports.vehicle_provider import VehicleDataProvider


@pytest.fixture(autouse=True)
def _bypass_rgg_for_fake_provider(monkeypatch):
    """These tests exercise Core invariant enforcement (P2.5), not runtime
    governance (P4) — bypass the RGG's external_services allowlist so the
    fake test provider below isn't blocked by default:deny. RGG-specific
    behavior (including that default:deny correctly blocks an unlisted
    provider) is tested separately in tests/test_governance.py."""
    from vir.domain import resolution as resolution_module
    monkeypatch.setattr(resolution_module.RGG, "is_provider_permitted", lambda *a, **k: True)


class _TwoCloseCandidatesProvider(VehicleDataProvider):
    """A fake, high-confidence, single-source provider that returns two
    richly-populated candidates agreeing on every field except fuel type.

    Why fuel type: `_build_candidates()` deduplicates on
    (manufacturer, model, year, fuel) — two candidates must differ on at
    least one of those four fields to survive as distinct candidates at
    all. Differing on fuel type (rather than, say, generation, which is
    *not* part of the dedup key and collapses to a single candidate) is
    the minimal realistic way to reach two distinct, richly-scored
    candidates from one source.

    Because both candidates come from the *same* adapter_id, the
    contradiction engine correctly treats this as single-source ambiguity,
    not a cross-source contradiction (see contradictions.py's own
    docstring) — so no contradiction penalizes field_consistency, and with
    every other scored field fully populated, confidence.score legitimately
    climbs above 0.90 (CONFIRMED-level) while resolution_status ends up
    AMBIGUOUS (the two candidates score identically). This is exactly the
    gap flagged during P2: ambiguity detection and confidence scoring don't
    see the same signal, so nothing before P2.5 stopped an AMBIGUOUS
    resolution from also claiming CONFIRMED-level confidence.
    """

    adapter_id = "fake-high-confidence-provider"
    supported_countries: list[str] = []
    supported_identifier_types = ["vin"]

    async def resolve_registration(self, number, country):
        raise NotImplementedError

    async def decode_vin(self, vin: str) -> list[ProviderVehicleRecord]:
        def _record(record_id: str, fuel: FuelType) -> ProviderVehicleRecord:
            identity = CanonicalVehicleIdentity(
                manufacturer="Peugeot",
                model="308",
                production=Production(year=2019),
                fuel=Fuel(primary_type=fuel),
                engine=Engine(power_kw=96.0),
                transmission=Transmission(type=TransmissionType.MANUAL),
            )
            return ProviderVehicleRecord(
                provider_record_id=record_id,
                adapter_id=self.adapter_id,
                normalized_candidate=identity,
                field_provenance=[
                    FieldProvenance(field_path="manufacturer", source_id=self.adapter_id, raw_value="Peugeot"),
                    FieldProvenance(field_path="model", source_id=self.adapter_id, raw_value="308"),
                ],
                provider_confidence=0.97,
            )

        return [_record("REC-A", FuelType.PETROL), _record("REC-B", FuelType.DIESEL)]

    async def retrieve_vehicle_configuration(self, **kwargs):
        raise NotImplementedError


def _request() -> VehicleIdentityRequest:
    return VehicleIdentityRequest(
        request_id="INV-ENFORCEMENT-TEST",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )


@pytest.mark.asyncio
async def test_ambiguous_high_confidence_scenario_is_architecturally_reachable():
    """Sanity check: confirm the fixture actually reproduces AMBIGUOUS status
    with confidence.score > 0.8 when invariant enforcement is bypassed —
    i.e. that this is a real gap the engine can reach, not a fabricated one.
    This test talks to the confidence/status computation directly rather
    than through resolve(), so it is unaffected by the invariant wiring."""
    from vir.domain.confidence import ConfidenceEngine
    from vir.domain.contradictions import ContradictionEngine

    engine = ResolutionEngine(providers=[_TwoCloseCandidatesProvider()])
    request = engine._normalize_identifiers(_request())
    records = await engine._query_providers(request)
    candidates = engine._build_candidates(records, request)
    contradictions = ContradictionEngine().detect(candidates, request)
    confidence = ConfidenceEngine().calculate(candidates, records, request, contradictions)
    status = engine._determine_status(candidates, contradictions, confidence, records)

    assert status == ResolutionStatus.AMBIGUOUS
    assert confidence.score > 0.8, (
        f"fixture must reproduce the gap (score={confidence.score}); "
        f"adjust the fixture if confidence scoring changes"
    )


@pytest.mark.asyncio
async def test_wired_invariants_block_ambiguous_with_inflated_confidence():
    """The real test: resolve() through the public engine entrypoint must
    now raise InvariantViolation for this scenario, because invariant_005
    (and/or 007) is wired in — before P2.5 this would have silently
    returned an AMBIGUOUS resolution carrying a >0.8 confidence score."""
    engine = ResolutionEngine(providers=[_TwoCloseCandidatesProvider()])
    with pytest.raises(InvariantViolation):
        await engine.resolve(_request())


@pytest.mark.asyncio
async def test_normal_resolution_paths_are_unaffected_by_new_wiring():
    """Regression guard: a well-behaved, non-ambiguous resolution must still
    complete normally with the new invariants wired in."""
    from vir.adapters.vin_decoder_adapter import VINDecoderAdapter

    engine = ResolutionEngine(providers=[VINDecoderAdapter()])
    request = VehicleIdentityRequest(
        request_id="REGRESSION-TEST",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    resolution = await engine.resolve(request)
    assert resolution.resolution_status == ResolutionStatus.RESOLVED
    # Every populated field must now have evidence (invariant_003, generalized)
    assert len(resolution.field_evidence) > 6  # more than the old fixed subset
    assert all(fe.sources for fe in resolution.field_evidence)  # invariant_006 holds
