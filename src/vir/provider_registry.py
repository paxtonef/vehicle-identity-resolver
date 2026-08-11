"""Provider Registry — P5 (Provider Router formalization).

Single source of truth for which provider adapter classes exist and how to
instantiate them, replacing the two previously-duplicated `_DEFAULT_PROVIDERS`
lists in `api/routes.py` and `cli/main.py`.

Follows the same integrity discipline as `vir.config` (P0.1) and
`vir.governance` (P4): RESOURCE EXISTS -> READABLE -> PARSES -> SCHEMA VALID,
raising explicitly rather than silently degrading — a runner must never
start with a provider list it failed to load correctly.

This module does NOT decide whether a provider is *permitted* to be called
(that's `vir.governance.RGG`, unchanged) — it only decides which adapter
*instances* exist. Provider selection combining "does this provider support
the request" with "is it permitted" still happens in
`ResolutionEngine._query_providers`.
"""
from __future__ import annotations

import importlib
from importlib import resources as importlib_resources
from typing import Any

import yaml

from vir.ports.vehicle_provider import VehicleDataProvider


class ProviderRegistryError(RuntimeError):
    """Raised when the Provider Registry is missing, unreadable, invalid, or
    when a declared adapter class doesn't match what it actually implements
    (mirrors vir.config.ConfigurationError / vir.governance.RuntimeGovernanceError)."""


def _read_packaged_yaml(resource_name: str) -> Any:
    try:
        resource = importlib_resources.files("vir.resources").joinpath(resource_name)
        exists = resource.is_file()
    except (ModuleNotFoundError, FileNotFoundError) as exc:
        raise ProviderRegistryError(
            f"Required registry resource '{resource_name}' could not be located "
            f"in the installed package (vir.resources): {exc}"
        ) from exc

    if not exists:
        raise ProviderRegistryError(
            f"Required registry resource '{resource_name}' is missing from the "
            f"installed package. Expected it packaged at vir/resources/{resource_name}."
        )

    try:
        raw = resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProviderRegistryError(
            f"Required registry resource '{resource_name}' exists but could not "
            f"be read: {exc}"
        ) from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ProviderRegistryError(
            f"Required registry resource '{resource_name}' is not valid YAML: {exc}"
        ) from exc

    if data is None or not isinstance(data, dict):
        raise ProviderRegistryError(
            f"Required registry resource '{resource_name}' parsed to an empty or "
            f"non-mapping document."
        )

    return data


def load_provider_registry() -> list[dict]:
    """Load and validate the provider registry.

    Required schema: a top-level 'provider_registry.providers' non-empty
    list, each entry needing provider_id/module/class_name/countries/
    identifier_types.
    """
    data = _read_packaged_yaml("provider_registry.yaml")

    root = data.get("provider_registry")
    if not isinstance(root, dict):
        raise ProviderRegistryError(
            "provider_registry.yaml: missing or empty required top-level key "
            "'provider_registry'."
        )

    providers = root.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ProviderRegistryError(
            "provider_registry.yaml: 'providers' must be a non-empty list."
        )

    required_keys = {"provider_id", "module", "class_name", "countries", "identifier_types"}
    for i, entry in enumerate(providers):
        if not isinstance(entry, dict):
            raise ProviderRegistryError(f"provider_registry.yaml: providers[{i}] is not a mapping.")
        missing = required_keys - entry.keys()
        if missing:
            raise ProviderRegistryError(
                f"provider_registry.yaml: providers[{i}] "
                f"('{entry.get('provider_id', '?')}') is missing required key(s): "
                f"{sorted(missing)}."
            )

    return providers


def _instantiate(entry: dict) -> VehicleDataProvider:
    module_name = entry["module"]
    class_name = entry["class_name"]
    provider_id = entry["provider_id"]

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProviderRegistryError(
            f"Provider '{provider_id}': could not import module '{module_name}': {exc}"
        ) from exc

    cls = getattr(module, class_name, None)
    if cls is None:
        raise ProviderRegistryError(
            f"Provider '{provider_id}': module '{module_name}' has no class "
            f"'{class_name}'."
        )

    instance = cls()

    # Cross-check: the registry's declared countries/identifier_types must
    # match what the adapter class actually implements. A mismatch here
    # means the registry and the code have drifted — exactly the failure
    # mode the parity discipline elsewhere in this project (P0.1, P3/P4)
    # exists to catch before it becomes a silent routing bug.
    if instance.adapter_id != provider_id:
        raise ProviderRegistryError(
            f"Provider registry declares provider_id='{provider_id}' for "
            f"{module_name}.{class_name}, but the class's actual adapter_id "
            f"is '{instance.adapter_id}'."
        )
    if set(instance.supported_countries) != set(entry["countries"]):
        raise ProviderRegistryError(
            f"Provider '{provider_id}': registry declares countries="
            f"{entry['countries']}, but the class's actual supported_countries "
            f"is {instance.supported_countries}."
        )
    if set(instance.supported_identifier_types) != set(entry["identifier_types"]):
        raise ProviderRegistryError(
            f"Provider '{provider_id}': registry declares identifier_types="
            f"{entry['identifier_types']}, but the class's actual "
            f"supported_identifier_types is {instance.supported_identifier_types}."
        )

    return instance


def build_providers() -> list[VehicleDataProvider]:
    """Build and return the list of provider instances declared in the
    registry — the single place both api/routes.py and cli/main.py now get
    their provider list from, instead of each hardcoding their own copy."""
    entries = load_provider_registry()
    return [_instantiate(entry) for entry in entries]
