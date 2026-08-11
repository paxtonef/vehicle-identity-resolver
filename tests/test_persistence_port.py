"""Tests proving PersistencePort substitutability — the concrete
architectural requirement behind SQLite-behind-a-port:

    PersistencePort
          |
          +-- SQLitePersistenceAdapter    <- now
          +-- PostgreSQLAdapter           <- later, not yet implemented

If the API/Web layer only ever calls PersistencePort's interface (not
SQLite-specific behavior), then a completely different implementation —
here, a trivial in-memory one, standing in for "some future adapter" —
must work as a drop-in replacement with zero changes to any caller. This
test proves that, rather than asserting it by architecture diagram alone.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vir.ports.persistence_port import PersistencePort
from vir.domain.models import VehicleIdentityRequest, VehicleIdentityResolution


class _InMemoryPersistenceAdapter(PersistencePort):
    """A second, independent PersistencePort implementation — not SQLite,
    not sharing any code with SQLitePersistenceAdapter beyond the port
    contract itself. Exists only to prove substitutability."""

    def __init__(self):
        self._resolutions: dict[str, VehicleIdentityResolution] = {}
        self._requests: dict[str, VehicleIdentityRequest] = {}

    def save_resolution(self, request: VehicleIdentityRequest, resolution: VehicleIdentityResolution) -> None:
        self._resolutions[resolution.resolution_id] = resolution
        self._requests[resolution.resolution_id] = request

    def get_resolution(self, resolution_id: str) -> VehicleIdentityResolution | None:
        return self._resolutions.get(resolution_id)

    def get_request(self, resolution_id: str) -> VehicleIdentityRequest | None:
        return self._requests.get(resolution_id)


def test_in_memory_adapter_satisfies_the_port_interface():
    """A completely independent implementation instantiates and type-checks
    as a PersistencePort — the ABC's abstractmethods are all satisfied."""
    adapter = _InMemoryPersistenceAdapter()
    assert isinstance(adapter, PersistencePort)


def test_sqlite_adapter_also_satisfies_the_port_interface(tmp_path):
    from vir.adapters.sqlite_persistence_adapter import SQLitePersistenceAdapter

    adapter = SQLitePersistenceAdapter(str(tmp_path / "test.db"))
    assert isinstance(adapter, PersistencePort)


def test_port_cannot_be_instantiated_directly():
    """The ABC itself is abstract — callers must go through a concrete
    adapter, never the port directly."""
    with pytest.raises(TypeError):
        PersistencePort()


@pytest.fixture
def client_with_in_memory_store(monkeypatch):
    """The real test: swap the API's STORE for a completely different
    PersistencePort implementation and confirm the API layer doesn't
    notice or care — proving it depends on the port, not on SQLite."""
    import vir.api.routes as routes_module
    import vir.web.routes as web_routes_module

    in_memory_store = _InMemoryPersistenceAdapter()
    monkeypatch.setattr(routes_module, "STORE", in_memory_store)
    monkeypatch.setattr(web_routes_module, "STORE", in_memory_store)

    return TestClient(routes_module.app)


def test_api_works_unchanged_against_a_non_sqlite_adapter(client_with_in_memory_store):
    client = client_with_in_memory_store

    resolve_resp = client.post(
        "/v1/vehicle-identities/resolve",
        json={
            "request_id": "PORT-TEST",
            "vin": "VF3XXXXXXXXXXXXXX",
            "consent": {"external_lookup_allowed": True},
        },
    )
    assert resolve_resp.status_code == 200
    resolution_id = resolve_resp.json()["resolution_id"]

    get_resp = client.get(f"/v1/vehicle-identities/{resolution_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["resolution_id"] == resolution_id

    handoff_resp = client.get(f"/v1/vehicle-identities/{resolution_id}/handoff/diagnostic")
    assert handoff_resp.status_code == 200


def test_web_layer_works_unchanged_against_a_non_sqlite_adapter(client_with_in_memory_store):
    client = client_with_in_memory_store

    resp = client.post("/resolve", data={"vin": "VF3XXXXXXXXXXXXXX", "consent": "yes"})
    assert resp.status_code == 200
    assert 'class="status-badge status-resolved"' in resp.text
