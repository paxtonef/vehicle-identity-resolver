from __future__ import annotations

from abc import ABC, abstractmethod

from vir.domain.models import ProviderVehicleRecord


class VehicleDataProvider(ABC):
    """Abstract port for vehicle data providers."""

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        ...

    @property
    @abstractmethod
    def supported_countries(self) -> list[str]:
        ...

    @property
    @abstractmethod
    def supported_identifier_types(self) -> list[str]:
        ...

    @abstractmethod
    async def resolve_registration(self, number: str, country: str) -> list[ProviderVehicleRecord]:
        """Resolve a registration number to one or more candidate vehicle records."""
        ...

    @abstractmethod
    async def decode_vin(self, vin: str) -> list[ProviderVehicleRecord]:
        """Decode a VIN to one or more candidate vehicle records."""
        ...

    @abstractmethod
    async def retrieve_vehicle_configuration(self, **kwargs) -> list[ProviderVehicleRecord]:
        """Retrieve one or more candidate vehicle configurations from partial data."""
        ...
