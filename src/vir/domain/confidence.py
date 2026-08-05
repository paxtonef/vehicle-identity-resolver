from __future__ import annotations

from vir.domain.enums import ConfidenceLevel
from vir.domain.models import (
    VehicleCandidate,
    ProviderVehicleRecord,
    VehicleIdentityRequest,
    Contradiction,
    Confidence,
)


class ConfidenceEngine:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {
            "identifier_quality": 0.25,
            "source_reliability": 0.25,
            "field_consistency": 0.25,
            "configuration_specificity": 0.15,
            "user_confirmation": 0.10,
        }

    def calculate(
        self,
        candidates: list[VehicleCandidate],
        records: list[ProviderVehicleRecord],
        request: VehicleIdentityRequest,
        contradictions: list[Contradiction],
    ) -> Confidence:
        identifier_quality = self._score_identifier_quality(request)
        source_reliability = self._score_source_reliability(records)
        field_consistency = self._score_field_consistency(candidates, contradictions)
        configuration_specificity = self._score_configuration_specificity(candidates)

        # user_confirmation is only applicable when manual identity data was supplied.
        # When not applicable, it is excluded from both the numerator and the
        # weight normalization denominator, rather than scored as 0.
        user_confirmation_applicable = self._is_user_confirmation_applicable(request)
        user_confirmation = self._score_user_confirmation(request) if user_confirmation_applicable else None

        components: list[tuple[float, float]] = [
            (identifier_quality, self.weights["identifier_quality"]),
            (source_reliability, self.weights["source_reliability"]),
            (field_consistency, self.weights["field_consistency"]),
            (configuration_specificity, self.weights["configuration_specificity"]),
        ]
        if user_confirmation is not None:
            components.append((user_confirmation, self.weights["user_confirmation"]))

        active_weight_sum = sum(weight for _, weight in components)
        if active_weight_sum <= 0:
            score = 0.0
        else:
            weighted_sum = sum(value * weight for value, weight in components)
            score = weighted_sum / active_weight_sum

        score = round(min(1.0, max(0.0, score)), 4)

        return Confidence(score=score, level=self._level_from_score(score))

    @staticmethod
    def _is_user_confirmation_applicable(request: VehicleIdentityRequest) -> bool:
        mi = request.manual_identity
        return bool(mi.manufacturer or mi.model or mi.production_year or mi.fuel_type)

    @staticmethod
    def _score_identifier_quality(request: VehicleIdentityRequest) -> float:
        if request.vin:
            return 1.0
        if request.registration.registration_number and request.registration.country_code:
            return 0.7
        if request.manual_identity.manufacturer and request.manual_identity.model:
            return 0.4
        return 0.2

    @staticmethod
    def _score_source_reliability(records: list[ProviderVehicleRecord]) -> float:
        if not records:
            return 0.0
        scores = [r.provider_confidence for r in records]
        return sum(scores) / len(scores)

    @staticmethod
    def _score_field_consistency(
        candidates: list[VehicleCandidate],
        contradictions: list[Contradiction],
    ) -> float:
        if not candidates:
            return 0.0
        if contradictions:
            # Penalize by severity
            high_count = sum(1 for c in contradictions if c.severity == "high")
            return max(0.0, 1.0 - (high_count * 0.3))
        return 0.9

    @staticmethod
    def _score_configuration_specificity(candidates: list[VehicleCandidate]) -> float:
        if not candidates:
            return 0.0
        best = max(candidates, key=lambda c: c.candidate_score)
        identity = best.identity
        filled = sum([
            identity.manufacturer is not None,
            identity.model is not None,
            identity.production.year is not None,
            identity.fuel.primary_type is not None,
            identity.engine.power_kw is not None,
            identity.transmission.type is not None,
            identity.body.type is not None,
        ])
        return min(1.0, filled / 7.0)

    @staticmethod
    def _score_user_confirmation(request: VehicleIdentityRequest) -> float:
        # User confirmation score is applied post-clarification
        # For initial resolution, check if manual input is detailed
        mi = request.manual_identity
        if mi.manufacturer and mi.model and mi.production_year and mi.fuel_type:
            return 0.5
        return 0.0

    @staticmethod
    def _level_from_score(score: float) -> ConfidenceLevel:
        if score >= 0.90:
            return ConfidenceLevel.CONFIRMED
        if score >= 0.75:
            return ConfidenceLevel.HIGH
        if score >= 0.50:
            return ConfidenceLevel.MEDIUM
        if score >= 0.25:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.UNRESOLVED
