"""Tests for the Web Product Layer (P6) — server-rendered HTML forms.

Uses FastAPI's TestClient against an isolated, temporary SQLite database
(same isolation pattern as test_api_persistence.py) so these never touch
a real vir_data.db.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from vir.adapters.sqlite_persistence_adapter import SQLitePersistenceAdapter
    import vir.api.routes as routes_module
    import vir.web.routes as web_routes_module

    isolated_store = SQLitePersistenceAdapter(str(tmp_path / "test_web.db"))
    monkeypatch.setattr(routes_module, "STORE", isolated_store)
    monkeypatch.setattr(web_routes_module, "STORE", isolated_store)

    return TestClient(routes_module.app)


def test_index_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Vehicle Identity Resolver" in resp.text
    assert 'action="/resolve"' in resp.text


def test_resolve_form_vin_shows_resolved_status(client):
    resp = client.post("/resolve", data={"vin": "VF3XXXXXXXXXXXXXX", "consent": "yes"})
    assert resp.status_code == 200
    assert 'class="status-badge status-resolved"' in resp.text
    assert "Résolu" in resp.text
    assert "Peugeot" in resp.text


def test_resolve_form_without_consent_shows_error_not_crash(client):
    resp = client.post("/resolve", data={"vin": "VF3XXXXXXXXXXXXXX"})
    assert resp.status_code == 200  # rendered error page, not a 500
    assert '<div class="error-box">' in resp.text
    assert "not authorized" in resp.text.lower() or "authoriz" in resp.text.lower()


def test_resolve_form_ambiguous_shows_clarification_form(client):
    resp = client.post(
        "/resolve",
        data={"registration_number": "AM-BIG-01", "country_code": "FR", "consent": "yes"},
    )
    assert resp.status_code == 200
    assert 'class="status-badge status-ambiguous"' in resp.text
    assert "/clarify/" in resp.text


def test_full_clarify_round_trip_through_forms(client):
    resolve_resp = client.post(
        "/resolve",
        data={"registration_number": "AM-BIG-01", "country_code": "FR", "consent": "yes"},
    )
    assert "/clarify/" in resolve_resp.text

    import re
    match = re.search(r'/clarify/([A-Za-z0-9-]+)', resolve_resp.text)
    assert match, "expected a clarify form action in the ambiguous result page"
    resolution_id = match.group(1)

    clarify_resp = client.post(
        f"/clarify/{resolution_id}",
        data={"answer__VIR-Q-001": "81"},
    )
    assert clarify_resp.status_code == 200
    assert '<div class="error-box">' not in clarify_resp.text


def test_clarify_unknown_resolution_shows_error_not_crash(client):
    resp = client.post("/clarify/DOES-NOT-EXIST", data={"answer__VIR-Q-VIN": "VF3XXXXXXXXXXXXXX"})
    assert resp.status_code == 200
    assert '<div class="error-box">' in resp.text
    assert "introuvable" in resp.text.lower()


def test_resolve_form_invalid_vin_shows_error_not_crash(client):
    resp = client.post("/resolve", data={"vin": "TOO-SHORT", "consent": "yes"})
    assert resp.status_code == 200
    assert '<div class="error-box">' in resp.text


def test_manual_only_resolution_does_not_require_consent(client):
    """Manual-only input must work even with consent unchecked, per
    USER_INTERACTION_CONTRACT.md section 5."""
    resp = client.post(
        "/resolve",
        data={"manufacturer": "Renault", "model": "Clio", "production_year": "2019"},
    )
    assert resp.status_code == 200
    assert '<div class="error-box">' not in resp.text
