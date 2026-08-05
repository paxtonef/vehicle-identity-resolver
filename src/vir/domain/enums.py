from enum import Enum


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    PROVISIONALLY_RESOLVED = "provisionally_resolved"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_DATA = "insufficient_data"
    CONTRADICTORY = "contradictory"
    UNSUPPORTED_COUNTRY = "unsupported_country"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_IDENTIFIER = "invalid_identifier"


class ConfidenceLevel(str, Enum):
    CONFIRMED = "confirmed"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRESOLVED = "unresolved"


class BodyType(str, Enum):
    HATCHBACK = "hatchback"
    SEDAN = "sedan"
    ESTATE = "estate"
    SUV = "suv"
    CROSSOVER = "crossover"
    COUPE = "coupe"
    CONVERTIBLE = "convertible"
    VAN = "van"
    PICKUP = "pickup"
    OTHER = "other"


class FuelType(str, Enum):
    PETROL = "petrol"
    DIESEL = "diesel"
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    PLUG_IN_HYBRID = "plug_in_hybrid"
    LPG = "lpg"
    CNG = "cng"
    HYDROGEN = "hydrogen"
    OTHER = "other"


class TransmissionType(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    AUTOMATED_MANUAL = "automated_manual"
    CVT = "cvt"
    DIRECT_DRIVE = "direct_drive"
    UNKNOWN = "unknown"


class Drivetrain(str, Enum):
    FRONT_WHEEL_DRIVE = "front_wheel_drive"
    REAR_WHEEL_DRIVE = "rear_wheel_drive"
    ALL_WHEEL_DRIVE = "all_wheel_drive"
    FOUR_WHEEL_DRIVE = "four_wheel_drive"
    UNKNOWN = "unknown"


class ContradictionType(str, Enum):
    IDENTIFIER_CONFLICT = "identifier_conflict"
    MANUFACTURER_CONFLICT = "manufacturer_conflict"
    MODEL_CONFLICT = "model_conflict"
    YEAR_CONFLICT = "year_conflict"
    ENGINE_CONFLICT = "engine_conflict"
    FUEL_CONFLICT = "fuel_conflict"
    TRANSMISSION_CONFLICT = "transmission_conflict"
    BODY_TYPE_CONFLICT = "body_type_conflict"
    POWER_CONFLICT = "power_conflict"


class QuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT = "text"
    BOOLEAN = "boolean"


class InputMode(str, Enum):
    REGISTRATION_NUMBER = "registration_number"
    VIN = "vin"
    REGISTRATION_DOCUMENT = "registration_document"
    MANUAL_VEHICLE_DESCRIPTION = "manual_vehicle_description"
    EXTERNAL_VEHICLE_RECORD = "external_vehicle_record"


class ResolutionState(str, Enum):
    RECEIVED = "received"
    VALIDATING = "validating"
    NORMALIZED = "normalized"
    QUERYING_SOURCES = "querying_sources"
    CANDIDATES_FOUND = "candidates_found"
    CLARIFICATION_REQUIRED = "clarification_required"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    PROVISIONALLY_RESOLVED = "provisionally_resolved"
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
    INSUFFICIENT_DATA = "insufficient_data"
    UNSUPPORTED_COUNTRY = "unsupported_country"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_IDENTIFIER = "invalid_identifier"
    FAILED = "failed"
