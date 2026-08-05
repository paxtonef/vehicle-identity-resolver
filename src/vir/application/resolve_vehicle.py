from __future__ import annotations

from vir.domain.models import VehicleIdentityRequest, VehicleIdentityResolution
from vir.domain.resolution import ResolutionEngine
from vir.ports.vehicle_provider import VehicleDataProvider


class ResolveVehicleUseCase:
    def __init__(self, providers: list[VehicleDataProvider]):
        self.engine = ResolutionEngine(providers=providers)

    async def execute(self, request: VehicleIdentityRequest) -> VehicleIdentityResolution:
        return await self.engine.resolve(request)
