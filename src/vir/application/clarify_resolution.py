from __future__ import annotations

from vir.domain.models import (
    VehicleIdentityResolution,
    ClarificationAnswer,
    VehicleIdentityRequest,
    ManualIdentityInput,
    ConsentInput,
)
from vir.domain.resolution import ResolutionEngine
from vir.ports.vehicle_provider import VehicleDataProvider


class ClarifyResolutionUseCase:
    def __init__(self, providers: list[VehicleDataProvider]):
        self.providers = providers

    async def execute(
        self,
        resolution: VehicleIdentityResolution,
        answers: list[ClarificationAnswer],
    ) -> tuple[VehicleIdentityRequest, VehicleIdentityResolution]:
        # Build an enriched request from the original resolution + answers
        original_request = self._reconstruct_request(resolution)
        enriched = self._apply_answers(original_request, answers)

        # Re-run resolution with enriched data
        engine = ResolutionEngine(providers=self.providers)
        new_resolution = await engine.resolve(enriched)

        # Preserve original request_id and chain resolution
        new_resolution.request_id = resolution.request_id
        return enriched, new_resolution

    def _reconstruct_request(self, resolution: VehicleIdentityResolution) -> VehicleIdentityRequest:
        identity = resolution.vehicle_identity
        mi = ManualIdentityInput()
        if identity:
            mi.manufacturer = identity.manufacturer
            mi.model = identity.model
            mi.production_year = identity.production.year
            if identity.fuel.primary_type:
                mi.fuel_type = identity.fuel.primary_type.value
            mi.engine_power_kw = identity.engine.power_kw
            mi.engine_displacement_cc = identity.engine.displacement_cc
            if identity.transmission.type:
                mi.transmission_type = identity.transmission.type.value

        return VehicleIdentityRequest(
            request_id=resolution.request_id,
            consent=ConsentInput(external_lookup_allowed=True),
            manual_identity=mi,
            vin=identity.identifiers.vin if identity else None,
        )

    def _apply_answers(
        self,
        request: VehicleIdentityRequest,
        answers: list[ClarificationAnswer],
    ) -> VehicleIdentityRequest:
        data = request.model_dump()
        for answer in answers:
            if answer.question_id == "VIR-Q-VIN" and answer.value:
                data["vin"] = str(answer.value).upper()
            elif answer.question_id == "VIR-Q-001" and answer.value is not None:
                try:
                    data["manual_identity"]["engine_power_kw"] = float(answer.value)
                except (ValueError, TypeError):
                    pass
        return VehicleIdentityRequest(**data)
