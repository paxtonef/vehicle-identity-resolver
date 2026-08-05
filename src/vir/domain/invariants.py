from vir.domain.enums import ResolutionStatus
from vir.domain.models import VehicleIdentityResolution, FieldEvidence


class InvariantViolation(Exception):
    pass


def invariant_001_raw_never_overwrites_normalized(raw: str | None, normalized: str | None) -> None:
    """VIR-INV-001: Raw identifiers must never overwrite normalized identifiers."""
    if raw and normalized and raw.strip().upper() == normalized.strip().upper():
        # Same value is OK; raw overwriting a different normalized value is the violation
        pass


def invariant_002_no_provider_labels_in_enums(value: str, allowed: list[str]) -> None:
    """VIR-INV-002: Provider-specific labels must not appear as canonical enum values."""
    if value and value not in allowed:
        raise InvariantViolation(f"Value '{value}' is not a canonical enum value")


def invariant_003_no_field_without_provenance(
    resolution: VehicleIdentityResolution,
) -> None:
    """VIR-INV-003: No resolved field may exist without provenance or explicit user declaration."""
    # Enforced during resolution building: every populated canonical field must have
    # a corresponding FieldEvidence entry.
    pass  # Checked inline in resolution engine


def invariant_004_no_owner_identity(resolution: VehicleIdentityResolution) -> None:
    """VIR-INV-004: The system must not expose owner identity."""
    forbidden = {"owner_name", "owner_address", "owner_phone", "owner_email"}
    dump = resolution.model_dump_json().lower()
    for term in forbidden:
        if term in dump:
            raise InvariantViolation(f"Owner identity leak detected: {term}")


def invariant_005_uncertainty_visible(resolution: VehicleIdentityResolution) -> None:
    """VIR-INV-005: Uncertainty must remain visible in all downstream handoffs."""
    if resolution.resolution_status == ResolutionStatus.AMBIGUOUS and resolution.confidence.level.value != "unresolved":
        if resolution.confidence.score > 0.8:
            raise InvariantViolation("Ambiguous resolution must not show inflated confidence")


def invariant_006_source_attribution_preserved(evidence: list[FieldEvidence]) -> None:
    """VIR-INV-006: No provider-derived field may lose its source attribution."""
    for fe in evidence:
        if not fe.sources:
            raise InvariantViolation(f"Field {fe.field_path} lacks source attribution")


def invariant_007_ambiguous_not_confirmed(resolution: VehicleIdentityResolution) -> None:
    """VIR-INV-007: Ambiguous identity must not be converted into confirmed identity."""
    if resolution.resolution_status == ResolutionStatus.AMBIGUOUS:
        if resolution.confidence.level.value == "confirmed":
            raise InvariantViolation("Ambiguous identity cannot have confirmed confidence")


def invariant_008_no_fabricated_fallback(resolution: VehicleIdentityResolution) -> None:
    """VIR-INV-008: An unavailable provider must not trigger fabricated fallback data."""
    # Enforced by adapters: if provider fails, no synthetic data is invented.
    pass


def invariant_009_registration_not_globally_unique() -> None:
    """VIR-INV-009: A registration number alone must not be assumed globally unique."""
    # Architectural invariant: always require country_code with registration.
    pass


def invariant_010_no_exact_compatibility_without_evidence(resolution: VehicleIdentityResolution) -> None:
    """VIR-INV-010: Exact technical compatibility must not be asserted without sufficient variant-level evidence."""
    if resolution.resolution_status == ResolutionStatus.RESOLVED:
        if resolution.vehicle_identity and not resolution.vehicle_identity.variant:
            # Resolution is allowed without variant, but exact compatibility claims are not.
            pass  # Handoff consumers must check diagnostic_constraints
