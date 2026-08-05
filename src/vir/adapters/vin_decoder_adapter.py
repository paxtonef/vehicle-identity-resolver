from vir.domain.models import (
    ProviderVehicleRecord,
    CanonicalVehicleIdentity,
    Identifiers,
    FieldProvenance,
    Production,
    Body,
    Fuel,
    Engine,
    Transmission,
)
from vir.domain.enums import BodyType, FuelType, TransmissionType, Drivetrain
from vir.ports.vehicle_provider import VehicleDataProvider


# WMI to manufacturer mapping (used for the sparse/partial decode fallback)
_WMI_MANUFACTURERS: dict[str, str] = {
    "VF1": "Renault",
    "VF3": "Peugeot",
    "VF7": "Citroen",
    "WBA": "BMW",
    "WDB": "Mercedes-Benz",
    "WVW": "Volkswagen",
}

# Known VINs with a full, authoritative factory decode (exact-match fixtures).
# A real VIN decoder provider would resolve these fields from the VDS/VIS
# segments plus a manufacturer catalog; this stub hardcodes a handful of
# fully-specified vehicles to represent that "exact VIN resolution" case.
_KNOWN_VIN_FULL_DECODE: dict[str, dict] = {
    "VF3XXXXXXXXXXXXXX": {
        "manufacturer": "Peugeot",
        "model": "3008",
        "generation": "II",
        "production_year": 2020,
        "body_type": "suv",
        "door_count": 5,
        "fuel_type": "diesel",
        "engine": {"commercial_name": "BlueHDi 130", "displacement_cc": 1499, "cylinders": 4, "power_kw": 96},
        "transmission": {"type": "automatic", "gears": 8},
        "drivetrain": "front_wheel_drive",
    },
}

_FUEL_MAP = {
    "diesel": FuelType.DIESEL,
    "petrol": FuelType.PETROL,
    "electric": FuelType.ELECTRIC,
    "hybrid": FuelType.HYBRID,
}
_TRANSMISSION_MAP = {
    "manual": TransmissionType.MANUAL,
    "automatic": TransmissionType.AUTOMATIC,
}
_BODY_MAP = {
    "suv": BodyType.SUV,
    "hatchback": BodyType.HATCHBACK,
    "sedan": BodyType.SEDAN,
}
_DRIVETRAIN_MAP = {
    "front_wheel_drive": Drivetrain.FRONT_WHEEL_DRIVE,
    "rear_wheel_drive": Drivetrain.REAR_WHEEL_DRIVE,
    "all_wheel_drive": Drivetrain.ALL_WHEEL_DRIVE,
}


class VINDecoderAdapter(VehicleDataProvider):
    """Stub VIN decoder adapter.

    Behaviour is intentionally split in two:
      - a VIN present in `_KNOWN_VIN_FULL_DECODE` represents an exact,
        authoritative factory decode: every discriminating field is
        populated and provider_confidence is high.
      - any other syntactically valid VIN falls back to a sparse decode
        (manufacturer only, from the WMI) with a low provider_confidence,
        so it can never be reported as `RESOLVED` on its own — only
        `PROVISIONALLY_RESOLVED` or `INSUFFICIENT_DATA`, per VIR-BR-001
        (never declare a specific engine variant without evidence).
    """

    adapter_id = "vin-decoder-stub"
    supported_countries = []
    supported_identifier_types = ["vin"]

    async def resolve_registration(self, number: str, country: str) -> list[ProviderVehicleRecord]:
        raise NotImplementedError("VIN adapter does not resolve registrations")

    async def decode_vin(self, vin: str) -> list[ProviderVehicleRecord]:
        vin = vin.strip().upper()

        if len(vin) != 17:
            raise ValueError(f"VIN must be 17 characters, got {len(vin)}")

        invalid_chars = set("IOQ")
        for i, char in enumerate(vin):
            if char in invalid_chars:
                raise ValueError(f"Invalid character '{char}' at position {i+1}")

        known = _KNOWN_VIN_FULL_DECODE.get(vin)
        if known:
            return [self._build_full_record(vin, known)]

        return [self._build_partial_record(vin)]

    async def retrieve_vehicle_configuration(self, **kwargs) -> list[ProviderVehicleRecord]:
        raise NotImplementedError("VIN adapter does not handle manual input")

    def _build_partial_record(self, vin: str) -> ProviderVehicleRecord:
        wmi = vin[0:3]
        manufacturer = _WMI_MANUFACTURERS.get(wmi, "Unknown")

        identity = CanonicalVehicleIdentity(
            manufacturer=manufacturer,
            identifiers=Identifiers(vin=vin),
        )

        provenance = [
            FieldProvenance(field_path="identifiers.vin", source_id=self.adapter_id, raw_value=vin),
            FieldProvenance(field_path="manufacturer", source_id=self.adapter_id, raw_value=manufacturer),
        ]

        return ProviderVehicleRecord(
            provider_record_id=f"VIN-{vin[:8]}",
            adapter_id=self.adapter_id,
            normalized_candidate=identity,
            field_provenance=provenance,
            provider_confidence=0.6,
        )

    def _build_full_record(self, vin: str, data: dict) -> ProviderVehicleRecord:
        engine_data = data.get("engine", {})
        transmission_data = data.get("transmission", {})

        identity = CanonicalVehicleIdentity(
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            generation=data.get("generation"),
            production=Production(year=data.get("production_year")),
            body=Body(
                type=_BODY_MAP.get((data.get("body_type") or "").lower()),
                door_count=data.get("door_count"),
            ),
            fuel=Fuel(primary_type=_FUEL_MAP.get((data.get("fuel_type") or "").lower())),
            engine=Engine(
                commercial_name=engine_data.get("commercial_name"),
                displacement_cc=engine_data.get("displacement_cc"),
                cylinders=engine_data.get("cylinders"),
                power_kw=engine_data.get("power_kw"),
            ),
            transmission=Transmission(
                type=_TRANSMISSION_MAP.get((transmission_data.get("type") or "").lower()),
                gears=transmission_data.get("gears"),
            ),
            drivetrain=_DRIVETRAIN_MAP.get(data.get("drivetrain")),
            identifiers=Identifiers(vin=vin),
        )

        provenance = [
            FieldProvenance(field_path="identifiers.vin", source_id=self.adapter_id, raw_value=vin),
            FieldProvenance(field_path="manufacturer", source_id=self.adapter_id, raw_value=data.get("manufacturer")),
            FieldProvenance(field_path="model", source_id=self.adapter_id, raw_value=data.get("model")),
            FieldProvenance(field_path="fuel.primary_type", source_id=self.adapter_id, raw_value=data.get("fuel_type")),
            FieldProvenance(field_path="engine.power_kw", source_id=self.adapter_id, raw_value=engine_data.get("power_kw")),
            FieldProvenance(field_path="transmission.type", source_id=self.adapter_id, raw_value=transmission_data.get("type")),
        ]

        return ProviderVehicleRecord(
            provider_record_id=f"VIN-{vin[:8]}",
            adapter_id=self.adapter_id,
            normalized_candidate=identity,
            field_provenance=provenance,
            provider_confidence=0.97,
        )
