from __future__ import annotations

from vir.domain.models import VehicleIdentityResolution, DiagnosticIdentityContext


class HandoffBuilder:
    @staticmethod
    def build_diagnostic_context(resolution: VehicleIdentityResolution) -> DiagnosticIdentityContext:
        identity = resolution.vehicle_identity
        vehicle: dict = {}
        if identity:
            vehicle = {
                "manufacturer": identity.manufacturer,
                "model": identity.model,
                "production_year": identity.production.year,
                "fuel_type": identity.fuel.primary_type.value if identity.fuel.primary_type else None,
                "engine_name": identity.engine.commercial_name,
                "power_kw": identity.engine.power_kw,
            }

        return DiagnosticIdentityContext(
            resolution_id=resolution.resolution_id,
            identity_status=resolution.resolution_status,
            vehicle=vehicle,
            diagnostic_constraints={
                "exact_engine_code_known": identity.engine.engine_code is not None if identity else False,
                "exact_factory_configuration_known": identity is not None and identity.identifiers.vin is not None,
                "confidence_score": resolution.confidence.score,
                "confidence_level": resolution.confidence.level.value,
                "unresolved_fields": resolution.unresolved_fields,
                "has_contradictions": len(resolution.contradictions) > 0,
            },
        )
