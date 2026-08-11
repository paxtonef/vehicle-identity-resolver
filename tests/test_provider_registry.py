"""Tests for vir.provider_registry (P5 — Provider Router formalization).

Three concerns:
1. Registry integrity — same discipline as vir.config / vir.governance:
   missing/corrupt/schema-invalid registry blocks loading with
   ProviderRegistryError.
2. Class/declaration parity — a registry entry whose declared
   provider_id/countries/identifier_types don't match what the adapter
   class actually implements must fail loudly, not silently route wrong.
3. Registry/RGM coverage — every registered provider should have a
   matching RGM allowlist entry, so nobody adds a provider to the registry
   and forgets the RGM ends up silently denying it via default:deny (not a
   crash, just a "did you forget?" regression guard).
"""
from __future__ import annotations

import pytest

from vir import provider_registry as provider_registry_module
from vir.provider_registry import (
    ProviderRegistryError,
    load_provider_registry,
    build_providers,
)
from vir.governance import load_rgm, LightweightRGG


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
        provider_registry_module.importlib_resources,
        "files",
        lambda _pkg: _FakeAnchor(resource),
    )


# -- Registry integrity chain -----------------------------------------------

def test_missing_registry_raises(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=False))
    with pytest.raises(ProviderRegistryError, match="is missing from the installed package"):
        load_provider_registry()


def test_unreadable_registry_raises(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, raise_on_read=OSError("denied")))
    with pytest.raises(ProviderRegistryError, match="could not be read"):
        load_provider_registry()


def test_invalid_yaml_registry_raises(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=": : : not valid : ["))
    with pytest.raises(ProviderRegistryError, match="not valid YAML"):
        load_provider_registry()


def test_registry_missing_top_level_key_raises(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text="something_else: {}"))
    with pytest.raises(ProviderRegistryError, match="provider_registry"):
        load_provider_registry()


def test_registry_empty_providers_list_raises(monkeypatch):
    text = "provider_registry:\n  providers: []\n"
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=text))
    with pytest.raises(ProviderRegistryError, match="non-empty list"):
        load_provider_registry()


def test_registry_entry_missing_required_key_raises(monkeypatch):
    text = (
        "provider_registry:\n"
        "  providers:\n"
        "    - provider_id: x\n"
        "      module: vir.adapters.manual_adapter\n"
        "      class_name: ManualAdapter\n"
        # missing countries/identifier_types
    )
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=text))
    with pytest.raises(ProviderRegistryError, match="missing required key"):
        load_provider_registry()


def test_real_packaged_registry_loads_successfully():
    entries = load_provider_registry()
    assert len(entries) == 3
    assert {e["provider_id"] for e in entries} == {
        "manual_input", "provider-fr-registration", "vin-decoder-stub",
    }


# -- Class/declaration parity ------------------------------------------------

def test_build_providers_detects_wrong_declared_provider_id(monkeypatch):
    bad_entries = [{
        "provider_id": "wrong-id",  # actual adapter_id is "manual_input"
        "module": "vir.adapters.manual_adapter",
        "class_name": "ManualAdapter",
        "countries": [],
        "identifier_types": ["manual"],
    }]
    monkeypatch.setattr(provider_registry_module, "load_provider_registry", lambda: bad_entries)
    with pytest.raises(ProviderRegistryError, match="actual adapter_id"):
        build_providers()


def test_build_providers_detects_wrong_declared_countries(monkeypatch):
    bad_entries = [{
        "provider_id": "provider-fr-registration",
        "module": "vir.adapters.registration_provider_adapter",
        "class_name": "FrenchRegistrationProviderAdapter",
        "countries": ["DE"],  # actual is ["FR"]
        "identifier_types": ["registration"],
    }]
    monkeypatch.setattr(provider_registry_module, "load_provider_registry", lambda: bad_entries)
    with pytest.raises(ProviderRegistryError, match="supported_countries"):
        build_providers()


def test_build_providers_detects_unimportable_module(monkeypatch):
    bad_entries = [{
        "provider_id": "x",
        "module": "vir.adapters.does_not_exist",
        "class_name": "Whatever",
        "countries": [],
        "identifier_types": ["manual"],
    }]
    monkeypatch.setattr(provider_registry_module, "load_provider_registry", lambda: bad_entries)
    with pytest.raises(ProviderRegistryError, match="could not import module"):
        build_providers()


def test_build_providers_returns_real_working_instances():
    providers = build_providers()
    assert len(providers) == 3
    ids = {p.adapter_id for p in providers}
    assert ids == {"manual_input", "provider-fr-registration", "vin-decoder-stub"}


# -- Registry/RGM coverage guard --------------------------------------------

def test_every_registered_provider_has_a_matching_rgm_entry():
    """Regression guard: catches someone adding a provider to the registry
    without updating the RGM — not a crash (default:deny handles it safely
    at runtime), but almost certainly a forgotten step worth failing the
    test suite over."""
    entries = load_provider_registry()
    rgg = LightweightRGG(load_rgm())
    for entry in entries:
        for identifier_type in entry["identifier_types"]:
            countries_to_check = entry["countries"] or [None]
            for country in countries_to_check:
                assert rgg.is_provider_permitted(entry["provider_id"], country, identifier_type), (
                    f"Provider '{entry['provider_id']}' is in the registry for "
                    f"(country={country!r}, identifier_type={identifier_type!r}) "
                    f"but the RGM does not permit it — update rgm.yaml."
                )
