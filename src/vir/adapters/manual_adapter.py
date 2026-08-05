from vir.domain.models import (
    ProviderVehicleRecord,
    CanonicalVehicleIdentity,
    Production,
    Fuel,
    Engine,
    Transmission,
    FieldProvenance,
)
from vir.domain.enums import FuelType, TransmissionType
from vir.ports.vehicle_provider import VehicleDataProvider


class ManualAdapter(VehicleDataProvider):
    """Adapter that creates a provider record from manual user input."""

    adapter_id = "manual_input"
    supported_countries = []
    supported_identifier_types = ["manual"]

    async def resolve_registration(self, number: str, country: str) -> list[ProviderVehicleRecord]:
        raise NotImplementedError("Manual adapter does not resolve registrations")

    async def decode_vin(self, vin: str) -> list[ProviderVehicleRecord]:
        raise NotImplementedError("Manual adapter does not decode VINs")

    async def retrieve_vehicle_configuration(self, **kwargs) -> list[ProviderVehicleRecord]:
        manufacturer = kwargs.get("manufacturer", "") or ""
        model = kwargs.get("model", "") or ""
        year = kwargs.get("year")
        fuel_type_str = kwargs.get("fuel_type", "") or ""
        displacement = kwargs.get("engine_displacement_cc")
        power = kwargs.get("engine_power_kw")
        transmission_str = kwargs.get("transmission_type", "") or ""

        # Normalize fuel type
        fuel = None
        if fuel_type_str:
            ft = fuel_type_str.lower()
            if ft in ("diesel", "diésel"):
                fuel = FuelType.DIESEL
            elif ft in ("petrol", "essence", "gasoline"):
                fuel = FuelType.PETROL
            elif ft == "electric":
                fuel = FuelType.ELECTRIC
            elif ft == "hybrid":
                fuel = FuelType.HYBRID

        # Normalize transmission
        transmission = None
        if transmission_str:
            tt = transmission_str.lower()
            if tt in ("manual", "manuelle", "man"):
                transmission = TransmissionType.MANUAL
            elif tt in ("automatic", "automatique", "auto"):
                transmission = TransmissionType.AUTOMATIC

        identity = CanonicalVehicleIdentity(
            manufacturer=manufacturer,
            model=model,
            production=Production(year=year),
            fuel=Fuel(primary_type=fuel),
            engine=Engine(
                displacement_cc=displacement,
                power_kw=power,
            ),
            transmission=Transmission(type=transmission),
        )

        provenance = []
        if manufacturer:
            provenance.append(FieldProvenance(field_path="manufacturer", source_id=self.adapter_id, raw_value=manufacturer))
        if model:
            provenance.append(FieldProvenance(field_path="model", source_id=self.adapter_id, raw_value=model))

        return [ProviderVehicleRecord(
            provider_record_id=f"MANUAL-{manufacturer[:3].upper()}-{model[:3].upper()}",
            adapter_id=self.adapter_id,
            normalized_candidate=identity,
            field_provenance=provenance,
            provider_confidence=0.3,
        )]
