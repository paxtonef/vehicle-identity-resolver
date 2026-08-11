from __future__ import annotations

from importlib import resources as importlib_resources
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vir_log_level: str = "INFO"
    vir_default_locale: str = "fr-FR"
    vir_provider_timeout_ms: int = 5000
    vir_provider_api_key: str | None = None
    vir_store_raw_provider_payload: bool = False
    vir_database_path: str = "vir_data.db"


class ConfigurationError(RuntimeError):
    """Raised when required runner configuration is missing, unreadable, or invalid.

    This runner must never start with missing or unreadable required
    configuration while presenting itself as operational (see
    RUNNER_EXECUTION_CONTRACT.md). Any failure in the chain
    RESOURCE EXISTS -> RESOURCE READABLE -> YAML PARSES -> SCHEMA VALID ->
    REQUIRED RULES PRESENT raises this exception instead of silently
    degrading to an empty configuration.
    """


def _read_packaged_yaml(resource_name: str) -> Any:
    """Read and parse a required YAML resource packaged inside vir.resources.

    Unlike the previous implementation (which resolved a path relative to
    __file__ and returned {} on any failure), this raises ConfigurationError
    at the first point of failure, so a broken or missing resource blocks
    import of this module -- and therefore blocks application startup --
    instead of silently continuing with an empty configuration.
    """
    try:
        resource = importlib_resources.files("vir.resources").joinpath(resource_name)
        exists = resource.is_file()
    except (ModuleNotFoundError, FileNotFoundError) as exc:
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}' could not be located "
            f"in the installed package (vir.resources): {exc}"
        ) from exc

    if not exists:
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}' is missing from the "
            f"installed package. Expected it packaged at vir/resources/{resource_name}. "
            f"This usually means the package was built or installed without its "
            f"package-data (see [tool.setuptools.package-data] in pyproject.toml)."
        )

    try:
        raw = resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}' exists but could not "
            f"be read: {exc}"
        ) from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}' is not valid YAML: {exc}"
        ) from exc

    if data is None or not isinstance(data, dict):
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}' parsed to an empty or "
            f"non-mapping document. A required configuration file must not be empty."
        )

    return data


def _require_nonempty(data: dict, key: str, expected_type: type, resource_name: str) -> Any:
    value = data.get(key)
    if value is None or (isinstance(value, (dict, list)) and not value):
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}' is missing or has an "
            f"empty required key '{key}'."
        )
    if not isinstance(value, expected_type):
        raise ConfigurationError(
            f"Required configuration resource '{resource_name}': key '{key}' must be "
            f"of type {expected_type.__name__}, got {type(value).__name__}."
        )
    return value


def load_business_rules() -> dict:
    """Load and validate config/business_rules.yaml (now packaged as vir.resources).

    Required schema: a non-empty 'rules' list, each entry with 'id' and 'rule'.
    """
    data = _read_packaged_yaml("business_rules.yaml")
    rules = _require_nonempty(data, "rules", list, "business_rules.yaml")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or "id" not in rule or "rule" not in rule:
            raise ConfigurationError(
                f"business_rules.yaml: rule at index {i} is missing required "
                f"key 'id' or 'rule'."
            )
    return data


def load_confidence_weights() -> dict:
    """Load and validate config/confidence_weights.yaml (now packaged as vir.resources).

    Required schema: non-empty 'weights' and 'levels' mappings.
    """
    data = _read_packaged_yaml("confidence_weights.yaml")
    _require_nonempty(data, "weights", dict, "confidence_weights.yaml")
    _require_nonempty(data, "levels", dict, "confidence_weights.yaml")
    return data


def load_vehicle_taxonomy() -> dict:
    """Load and validate config/vehicle_taxonomy.yaml (now packaged as vir.resources).

    Required schema: a non-empty 'taxonomy' mapping.
    """
    data = _read_packaged_yaml("vehicle_taxonomy.yaml")
    _require_nonempty(data, "taxonomy", dict, "vehicle_taxonomy.yaml")
    return data


# Eager load at import time: this is what turns a configuration defect into a
# blocked startup (import failure) instead of a silently degraded runtime.
settings = Settings()
business_rules_config = load_business_rules()
confidence_config = load_confidence_weights()
taxonomy_config = load_vehicle_taxonomy()
