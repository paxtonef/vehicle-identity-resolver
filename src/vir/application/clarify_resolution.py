from __future__ import annotations

from vir.domain.models import (
    VehicleIdentityResolution,
    ClarificationAnswer,
    VehicleIdentityRequest,
)
from vir.domain.resolution import ResolutionEngine
from vir.ports.vehicle_provider import VehicleDataProvider


class ClarifyResolutionUseCase:
    """Applies clarification answers on top of the ORIGINAL request that
    produced a resolution, then re-runs resolution.

    Invariant (P6.1, yours): "Clarification MUST preserve all previously
    accepted identification inputs unless the user explicitly corrects
    them." This applies to VIN, registration number, country, manufacturer/
    model already confirmed — not just the field a clarification question
    targets.

    Fixed in P6.1: this previously reconstructed an approximate request
    from the *resolved identity* (`_reconstruct_request`), which silently
    dropped anything not carried on `CanonicalVehicleIdentity` — most
    notably the registration number, since `identifiers.registration_number`
    was never copied. Now it starts from the actual original request
    (persisted via PersistencePort, see P6/P6.1), which by construction
    preserves everything the user originally submitted.
    """

    def __init__(self, providers: list[VehicleDataProvider]):
        self.providers = providers

    async def execute(
        self,
        original_request: VehicleIdentityRequest,
        resolution: VehicleIdentityResolution,
        answers: list[ClarificationAnswer],
    ) -> tuple[VehicleIdentityRequest, VehicleIdentityResolution]:
        enriched = self._apply_answers(original_request, resolution, answers)

        # Re-run resolution with the enriched, still-complete request
        engine = ResolutionEngine(providers=self.providers)
        new_resolution = await engine.resolve(enriched)

        # Preserve original request_id and chain resolution
        new_resolution.request_id = resolution.request_id
        return enriched, new_resolution

    def _apply_answers(
        self,
        request: VehicleIdentityRequest,
        resolution: VehicleIdentityResolution,
        answers: list[ClarificationAnswer],
    ) -> VehicleIdentityRequest:
        """Apply each answer to the field it targets, resolved via the
        *originating question's* `target_field` — not a hardcoded
        question_id string match. This generalizes to any clarification
        question the resolution engine generates, rather than silently
        ignoring an answer to a question this method doesn't recognize by
        id (the previous implementation's failure mode).

        The complete, current set of target_field values the resolution
        engine can generate is exactly {"identifiers.vin",
        "engine.power_kw"} — see ResolutionEngine._generate_clarifications.
        tests/test_clarify_resolution.py asserts this set stays in sync
        with what's handled here (a mapping-completeness contract test,
        per your framing), so adding a new clarification question without
        also teaching this method how to apply its answer fails the test
        suite instead of silently dropping the answer.
        """
        question_target_field = {
            q.question_id: q.target_field for q in resolution.clarification_questions
        }

        data = request.model_dump()
        for answer in answers:
            target_field = question_target_field.get(answer.question_id)

            if target_field == "identifiers.vin" and answer.value:
                data["vin"] = str(answer.value).upper()
            elif target_field == "engine.power_kw" and answer.value is not None:
                try:
                    data["manual_identity"]["engine_power_kw"] = float(answer.value)
                except (ValueError, TypeError):
                    pass
            # An answer to an unrecognized target_field is intentionally
            # ignored here rather than raising — a clarification answer is
            # always optional (see USER_INTERACTION_CONTRACT.md section 4)
            # and a malformed/unknown answer must not block re-resolution.
            # The mapping-completeness test ensures "unrecognized" can only
            # mean "genuinely not a target_field this engine can produce",
            # not "we forgot to handle a real one".

        return VehicleIdentityRequest(**data)
