from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from vir.domain.enums import ResolutionStatus, ResolutionState, QuestionType, ConfidenceLevel
from vir.domain.errors import (
    MissingIdentifierError,
    InvalidRegistrationFormatError,
    InvalidVINFormatError,
    UnsupportedCountryError,
    ExternalLookupNotAuthorizedError,
)
from vir.domain.models import (
    VehicleIdentityRequest,
    VehicleIdentityResolution,
    VehicleCandidate,
    CanonicalVehicleIdentity,
    ProviderVehicleRecord,
    Confidence,
    Contradiction,
    ClarificationQuestion,
    ClarificationChoice,
    SourceSummary,
    FieldEvidence,
    SourceEvidence,
    Production,
    Body,
    Fuel,
    Engine,
    Transmission,
    Identifiers,
)
from vir.domain.confidence import ConfidenceEngine
from vir.domain.contradictions import ContradictionEngine
from vir.domain.invariants import invariant_004_no_owner_identity


class ResolutionEngine:
    def __init__(self, providers: list[Any], config: dict[str, Any] | None = None):
        self.providers = providers
        self.config = config or {}
        self.confidence_engine = ConfidenceEngine()
        self.contradiction_engine = ContradictionEngine()
        self.state = ResolutionState.RECEIVED

    async def resolve(self, request: VehicleIdentityRequest) -> VehicleIdentityResolution:
        self.state = ResolutionState.VALIDATING
        self._validate_input(request)

        self.state = ResolutionState.NORMALIZED
        normalized_request = self._normalize_identifiers(request)

        self.state = ResolutionState.QUERYING_SOURCES
        records = await self._query_providers(normalized_request)

        self.state = ResolutionState.CANDIDATES_FOUND
        candidates = self._build_candidates(records, normalized_request)

        self.state = ResolutionState.RESOLVING
        contradictions = self.contradiction_engine.detect(candidates, normalized_request)
        confidence = self.confidence_engine.calculate(candidates, records, normalized_request, contradictions)
        status = self._determine_status(candidates, contradictions, confidence, records)
        questions = self._generate_clarifications(candidates, status, normalized_request)
        unresolved = self._collect_unresolved_fields(candidates)
        evidence = self._build_field_evidence(candidates, records)
        source_summary = self._build_source_summary(records)
        limitations = self._build_limitations(candidates, records, status)

        # Select primary identity
        vehicle_identity = None
        if candidates and status not in (
            ResolutionStatus.INSUFFICIENT_DATA,
            ResolutionStatus.INVALID_IDENTIFIER,
        ):
            best = max(candidates, key=lambda c: c.candidate_score)
            vehicle_identity = best.identity

        resolution = VehicleIdentityResolution(
            request_id=request.request_id,
            resolution_id=f"VIR-RES-{uuid.uuid4().hex[:12].upper()}",
            resolution_status=status,
            confidence=confidence,
            vehicle_identity=vehicle_identity,
            alternative_candidates=[c for c in candidates[1:]] if len(candidates) > 1 else [],
            unresolved_fields=unresolved,
            contradictions=contradictions,
            clarification_questions=questions,
            field_evidence=evidence,
            source_summary=source_summary,
            limitations=limitations,
        )

        # Enforce invariants
        invariant_004_no_owner_identity(resolution)

        self.state = ResolutionState(status.value) if status != ResolutionStatus.CONTRADICTORY else ResolutionState.CONTRADICTORY
        return resolution

    def _validate_input(self, request: VehicleIdentityRequest) -> None:
        # VIR-IN-001: at least one identifier
        has_id = bool(
            request.vin
            or request.registration.registration_number
            or (request.manual_identity.manufacturer and request.manual_identity.model)
        )
        if not has_id:
            raise MissingIdentifierError()

        # VIR-IN-002: country required with registration
        if request.registration.registration_number and not request.registration.country_code:
            raise InvalidRegistrationFormatError("Country code is required with registration number")

        # VIR-IN-003: VIN must be 17 characters
        if request.vin and len(request.vin.strip()) != 17:
            raise InvalidVINFormatError(f"Expected 17 characters, got {len(request.vin.strip())}")

        # VIR-IN-004: plausible production year
        if request.manual_identity.production_year:
            year = request.manual_identity.production_year
            current_year = datetime.now(timezone.utc).year
            if year < 1900 or year > current_year + 1:
                raise InvalidRegistrationFormatError(f"Production year {year} is not plausible")

        # VIR-IN-005: external lookup requires permission
        if not request.consent.external_lookup_allowed:
            # If only manual data provided, this is fine
            if request.vin or request.registration.registration_number:
                # Check if any provider would be queried
                has_provider_capable = any(
                    hasattr(p, "supported_identifier_types") and p.supported_identifier_types
                    for p in self.providers
                )
                if has_provider_capable:
                    raise ExternalLookupNotAuthorizedError()

    def _normalize_identifiers(self, request: VehicleIdentityRequest) -> VehicleIdentityRequest:
        data = request.model_dump()
        if request.registration.registration_number:
            raw = request.registration.registration_number
            normalized = raw.strip().upper().replace(" ", "-")
            # Remove multiple dashes
            while "--" in normalized:
                normalized = normalized.replace("--", "-")
            data["registration"]["registration_number"] = normalized
        if request.vin:
            data["vin"] = request.vin.strip().upper().replace(" ", "")
        return VehicleIdentityRequest(**data)

    async def _query_providers(self, request: VehicleIdentityRequest) -> list[ProviderVehicleRecord]:
        records: list[ProviderVehicleRecord] = []
        for provider in self.providers:
            try:
                provider_records: list[ProviderVehicleRecord] = []
                if request.vin and "vin" in getattr(provider, "supported_identifier_types", []):
                    provider_records = await provider.decode_vin(request.vin)
                elif (
                    request.registration.registration_number
                    and "registration" in getattr(provider, "supported_identifier_types", [])
                    and request.registration.country_code in getattr(provider, "supported_countries", [])
                ):
                    provider_records = await provider.resolve_registration(
                        request.registration.registration_number,
                        request.registration.country_code,
                    )
                elif (
                    request.manual_identity.manufacturer
                    and "manual" in getattr(provider, "supported_identifier_types", [])
                ):
                    provider_records = await provider.retrieve_vehicle_configuration(
                        manufacturer=request.manual_identity.manufacturer,
                        model=request.manual_identity.model,
                        year=request.manual_identity.production_year,
                        fuel_type=request.manual_identity.fuel_type,
                    )
                if provider_records:
                    records.extend(provider_records)
            except Exception:
                # Provider failure must not invalidate user data (VIR-BR-009)
                continue
        return records

    def _build_candidates(
        self,
        records: list[ProviderVehicleRecord],
        request: VehicleIdentityRequest,
    ) -> list[VehicleCandidate]:
        candidates: list[VehicleCandidate] = []
        seen: set[str] = set()

        for idx, record in enumerate(records):
            identity = record.normalized_candidate
            key = f"{identity.manufacturer or ''}:{identity.model or ''}:{identity.production.year or ''}:{identity.fuel.primary_type or ''}"
            if key in seen:
                continue
            seen.add(key)

            # Score based on provider confidence and field completeness
            filled = sum([
                identity.manufacturer is not None,
                identity.model is not None,
                identity.production.year is not None,
                identity.fuel.primary_type is not None,
                identity.engine.power_kw is not None,
                identity.transmission.type is not None,
            ])
            score = (filled / 6.0) * 0.5 + record.provider_confidence * 0.5

            candidates.append(VehicleCandidate(
                candidate_id=f"CAND-{idx+1:03d}",
                identity=identity,
                source_ids=[record.adapter_id],
                candidate_score=round(score, 4),
            ))

        # If manual input exists but no providers returned, create a manual candidate
        mi = request.manual_identity
        if not candidates and mi.manufacturer and mi.model:
            identity = CanonicalVehicleIdentity(
                manufacturer=mi.manufacturer,
                model=mi.model,
                production=Production(year=mi.production_year),
                fuel=Fuel(primary_type=mi.fuel_type),
                engine=Engine(
                    displacement_cc=mi.engine_displacement_cc,
                    power_kw=mi.engine_power_kw,
                ),
                transmission=Transmission(
                    type=mi.transmission_type,
                ),
            )
            candidates.append(VehicleCandidate(
                candidate_id="CAND-MANUAL",
                identity=identity,
                source_ids=["user_manual_input"],
                candidate_score=0.3,
            ))

        candidates.sort(key=lambda c: c.candidate_score, reverse=True)
        return candidates

    def _determine_status(
        self,
        candidates: list[VehicleCandidate],
        contradictions: list[Contradiction],
        confidence: Confidence,
        records: list[ProviderVehicleRecord],
    ) -> ResolutionStatus:
        if not candidates and not records:
            return ResolutionStatus.INSUFFICIENT_DATA

        if contradictions and any(c.severity == "high" for c in contradictions):
            return ResolutionStatus.CONTRADICTORY

        if len(candidates) > 1 and all(abs(candidates[0].candidate_score - c.candidate_score) < 0.15 for c in candidates[:2]):
            return ResolutionStatus.AMBIGUOUS

        if confidence.score >= 0.90 and not contradictions:
            return ResolutionStatus.RESOLVED
        if confidence.score >= 0.50:
            return ResolutionStatus.PROVISIONALLY_RESOLVED

        if not records:
            return ResolutionStatus.PROVIDER_UNAVAILABLE

        return ResolutionStatus.INSUFFICIENT_DATA

    def _generate_clarifications(
        self,
        candidates: list[VehicleCandidate],
        status: ResolutionStatus,
        request: VehicleIdentityRequest,
    ) -> list[ClarificationQuestion]:
        questions: list[ClarificationQuestion] = []

        if status == ResolutionStatus.AMBIGUOUS and candidates:
            # Ask about engine power if multiple motorizations possible
            powers = set()
            for c in candidates:
                if c.identity.engine.power_kw:
                    powers.add(c.identity.engine.power_kw)
            if len(powers) > 1:
                choices = [ClarificationChoice(label=f"{int(p)} kW", value=p) for p in sorted(powers)]
                choices.append(ClarificationChoice(label="Je ne sais pas", value=None))
                questions.append(ClarificationQuestion(
                    question_id="VIR-Q-001",
                    target_field="engine.power_kw",
                    reason="multiple_engine_variants_found",
                    question_type=QuestionType.SINGLE_CHOICE,
                    prompt="Quelle puissance figure sur le certificat d'immatriculation ?",
                    choices=choices,
                    required=False,
                ))

        if request.vin is None and status in (ResolutionStatus.PROVISIONALLY_RESOLVED, ResolutionStatus.AMBIGUOUS):
            questions.append(ClarificationQuestion(
                question_id="VIR-Q-VIN",
                target_field="identifiers.vin",
                reason="vin_required_for_exact_configuration",
                question_type=QuestionType.TEXT,
                prompt="Pouvez-vous indiquer le VIN figurant sur le certificat d'immatriculation ?",
                required=False,
            ))

        return questions

    def _collect_unresolved_fields(self, candidates: list[VehicleCandidate]) -> list[str]:
        if not candidates:
            return []
        best = candidates[0].identity
        unresolved: list[str] = []
        if not best.engine.engine_code:
            unresolved.append("engine.engine_code")
        if not best.identifiers.vin:
            unresolved.append("identifiers.vin")
        if not best.trim:
            unresolved.append("trim")
        if not best.variant:
            unresolved.append("variant")
        return unresolved

    def _build_field_evidence(
        self,
        candidates: list[VehicleCandidate],
        records: list[ProviderVehicleRecord],
    ) -> list[FieldEvidence]:
        evidence: list[FieldEvidence] = []
        if not candidates:
            return evidence

        best = candidates[0]
        identity = best.identity

        fields = [
            ("manufacturer", identity.manufacturer),
            ("model", identity.model),
            ("production.year", identity.production.year),
            ("fuel.primary_type", identity.fuel.primary_type.value if identity.fuel.primary_type else None),
            ("engine.power_kw", identity.engine.power_kw),
            ("transmission.type", identity.transmission.type.value if identity.transmission.type else None),
        ]

        for field_path, value in fields:
            if value is None:
                continue
            sources = []
            for record in records:
                # Find matching provenance
                for fp in record.field_provenance:
                    if fp.field_path == field_path:
                        sources.append(SourceEvidence(
                            source_id=record.adapter_id,
                            reported_value=fp.raw_value,
                            reliability="high" if record.provider_confidence > 0.7 else "medium",
                        ))
            if not sources:
                sources.append(SourceEvidence(
                    source_id=best.source_ids[0] if best.source_ids else "unknown",
                    reported_value=value,
                    reliability="medium",
                ))
            evidence.append(FieldEvidence(
                field_path=field_path,
                resolved_value=value,
                sources=sources,
            ))

        return evidence

    def _build_source_summary(self, records: list[ProviderVehicleRecord]) -> list[SourceSummary]:
        return [
            SourceSummary(
                source_id=r.adapter_id,
                retrieved_at=r.retrieved_at,
                reliability="high" if r.provider_confidence > 0.7 else "medium",
                fields_provided=[fp.field_path for fp in r.field_provenance],
            )
            for r in records
        ]

    def _build_limitations(
        self,
        candidates: list[VehicleCandidate],
        records: list[ProviderVehicleRecord],
        status: ResolutionStatus,
    ) -> list[str]:
        limitations: list[str] = []
        if not any(r.adapter_id.startswith("vin") for r in records):
            limitations.append("Exact factory configuration cannot be confirmed without VIN.")
        if status == ResolutionStatus.PROVISIONALLY_RESOLVED:
            limitations.append("Identity is provisional pending additional verification.")
        return limitations
