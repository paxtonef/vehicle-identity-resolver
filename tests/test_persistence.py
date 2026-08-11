"""Tests for the SQLitePersistenceAdapter (P6, refactored behind
PersistencePort per your architectural requirement) and the 3 endpoints it
unblocks."""
from __future__ import annotations

import pytest

from vir.adapters.sqlite_persistence_adapter import SQLitePersistenceAdapter
from vir.ports.persistence_port import PersistenceError
from vir.domain.models import VehicleIdentityRequest, VehicleIdentityResolution, ConsentInput, Confidence
from vir.domain.enums import ResolutionStatus, ConfidenceLevel


def _request(request_id="REQ-TEST") -> VehicleIdentityRequest:
    return VehicleIdentityRequest(
        request_id=request_id,
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )


def _resolution(resolution_id="VIR-RES-TEST", request_id="REQ-TEST") -> VehicleIdentityResolution:
    return VehicleIdentityResolution(
        request_id=request_id,
        resolution_id=resolution_id,
        resolution_status=ResolutionStatus.RESOLVED,
        confidence=Confidence(score=0.9, level=ConfidenceLevel.HIGH),
    )


@pytest.fixture
def store(tmp_path) -> SQLitePersistenceAdapter:
    return SQLitePersistenceAdapter(str(tmp_path / "test.db"))


# -- Basic CRUD --------------------------------------------------------------

def test_save_and_get_resolution_round_trip(store):
    store.save_resolution(_request(), _resolution())
    fetched = store.get_resolution("VIR-RES-TEST")
    assert fetched is not None
    assert fetched.resolution_id == "VIR-RES-TEST"
    assert fetched.request_id == "REQ-TEST"
    assert fetched.resolution_status == ResolutionStatus.RESOLVED
    assert fetched.confidence.score == 0.9


def test_get_and_fetch_request_round_trip(store):
    """New in this refactor: the request itself (as received) is now
    persisted and retrievable — the schema extension your message asked
    for ('requête normalisée')."""
    request = _request()
    store.save_resolution(request, _resolution())
    fetched_request = store.get_request("VIR-RES-TEST")
    assert fetched_request is not None
    assert fetched_request.vin == "VF3XXXXXXXXXXXXXX"
    assert fetched_request.consent.external_lookup_allowed is True


def test_get_nonexistent_resolution_returns_none(store):
    assert store.get_resolution("DOES-NOT-EXIST") is None


def test_get_nonexistent_request_returns_none(store):
    assert store.get_request("DOES-NOT-EXIST") is None


def test_save_resolution_twice_overwrites(store):
    store.save_resolution(_request(), _resolution())
    r2 = _resolution()
    r2.resolution_status = ResolutionStatus.AMBIGUOUS
    store.save_resolution(_request(), r2)
    fetched = store.get_resolution("VIR-RES-TEST")
    assert fetched.resolution_status == ResolutionStatus.AMBIGUOUS


def test_schema_created_idempotently(tmp_path):
    path = str(tmp_path / "idempotent.db")
    SQLitePersistenceAdapter(path)
    SQLitePersistenceAdapter(path)  # must not raise on second init


def test_unwritable_path_raises_persistence_error():
    with pytest.raises(PersistenceError):
        SQLitePersistenceAdapter("/nonexistent_dir_xyz/impossible.db")


# -- Round-trip fidelity for nested fields -----------------------------------

def test_round_trip_preserves_nested_fields(store):
    from vir.domain.models import CanonicalVehicleIdentity, FieldEvidence, SourceEvidence

    resolution = _resolution()
    resolution.vehicle_identity = CanonicalVehicleIdentity(manufacturer="Peugeot", model="3008")
    resolution.field_evidence = [
        FieldEvidence(
            field_path="manufacturer",
            resolved_value="Peugeot",
            sources=[SourceEvidence(source_id="x", reported_value="Peugeot", reliability="high")],
        ),
    ]
    store.save_resolution(_request(), resolution)
    fetched = store.get_resolution("VIR-RES-TEST")
    assert fetched.vehicle_identity.manufacturer == "Peugeot"
    assert fetched.field_evidence[0].field_path == "manufacturer"
    assert fetched.field_evidence[0].sources[0].source_id == "x"
