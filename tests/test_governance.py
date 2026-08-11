"""Tests for vir.governance (P4 — Lightweight RGG).

Two concerns, kept separate:
1. RGM integrity — same discipline as vir.config (P0.1): a missing,
   corrupt, or schema-invalid RGM must block loading with
   RuntimeGovernanceError, not silently leave every provider unchecked.
2. RGG decision logic — default:deny actually blocks an unlisted provider,
   and the real, packaged allowlist matches the runner's actual registered
   providers (so this closure doesn't silently break the existing
   Manual/FR-registration/VIN-decoder providers).

A third test guards against the markdown documentation
(RUNTIME_GOVERNANCE_MANIFEST.md) silently drifting from the packaged,
enforced rgm.yaml — the exact failure mode P0.1 fixed for configuration,
applied here to governance documentation.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from vir import governance as governance_module
from vir.governance import (
    RuntimeGovernanceError,
    LightweightRGG,
    load_rgm,
)


class _FakeResource:
    def __init__(self, exists: bool = True, text: str | None = None, raise_on_read: Exception | None = None):
        self._exists = exists
        self._text = text
        self._raise_on_read = raise_on_read

    def is_file(self) -> bool:
        return self._exists

    def read_text(self, encoding: str = "utf-8") -> str:
        if self._raise_on_read:
            raise self._raise_on_read
        return self._text or ""


class _FakeAnchor:
    def __init__(self, resource: _FakeResource):
        self._resource = resource

    def joinpath(self, name: str) -> _FakeResource:
        return self._resource


def _patch_resource(monkeypatch, resource: _FakeResource) -> None:
    monkeypatch.setattr(
        governance_module.importlib_resources,
        "files",
        lambda _pkg: _FakeAnchor(resource),
    )


# -- RGM integrity chain (mirrors test_config_integrity.py's discipline) ---

def test_missing_rgm_raises_runtime_governance_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=False))
    with pytest.raises(RuntimeGovernanceError, match="is missing from the installed package"):
        load_rgm()


def test_unreadable_rgm_raises_runtime_governance_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, raise_on_read=OSError("denied")))
    with pytest.raises(RuntimeGovernanceError, match="could not be read"):
        load_rgm()


def test_invalid_yaml_rgm_raises_runtime_governance_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=": : : not valid yaml : ["))
    with pytest.raises(RuntimeGovernanceError, match="not valid YAML"):
        load_rgm()


def test_rgm_missing_top_level_key_raises(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text="something_else: {}"))
    with pytest.raises(RuntimeGovernanceError, match="runtime_governance_manifest"):
        load_rgm()


def test_rgm_missing_external_services_raises(monkeypatch):
    _patch_resource(
        monkeypatch,
        _FakeResource(exists=True, text="runtime_governance_manifest:\n  version: '0.1.0'\n"),
    )
    with pytest.raises(RuntimeGovernanceError, match="external_services"):
        load_rgm()


def test_rgm_invalid_default_value_raises(monkeypatch):
    text = (
        "runtime_governance_manifest:\n"
        "  external_services:\n"
        "    default: maybe\n"
        "    allowed:\n"
        "      - provider_id: x\n"
        "        countries: []\n"
        "        identifier_types: [vin]\n"
    )
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=text))
    with pytest.raises(RuntimeGovernanceError, match="'deny' or 'allow'"):
        load_rgm()


def test_rgm_empty_allowed_list_raises(monkeypatch):
    text = (
        "runtime_governance_manifest:\n"
        "  external_services:\n"
        "    default: deny\n"
        "    allowed: []\n"
    )
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=text))
    with pytest.raises(RuntimeGovernanceError, match="non-empty list"):
        load_rgm()


def test_real_packaged_rgm_loads_successfully():
    """Positive control: the actual packaged RGM must load without error."""
    rgm = load_rgm()
    assert rgm["external_services"]["default"] == "deny"
    assert len(rgm["external_services"]["allowed"]) >= 3


# -- RGG decision logic -----------------------------------------------------

def test_default_deny_blocks_unlisted_provider():
    rgm = {
        "external_services": {
            "default": "deny",
            "allowed": [
                {"provider_id": "known-provider", "countries": [], "identifier_types": ["vin"]},
            ],
        }
    }
    rgg = LightweightRGG(rgm)
    assert rgg.is_provider_permitted("known-provider", None, "vin") is True
    assert rgg.is_provider_permitted("unknown-provider", None, "vin") is False


def test_country_scoped_entry_only_matches_listed_countries():
    rgm = {
        "external_services": {
            "default": "deny",
            "allowed": [
                {"provider_id": "fr-provider", "countries": ["FR"], "identifier_types": ["registration"]},
            ],
        }
    }
    rgg = LightweightRGG(rgm)
    assert rgg.is_provider_permitted("fr-provider", "FR", "registration") is True
    assert rgg.is_provider_permitted("fr-provider", "DE", "registration") is False


def test_identifier_type_must_match():
    rgm = {
        "external_services": {
            "default": "deny",
            "allowed": [
                {"provider_id": "vin-only-provider", "countries": [], "identifier_types": ["vin"]},
            ],
        }
    }
    rgg = LightweightRGG(rgm)
    assert rgg.is_provider_permitted("vin-only-provider", None, "vin") is True
    assert rgg.is_provider_permitted("vin-only-provider", None, "registration") is False


def test_default_allow_permits_unlisted_provider():
    rgm = {
        "external_services": {
            "default": "allow",
            "allowed": [
                {"provider_id": "known-provider", "countries": [], "identifier_types": ["vin"]},
            ],
        }
    }
    rgg = LightweightRGG(rgm)
    assert rgg.is_provider_permitted("anything-else", None, "vin") is True


def test_real_rgm_permits_all_currently_registered_providers():
    """The packaged allowlist must exactly cover the runner's real,
    registered providers — this is the regression guard proving P4 doesn't
    silently break Manual/FR-registration/VIN-decoder resolution."""
    rgm = load_rgm()
    rgg = LightweightRGG(rgm)
    assert rgg.is_provider_permitted("manual_input", None, "manual") is True
    assert rgg.is_provider_permitted("provider-fr-registration", "FR", "registration") is True
    assert rgg.is_provider_permitted("vin-decoder-stub", None, "vin") is True
    # And a provider that was never registered must still be denied by default.
    assert rgg.is_provider_permitted("some-future-unlisted-provider", None, "vin") is False


@pytest.mark.asyncio
async def test_unlisted_provider_is_actually_skipped_through_the_real_engine():
    """End-to-end proof (not just a LightweightRGG unit check): an unlisted
    provider wired into ResolutionEngine must be silently skipped by
    _query_providers — the resolution degrades to INSUFFICIENT_DATA rather
    than crashing or, worse, silently using data from a non-permitted
    source."""
    from vir.domain.enums import ResolutionStatus
    from vir.domain.models import VehicleIdentityRequest, ConsentInput, ProviderVehicleRecord, CanonicalVehicleIdentity
    from vir.domain.resolution import ResolutionEngine
    from vir.ports.vehicle_provider import VehicleDataProvider

    class _UnlistedProvider(VehicleDataProvider):
        adapter_id = "totally-unlisted-provider"
        supported_countries: list[str] = []
        supported_identifier_types = ["vin"]

        async def resolve_registration(self, number, country):
            raise NotImplementedError

        async def decode_vin(self, vin: str) -> list[ProviderVehicleRecord]:
            # If this ever gets called, governance failed to block it.
            return [ProviderVehicleRecord(
                provider_record_id="SHOULD-NOT-APPEAR",
                adapter_id=self.adapter_id,
                normalized_candidate=CanonicalVehicleIdentity(manufacturer="ShouldNotAppear"),
                provider_confidence=0.99,
            )]

        async def retrieve_vehicle_configuration(self, **kwargs):
            raise NotImplementedError

    engine = ResolutionEngine(providers=[_UnlistedProvider()])
    request = VehicleIdentityRequest(
        request_id="RGG-BLOCK-TEST",
        vin="VF3XXXXXXXXXXXXXX",
        consent=ConsentInput(external_lookup_allowed=True),
    )
    resolution = await engine.resolve(request)

    assert resolution.resolution_status == ResolutionStatus.INSUFFICIENT_DATA
    assert resolution.vehicle_identity is None
    assert all(
        s.source_id != "totally-unlisted-provider" for s in resolution.source_summary
    )


# -- Documentation parity (prevents the RGM markdown from going stale) -----

def test_markdown_and_packaged_rgm_match():
    repo_root = Path(__file__).resolve().parent.parent
    markdown_path = repo_root / "RUNTIME_GOVERNANCE_MANIFEST.md"
    packaged_path = repo_root / "src" / "vir" / "resources" / "rgm.yaml"

    markdown_content = markdown_path.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*?)\n```", markdown_content, re.DOTALL)
    assert match, "RUNTIME_GOVERNANCE_MANIFEST.md must contain a ```yaml``` block"
    markdown_yaml = yaml.safe_load(match.group(1))

    packaged_yaml = yaml.safe_load(packaged_path.read_text(encoding="utf-8"))

    assert markdown_yaml == packaged_yaml, (
        "RUNTIME_GOVERNANCE_MANIFEST.md's embedded YAML has drifted from "
        "src/vir/resources/rgm.yaml (the enforced source of truth). "
        "Update whichever one is stale."
    )
