from __future__ import annotations

from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vir_log_level: str = "INFO"
    vir_default_locale: str = "fr-FR"
    vir_provider_timeout_ms: int = 5000
    vir_provider_api_key: str | None = None
    vir_store_raw_provider_payload: bool = False


def load_yaml_config(name: str) -> dict:
    """Load a YAML configuration file from the config/ directory."""
    # Look relative to this file: src/vir/config.py -> project_root/config/
    config_path = Path(__file__).parent.parent.parent / "config" / f"{name}.yaml"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


settings = Settings()
taxonomy_config = load_yaml_config("vehicle_taxonomy")
confidence_config = load_yaml_config("confidence_weights")
business_rules_config = load_yaml_config("business_rules")
