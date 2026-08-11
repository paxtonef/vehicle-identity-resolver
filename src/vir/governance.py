"""Lightweight Runtime Governance Gate (RGG) — P4.

Loads the Runtime Governance Manifest (RGM, P3) and provides the one
decision point it currently defines with no Core equivalent:
`external_services` — whether a given provider is permitted to be called
for a given (country, identifier_type) combination.

Design notes (per the P2 -> P2.5 -> P3 -> P4 sequence this follows):
- This module does NOT re-implement anything already enforced by VIR Core
  (see domain/invariants.py and P2_5_CORE_GOVERNANCE_CLOSURE.md). It only
  answers "is this provider call permitted", the one rule P2/P3 identified
  as genuinely belonging to runtime governance rather than the resolution
  engine itself.
- The RGM is loaded with the same integrity discipline as vir.config
  (P0.1): RESOURCE EXISTS -> READABLE -> PARSES -> SCHEMA VALID, raising
  explicitly instead of silently degrading. A runner must never start
  claiming to enforce a governance policy it failed to load.
"""
from __future__ import annotations

from importlib import resources as importlib_resources
from typing import Any

import yaml


class RuntimeGovernanceError(RuntimeError):
    """Raised when the Runtime Governance Manifest is missing, unreadable,
    or invalid — mirrors vir.config.ConfigurationError's discipline, kept
    as a distinct exception type because a broken RGM is a governance
    failure, not a plain configuration failure, and callers may want to
    handle the two differently."""


def _read_packaged_yaml(resource_name: str) -> Any:
    try:
        resource = importlib_resources.files("vir.resources").joinpath(resource_name)
        exists = resource.is_file()
    except (ModuleNotFoundError, FileNotFoundError) as exc:
        raise RuntimeGovernanceError(
            f"Required governance resource '{resource_name}' could not be located "
            f"in the installed package (vir.resources): {exc}"
        ) from exc

    if not exists:
        raise RuntimeGovernanceError(
            f"Required governance resource '{resource_name}' is missing from the "
            f"installed package. Expected it packaged at vir/resources/{resource_name}."
        )

    try:
        raw = resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeGovernanceError(
            f"Required governance resource '{resource_name}' exists but could not "
            f"be read: {exc}"
        ) from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RuntimeGovernanceError(
            f"Required governance resource '{resource_name}' is not valid YAML: {exc}"
        ) from exc

    if data is None or not isinstance(data, dict):
        raise RuntimeGovernanceError(
            f"Required governance resource '{resource_name}' parsed to an empty or "
            f"non-mapping document."
        )

    return data


def load_rgm() -> dict:
    """Load and validate the Runtime Governance Manifest.

    Required schema: a top-level 'runtime_governance_manifest' mapping
    containing a non-empty 'external_services' block with 'default' and
    an 'allowed' list (each entry needs provider_id/countries/identifier_types).
    """
    data = _read_packaged_yaml("rgm.yaml")

    root = data.get("runtime_governance_manifest")
    if not isinstance(root, dict):
        raise RuntimeGovernanceError(
            "rgm.yaml: missing or empty required top-level key "
            "'runtime_governance_manifest'."
        )

    ext = root.get("external_services")
    if not isinstance(ext, dict):
        raise RuntimeGovernanceError(
            "rgm.yaml: missing or empty required key 'external_services'."
        )

    if ext.get("default") not in ("deny", "allow"):
        raise RuntimeGovernanceError(
            "rgm.yaml: external_services.default must be 'deny' or 'allow', "
            f"got {ext.get('default')!r}."
        )

    allowed = ext.get("allowed")
    if not isinstance(allowed, list) or not allowed:
        raise RuntimeGovernanceError(
            "rgm.yaml: external_services.allowed must be a non-empty list."
        )

    for i, entry in enumerate(allowed):
        if not isinstance(entry, dict) or "provider_id" not in entry:
            raise RuntimeGovernanceError(
                f"rgm.yaml: external_services.allowed[{i}] is missing required "
                f"key 'provider_id'."
            )
        if "countries" not in entry or "identifier_types" not in entry:
            raise RuntimeGovernanceError(
                f"rgm.yaml: external_services.allowed[{i}] "
                f"('{entry.get('provider_id')}') is missing 'countries' or "
                f"'identifier_types'."
            )

    return root


class LightweightRGG:
    """Answers runtime governance questions against a loaded RGM.

    Currently implements exactly one decision: is a given provider
    permitted to be called for a given country + identifier_type. This is
    intentionally minimal — see RUNTIME_GOVERNANCE_MANIFEST.md's "What P3
    Deliberately Does Not Do" for what is explicitly out of scope.
    """

    def __init__(self, rgm: dict):
        self._rgm = rgm
        ext = rgm["external_services"]
        self._default_deny = ext["default"] == "deny"
        self._allowed = ext["allowed"]

    def is_provider_permitted(
        self,
        provider_id: str,
        country: str | None,
        identifier_type: str,
    ) -> bool:
        """RGM decision point:

            Provider registered
                  +
            technical compatibility
                  |
                  v
            Governance policy
                  |
                  v
            Is this provider permitted?
                ├─ NO  -> block (return False)
                └─ YES -> execute (return True)

        An entry matches when provider_id matches AND (its countries list
        is empty, meaning "not country-scoped", OR the requested country is
        in it) AND the requested identifier_type is in its identifier_types.
        """
        for entry in self._allowed:
            if entry["provider_id"] != provider_id:
                continue
            entry_countries = entry.get("countries") or []
            if entry_countries and country not in entry_countries:
                continue
            if identifier_type not in (entry.get("identifier_types") or []):
                continue
            return True

        return not self._default_deny


# Eager load at import time: a governance policy that fails to load must
# block startup, not silently leave every provider call unchecked (same
# discipline as vir.config, P0.1).
RGM = load_rgm()
RGG = LightweightRGG(RGM)
