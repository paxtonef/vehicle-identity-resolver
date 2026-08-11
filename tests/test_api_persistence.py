"""Integration tests for the 3 endpoints unblocked by Persistence (P6):
GET /v1/vehicle-identities/{id}, POST .../clarifications,
GET .../handoff/diagnostic.

Uses FastAPI's TestClient against an isolated, temporary SQLite database
(monkeypatched onto the app's STORE) so these tests never touch a real
vir_data.db and can't interfere with each other.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from vir.adapters.sqlite_persistence_adapter import SQLitePersistenceAdapter
    import vir.api.routes as routes_module

    isolated_store = SQLitePersistenceAdapter(str(tmp_path / "test_api.db"))
    monkeypatch.setattr(routes_module, "STORE", isolated_store)

    return TestClient(routes_module.app)


def _resolve_payload(**overrides):
    payload = {
        "request_id": "API-TEST",
        "vin": "VF3XXXXXXXXXXXXXX",
        "consent": {"external_lookup_allowed": True},
    }
    payload.update(overrides)
    return payload


def test_resolve_then_get_by_id_round_trips(client):
    resolve_resp = client.post("/v1/vehicle-identities/resolve", json=_resolve_payload())
    assert resolve_resp.status_code == 200
    resolution_id = resolve_resp.json()["resolution_id"]

    get_resp = client.get(f"/v1/vehicle-identities/{resolution_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["resolution_id"] == resolution_id
    assert get_resp.json()["resolution_status"] == "resolved"


def test_get_nonexistent_resolution_returns_404(client):
    resp = client.get("/v1/vehicle-identities/DOES-NOT-EXIST")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "VIR-ERR-010"


def test_handoff_diagnostic_returns_data_for_stored_resolution(client):
    resolve_resp = client.post("/v1/vehicle-identities/resolve", json=_resolve_payload())
    resolution_id = resolve_resp.json()["resolution_id"]

    handoff_resp = client.get(f"/v1/vehicle-identities/{resolution_id}/handoff/diagnostic")
    assert handoff_resp.status_code == 200
    data = handoff_resp.json()
    assert data["resolution_id"] == resolution_id
    assert data["identity_status"] == "resolved"
    assert "confidence_score" in data["diagnostic_constraints"]


def test_handoff_diagnostic_404_for_unknown_resolution(client):
    resp = client.get("/v1/vehicle-identities/DOES-NOT-EXIST/handoff/diagnostic")
    assert resp.status_code == 404


def test_clarification_produces_a_new_stored_resolution(client):
    resolve_resp = client.post(
        "/v1/vehicle-identities/resolve",
        json=_resolve_payload(
            vin=None,
            registration={"registration_number": "AM-BIG-01", "country_code": "FR"},
        ),
    )
    assert resolve_resp.status_code == 200
    original = resolve_resp.json()
    assert original["resolution_status"] == "ambiguous"
    original_id = original["resolution_id"]

    clarify_resp = client.post(
        f"/v1/vehicle-identities/{original_id}/clarifications",
        json={"answers": [{"question_id": "VIR-Q-001", "value": 81}]},
    )
    assert clarify_resp.status_code == 200
    new_resolution = clarify_resp.json()
    # A new resolution_id is generated (documented behavior — see
    # P6_PERSISTENCE_AND_WEB_LAYER.md: this reactivated the pre-existing
    # ClarifyResolutionUseCase as-is, which does not link back to the
    # original resolution_id).
    assert new_resolution["resolution_id"] != original_id
    # The new resolution must itself now be independently fetchable.
    get_resp = client.get(f"/v1/vehicle-identities/{new_resolution['resolution_id']}")
    assert get_resp.status_code == 200


def test_clarification_404_for_unknown_resolution(client):
    resp = client.post(
        "/v1/vehicle-identities/DOES-NOT-EXIST/clarifications",
        json={"answers": [{"question_id": "VIR-Q-VIN", "value": "VF3XXXXXXXXXXXXXX"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "VIR-ERR-010"
