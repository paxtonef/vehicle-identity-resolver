from vir.domain.models import (
    ProviderVehicleRecord,
    CanonicalVehicleIdentity,
    Production,
    Body,
    Fuel,
    Engine,
    Transmission,
    Identifiers,
    FieldProvenance,
)
from vir.domain.enums import BodyType, FuelType, TransmissionType, Drivetrain
from vir.ports.vehicle_provider import VehicleDataProvider


# Stub in-memory database for French plates
_FRENCH_KNOWN_PLATES: dict[str, dict] = {
    "AB-123-CD": {
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
    "AC-456-EF": {
        "manufacturer": "Renault",
        "model": "Clio",
        "generation": "V",
        "production_year": 2019,
        "body_type": "hatchback",
        "door_count": 5,
        "fuel_type": "diesel",
        "engine": {"commercial_name": "1.5 Blue dCi", "displacement_cc": 1461, "cylinders": 4, "power_kw": 85},
        "transmission": {"type": "manual", "gears": 6},
        "drivetrain": "front_wheel_drive",
    },
    # Ambiguous plate: multiple motorizations
    "AM-BIG-01": {
        "ambiguous": True,
        "candidates": [
            {
                "manufacturer": "Peugeot",
                "model": "308",
                "generation": "II",
                "production_year": 2018,
                "fuel_type": "petrol",
                "engine": {"commercial_name": "PureTech 110", "power_kw": 81},
                "transmission": {"type": "manual", "gears": 5},
            },
            {
                "manufacturer": "Peugeot",
                "model": "308",
                "generation": "II",
                "production_year": 2018,
                "fuel_type": "petrol",
                "engine": {"commercial_name": "PureTech 130", "power_kw": 96},
                "transmission": {"type": "manual", "gears": 6},
            },
            {
                "manufacturer": "Peugeot",
                "model": "308",
                "generation": "II",
                "production_year": 2018,
                "fuel_type": "diesel",
                "engine": {"commercial_name": "BlueHDi 100", "power_kw": 73},
                "transmission": {"type": "manual", "gears": 5},
            },
        ]
    },
}


class FrenchRegistrationProviderAdapter(VehicleDataProvider):
    """Stub adapter for French registration provider."""

    adapter_id = "provider-fr-registration"
    supported_countries = ["FR"]
    supported_identifier_types = ["registration"]

    async def resolve_registration(self, number: str, country: str) -> list[ProviderVehicleRecord]:
        if country.upper() != "FR":
            raise ValueError(f"Country {country} not supported by this adapter")

        data = _FRENCH_KNOWN_PLATES.get(number.upper())
        if not data:
            raise ValueError(f"Plate {number} not found")

        # Handle ambiguous plates: expose every matching candidate, not just the first
        if data.get("ambiguous"):
            return [
                self._build_record(number, candidate, is_ambiguous=True)
                for candidate in data["candidates"]
            ]

        return [self._build_record(number, data, is_ambiguous=False)]

    async def decode_vin(self, vin: str) -> list[ProviderVehicleRecord]:
        raise NotImplementedError("Registration adapter does not decode VINs")

    async def retrieve_vehicle_configuration(self, **kwargs) -> list[ProviderVehicleRecord]:
        raise NotImplementedError("Registration adapter does not handle manual input")

    def _build_record(self, plate: str, data: dict, is_ambiguous: bool) -> ProviderVehicleRecord:
        fuel = self._parse_fuel(data.get("fuel_type"))
        transmission = self._parse_transmission(data.get("transmission", {}))
        body = self._parse_body(data.get("body_type"), data.get("door_count"))

        identity = CanonicalVehicleIdentity(
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            generation=data.get("generation"),
            production=Production(year=data.get("production_year")),
            body=body,
            fuel=Fuel(primary_type=fuel),
            engine=Engine(
                commercial_name=data.get("engine", {}).get("commercial_name"),
                displacement_cc=data.get("engine", {}).get("displacement_cc"),
                cylinders=data.get("engine", {}).get("cylinders"),
                power_kw=data.get("engine", {}).get("power_kw"),
            ),
            transmission=transmission,
            drivetrain=self._parse_drivetrain(data.get("drivetrain")),
            identifiers=Identifiers(registration_number=plate, registration_country="FR"),
        )

        provenance = [
            FieldProvenance(field_path="manufacturer", source_id=self.adapter_id, raw_value=data.get("manufacturer")),
            FieldProvenance(field_path="model", source_id=self.adapter_id, raw_value=data.get("model")),
            FieldProvenance(field_path="fuel.primary_type", source_id=self.adapter_id, raw_value=data.get("fuel_type")),
        ]

        return ProviderVehicleRecord(
            provider_record_id=f"FR-REG-{plate}",
            adapter_id=self.adapter_id,
            normalized_candidate=identity,
            field_provenance=provenance,
            provider_confidence=0.8 if not is_ambiguous else 0.6,
        )

    @staticmethod
    def _parse_fuel(value: str | None) -> FuelType | None:
        if not value:
            return None
        mapping = {
            "diesel": FuelType.DIESEL,
            "petrol": FuelType.PETROL,
            "electric": FuelType.ELECTRIC,
            "hybrid": FuelType.HYBRID,
        }
        return mapping.get(value.lower())

    @staticmethod
    def _parse_transmission(data: dict) -> Transmission:
        ttype = data.get("type", "") or ""
        mapping = {
            "manual": TransmissionType.MANUAL,
            "automatic": TransmissionType.AUTOMATIC,
        }
        return Transmission(
            type=mapping.get(ttype.lower()),
            gears=data.get("gears"),
        )

    @staticmethod
    def _parse_body(btype: str | None, doors: int | None) -> Body:
        mapping = {
            "suv": BodyType.SUV,
            "hatchback": BodyType.HATCHBACK,
            "sedan": BodyType.SEDAN,
        }
        return Body(
            type=mapping.get(btype.lower()) if btype else None,
            door_count=doors,
        )

    @staticmethod
    def _parse_drivetrain(value: str | None) -> Drivetrain | None:
        mapping = {
            "front_wheel_drive": Drivetrain.FRONT_WHEEL_DRIVE,
            "rear_wheel_drive": Drivetrain.REAR_WHEEL_DRIVE,
            "all_wheel_drive": Drivetrain.ALL_WHEEL_DRIVE,
        }
        return mapping.get(value) if value else None
