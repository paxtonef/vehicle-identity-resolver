"""Tests for vir.config's configuration integrity chain (P0.1).

Invariant under test: a runner must never start with missing or unreadable
required configuration while presenting itself as operational. These are
negative tests — they verify that a broken, missing, or schema-invalid
required configuration resource blocks loading with a ConfigurationError,
instead of silently degrading to an empty config (the bug this fixes).

Chain verified: RESOURCE EXISTS -> RESOURCE READABLE -> YAML PARSES ->
SCHEMA VALID -> REQUIRED RULES PRESENT.
"""
from __future__ import annotations

import pytest

from vir import config as vir_config
from vir.config import ConfigurationError


class _FakeResource:
    """Stand-in for an importlib.resources.Traversable, to simulate
    missing/unreadable/corrupt packaged files without touching the real
    installed package."""

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
        vir_config.importlib_resources,
        "files",
        lambda _pkg: _FakeAnchor(resource),
    )


# -- RESOURCE EXISTS ----------------------------------------------------

def test_missing_resource_raises_configuration_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=False))
    with pytest.raises(ConfigurationError, match="is missing from the installed package"):
        vir_config._read_packaged_yaml("business_rules.yaml")


# -- RESOURCE READABLE ----------------------------------------------------

def test_unreadable_resource_raises_configuration_error(monkeypatch):
    _patch_resource(
        monkeypatch,
        _FakeResource(exists=True, raise_on_read=OSError("permission denied")),
    )
    with pytest.raises(ConfigurationError, match="could not be read"):
        vir_config._read_packaged_yaml("business_rules.yaml")


# -- YAML PARSES ----------------------------------------------------

def test_invalid_yaml_raises_configuration_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=": : : not valid yaml : ["))
    with pytest.raises(ConfigurationError, match="not valid YAML"):
        vir_config._read_packaged_yaml("business_rules.yaml")


def test_empty_document_raises_configuration_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text=""))
    with pytest.raises(ConfigurationError, match="empty or non-mapping"):
        vir_config._read_packaged_yaml("business_rules.yaml")


# -- SCHEMA VALID / REQUIRED RULES PRESENT --------------------------------

def test_business_rules_empty_list_raises_configuration_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text="rules: []"))
    with pytest.raises(ConfigurationError, match="empty required key 'rules'"):
        vir_config.load_business_rules()


def test_business_rules_missing_id_raises_configuration_error(monkeypatch):
    _patch_resource(
        monkeypatch,
        _FakeResource(exists=True, text="rules:\n  - rule: 'no id field'\n"),
    )
    with pytest.raises(ConfigurationError, match="missing required key 'id' or 'rule'"):
        vir_config.load_business_rules()


def test_confidence_weights_missing_levels_raises_configuration_error(monkeypatch):
    _patch_resource(
        monkeypatch,
        _FakeResource(exists=True, text="weights:\n  identifier_quality: 0.5\n"),
    )
    with pytest.raises(ConfigurationError, match="empty required key 'levels'"):
        vir_config.load_confidence_weights()


def test_vehicle_taxonomy_missing_taxonomy_key_raises_configuration_error(monkeypatch):
    _patch_resource(monkeypatch, _FakeResource(exists=True, text="normalization: {}"))
    with pytest.raises(ConfigurationError, match="empty required key 'taxonomy'"):
        vir_config.load_vehicle_taxonomy()


# -- RUNNER READY (positive control) --------------------------------------

def test_real_packaged_resources_load_successfully():
    """The actual packaged YAML files must load without error — this is the
    positive control confirming the chain doesn't over-fire on valid input."""
    assert vir_config.load_business_rules()["rules"]
    assert vir_config.load_confidence_weights()["weights"]
    assert vir_config.load_vehicle_taxonomy()["taxonomy"]
