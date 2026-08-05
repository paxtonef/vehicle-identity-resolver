from __future__ import annotations

from typing import Any

from vir.domain.enums import ContradictionType
from vir.domain.models import (
    VehicleCandidate,
    VehicleIdentityRequest,
    Contradiction,
    ContradictionValue,
    CanonicalVehicleIdentity,
)


class ContradictionEngine:
    """Detects genuine cross-source contradictions.

    Provenance-aware rule:
      - differing values for a field within a single `adapter_id` (source)
        represent that source's own ambiguity (e.g. a plate matching
        several motorisations) and are NOT reported as a contradiction;
      - incompatible values for the same field across at least two
        independent `adapter_id` values ARE reported as a contradiction.

    "Independent sources are compatible" means their asserted value sets
    share at least one common value (e.g. one ambiguous source offering
    {81, 96, 73} kW and another source confirming 81 kW are compatible,
    not contradictory).
    """

    def detect(
        self,
        candidates: list[VehicleCandidate],
        request: VehicleIdentityRequest,
    ) -> list[Contradiction]:
        contradictions: list[Contradiction] = []

        # field_path -> source_id -> list of original values asserted by that source
        field_source_values: dict[str, dict[str, list[Any]]] = {}

        def register(field_path: str, value: Any, source_id: str) -> None:
            if value is None:
                return
            field_source_values.setdefault(field_path, {}).setdefault(source_id, []).append(value)

        # Add user input as a source
        user_source = "user_input"
        mi = request.manual_identity
        register("manufacturer", mi.manufacturer, user_source)
        register("model", mi.model, user_source)
        if mi.fuel_type:
            register("fuel.primary_type", mi.fuel_type.lower(), user_source)
        if mi.engine_power_kw is not None:
            register("engine.power_kw", mi.engine_power_kw, user_source)

        # Add candidate values, grouped by their originating adapter/provider
        for cand in candidates:
            src = cand.source_ids[0] if cand.source_ids else "unknown"
            self._extract_fields(cand.identity, register, src)

        # Detect cross-source conflicts (single-source variance is ambiguity, not contradiction)
        for field_path, source_map in field_source_values.items():
            conflict = self._check_conflict(field_path, source_map)
            if conflict:
                contradictions.append(conflict)

        return contradictions

    def _extract_fields(
        self,
        identity: CanonicalVehicleIdentity,
        register,
        source_id: str,
    ) -> None:
        if identity.manufacturer:
            register("manufacturer", identity.manufacturer, source_id)
        if identity.model:
            register("model", identity.model, source_id)
        if identity.production.year is not None:
            register("production.year", identity.production.year, source_id)
        if identity.fuel.primary_type is not None:
            register("fuel.primary_type", identity.fuel.primary_type.value, source_id)
        if identity.engine.power_kw is not None:
            register("engine.power_kw", identity.engine.power_kw, source_id)
        if identity.engine.displacement_cc is not None:
            register("engine.displacement_cc", identity.engine.displacement_cc, source_id)
        if identity.transmission.type is not None:
            register("transmission.type", identity.transmission.type.value, source_id)
        if identity.body.type is not None:
            register("body.type", identity.body.type.value, source_id)

    def _check_conflict(self, field_path: str, source_map: dict[str, list[Any]]) -> Contradiction | None:
        # Only sources that actually asserted a value for this field count.
        sources_with_values = {src: vals for src, vals in source_map.items() if vals}

        # Rule: variance within a single source is ambiguity, not a contradiction.
        if len(sources_with_values) < 2:
            return None

        # Normalize each source's asserted values into a comparable set.
        per_source_normalized: dict[str, set[str]] = {
            src: {str(v).lower().strip() for v in vals}
            for src, vals in sources_with_values.items()
        }

        # Independent sources are compatible if they share at least one value
        # in common (e.g. an ambiguous source's offered variants include the
        # value another source confirms).
        common = set.intersection(*per_source_normalized.values())
        if common:
            return None

        # Genuine cross-source incompatibility: build one ContradictionValue
        # per distinct normalized value, attributed to the first source that
        # asserted it.
        seen_norm: dict[str, tuple[Any, str]] = {}
        for src, vals in sources_with_values.items():
            for v in vals:
                norm = str(v).lower().strip()
                if norm not in seen_norm:
                    seen_norm[norm] = (v, src)

        return Contradiction(
            contradiction_id=f"CONT-{field_path.replace('.', '_').upper()}",
            field_path=field_path,
            values=[
                ContradictionValue(value=orig, source_id=src)
                for orig, src in seen_norm.values()
            ],
            severity="high",
            resolution_action="request_user_confirmation",
        )

    @staticmethod
    def _contradiction_type_for_field(field_path: str) -> ContradictionType:
        mapping = {
            "manufacturer": ContradictionType.MANUFACTURER_CONFLICT,
            "model": ContradictionType.MODEL_CONFLICT,
            "production.year": ContradictionType.YEAR_CONFLICT,
            "fuel.primary_type": ContradictionType.FUEL_CONFLICT,
            "engine.power_kw": ContradictionType.POWER_CONFLICT,
            "engine.displacement_cc": ContradictionType.ENGINE_CONFLICT,
            "transmission.type": ContradictionType.TRANSMISSION_CONFLICT,
            "body.type": ContradictionType.BODY_TYPE_CONFLICT,
        }
        return mapping.get(field_path, ContradictionType.IDENTIFIER_CONFLICT)
