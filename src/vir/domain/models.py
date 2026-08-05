from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ConfigDict

from vir.domain.enums import (
    ResolutionStatus,
    ConfidenceLevel,
    BodyType,
    FuelType,
    TransmissionType,
    Drivetrain,
    ContradictionType,
    QuestionType,
)


# ---------------------------------------------------------------------------
# Canonical Vehicle Identity
# ---------------------------------------------------------------------------

class Engine(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    commercial_name: str | None = Field(default=None)
    engine_code: str | None = Field(default=None)
    displacement_cc: int | None = Field(default=None)
    cylinders: int | None = Field(default=None)
    power_kw: float | None = Field(default=None)
    power_hp: float | None = Field(default=None)


class Transmission(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: TransmissionType | None = Field(default=None)
    gears: int | None = Field(default=None)


class Body(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: BodyType | None = Field(default=None)
    door_count: int | None = Field(default=None)


class Fuel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    primary_type: FuelType | None = Field(default=None)


class Production(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    year: int | None = Field(default=None)
    start_date: str | None = Field(default=None)
    end_date: str | None = Field(default=None)


class Identifiers(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    registration_number: str | None = Field(default=None)
    registration_country: str | None = Field(default=None)
    vin: str | None = Field(default=None)


class CanonicalVehicleIdentity(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    manufacturer: str | None = Field(default=None)
    brand: str | None = Field(default=None)
    model: str | None = Field(default=None)
    generation: str | None = Field(default=None)
    variant: str | None = Field(default=None)
    trim: str | None = Field(default=None)
    production: Production = Field(default_factory=Production)
    body: Body = Field(default_factory=Body)
    fuel: Fuel = Field(default_factory=Fuel)
    engine: Engine = Field(default_factory=Engine)
    transmission: Transmission = Field(default_factory=Transmission)
    drivetrain: Drivetrain | None = Field(default=None)
    identifiers: Identifiers = Field(default_factory=Identifiers)


# ---------------------------------------------------------------------------
# Evidence & Provenance
# ---------------------------------------------------------------------------

class SourceEvidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_id: str
    reported_value: Any
    reliability: str  # high | medium | low


class FieldEvidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    field_path: str
    resolved_value: Any
    sources: list[SourceEvidence] = Field(default_factory=list)
    confidence: str = "medium"  # high | medium | low


# ---------------------------------------------------------------------------
# Contradictions & Clarifications
# ---------------------------------------------------------------------------

class ContradictionValue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    value: Any
    source_id: str


class Contradiction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    contradiction_id: str
    field_path: str
    values: list[ContradictionValue] = Field(default_factory=list)
    severity: str  # high | medium | low
    resolution_action: str = "request_user_confirmation"


class ClarificationChoice(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    label: str
    value: Any


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    question_id: str
    target_field: str
    reason: str
    question_type: QuestionType
    prompt: str
    choices: list[ClarificationChoice] | None = Field(default=None)
    required: bool = True


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

class VehicleCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    candidate_id: str
    identity: CanonicalVehicleIdentity
    matching_fields: list[str] = Field(default_factory=list)
    conflicting_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    candidate_score: float = 0.0


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

class Confidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    level: ConfidenceLevel = ConfidenceLevel.UNRESOLVED


# ---------------------------------------------------------------------------
# Input Contract
# ---------------------------------------------------------------------------

class RegistrationInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    registration_number: str | None = Field(default=None)
    country_code: str | None = Field(default=None)


class ManualIdentityInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    manufacturer: str | None = Field(default=None)
    model: str | None = Field(default=None)
    production_year: int | None = Field(default=None)
    fuel_type: str | None = Field(default=None)
    engine_displacement_cc: int | None = Field(default=None)
    engine_power_kw: float | None = Field(default=None)
    transmission_type: str | None = Field(default=None)


class ConsentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    external_lookup_allowed: bool


class VehicleIdentityRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str
    locale: str = Field(default="fr-FR")
    registration: RegistrationInput = Field(default_factory=RegistrationInput)
    vin: str | None = Field(default=None)
    manual_identity: ManualIdentityInput = Field(default_factory=ManualIdentityInput)
    supporting_documents: list[Any] = Field(default_factory=list)
    consent: ConsentInput


# ---------------------------------------------------------------------------
# Provider Contract
# ---------------------------------------------------------------------------

class FieldProvenance(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    field_path: str
    source_id: str
    raw_value: Any
    transformed: bool = False


class ProviderVehicleRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    provider_record_id: str
    adapter_id: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload_reference: str | None = Field(default=None)
    normalized_candidate: CanonicalVehicleIdentity
    field_provenance: list[FieldProvenance] = Field(default_factory=list)
    provider_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Output Contract
# ---------------------------------------------------------------------------

class SourceSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_id: str
    retrieved_at: datetime
    reliability: str
    fields_provided: list[str] = Field(default_factory=list)


class VehicleIdentityResolution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str
    resolution_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolution_status: ResolutionStatus
    confidence: Confidence = Field(default_factory=Confidence)
    vehicle_identity: CanonicalVehicleIdentity | None = Field(default=None)
    alternative_candidates: list[VehicleCandidate] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    source_summary: list[SourceSummary] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Handoff Contract
# ---------------------------------------------------------------------------

class DiagnosticIdentityContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resolution_id: str
    identity_status: ResolutionStatus
    vehicle: dict[str, Any]
    diagnostic_constraints: dict[str, Any]


# ---------------------------------------------------------------------------
# Clarification Answer
# ---------------------------------------------------------------------------

class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    question_id: str
    value: Any


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    answers: list[ClarificationAnswer] = Field(default_factory=list)
