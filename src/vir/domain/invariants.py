from vir.domain.enums import ResolutionStatus
from vir.domain.models import VehicleIdentityResolution, FieldEvidence


class InvariantViolation(Exception):
    pass


def invariant_001_raw_never_overwrites_normalized(raw: str | None, normalized: str | None) -> None:
    """VIR-INV-001: Raw identifiers must never overwrite normalized identifiers.

    Violated when a raw value was supplied but normalization did not produce
    a usable value to use in its place: any caller that then writes into a
    canonical field under those conditions ends up falling back to the raw
    value, which is exactly a raw identifier overwriting a normalized one.

    Fixed 2026 (P2.5): the previous implementation never raised, even in the
    violation case it described in its own docstring.
    """
    if raw and raw.strip() and not (normalized and normalized.strip()):
        raise InvariantViolation(
            f"Raw identifier {raw!r} has no normalized counterpart; using it "
            f"directly would let a raw value overwrite a normalized identifier."
        )


def invariant_002_no_provider_labels_in_enums(value: str, allowed: list[str]) -> None:
    """VIR-INV-002: Provider-specific labels must not appear as canonical enum values."""
    if value and value not in allowed:
        raise InvariantViolation(f"Value '{value}' is not a canonical enum value")


def _populated_identity_field_paths(identity) -> dict[str, object]:
    """Return {dotted_field_path: value} for every non-None leaf field on a
    CanonicalVehicleIdentity.

    Shared by invariant_003 (which asserts every one of these paths has
    evidence) and ResolutionEngine._build_field_evidence (which builds that
    evidence) — a single source of truth for "what counts as a resolved
    field", so the two can never drift apart again (see P2.5 closure notes:
    the previous implementation covered only 6 of ~23 leaf fields).
    """
    paths: dict[str, object] = {}

    def _val(v):
        return v.value if hasattr(v, "value") else v

    if identity.manufacturer is not None:
        paths["manufacturer"] = identity.manufacturer
    if identity.brand is not None:
        paths["brand"] = identity.brand
    if identity.model is not None:
        paths["model"] = identity.model
    if identity.generation is not None:
        paths["generation"] = identity.generation
    if identity.variant is not None:
        paths["variant"] = identity.variant
    if identity.trim is not None:
        paths["trim"] = identity.trim
    if identity.production.year is not None:
        paths["production.year"] = identity.production.year
    if identity.production.start_date is not None:
        paths["production.start_date"] = identity.production.start_date
    if identity.production.end_date is not None:
        paths["production.end_date"] = identity.production.end_date
    if identity.body.type is not None:
        paths["body.type"] = _val(identity.body.type)
    if identity.body.door_count is not None:
        paths["body.door_count"] = identity.body.door_count
    if identity.fuel.primary_type is not None:
        paths["fuel.primary_type"] = _val(identity.fuel.primary_type)
    if identity.engine.commercial_name is not None:
        paths["engine.commercial_name"] = identity.engine.commercial_name
    if identity.engine.engine_code is not None:
        paths["engine.engine_code"] = identity.engine.engine_code
    if identity.engine.displacement_cc is not None:
        paths["engine.displacement_cc"] = identity.engine.displacement_cc
    if identity.engine.cylinders is not None:
        paths["engine.cylinders"] = identity.engine.cylinders
    if identity.engine.power_kw is not None:
        paths["engine.power_kw"] = identity.engine.power_kw
    if identity.engine.power_hp is not None:
        paths["engine.power_hp"] = identity.engine.power_hp
    if identity.transmission.type is not None:
        paths["transmission.type"] = _val(identity.transmission.type)
    if identity.transmission.gears is not None:
        paths["transmission.gears"] = identity.transmission.gears
    if identity.drivetrain is not None:
        paths["drivetrain"] = _val(identity.drivetrain)
    if identity.identifiers.registration_number is not None:
        paths["identifiers.registration_number"] = identity.identifiers.registration_number
    if identity.identifiers.registration_country is not None:
        paths["identifiers.registration_country"] = identity.identifiers.registration_country
    if identity.identifiers.vin is not None:
        paths["identifiers.vin"] = identity.identifiers.vin

    return paths


def invariant_003_no_field_without_provenance(
    resolution: VehicleIdentityResolution,
) -> None:
    """VIR-INV-003 (canonical, generalized in P2.5): No asserted resolved
    field may exist without attributable evidence.

    Elevated during P2.5 from a docstring-only, unenforced invariant covering
    a fixed subset of 6 fields to a real check covering every populated
    field on the resolved identity, via the same field enumeration
    (`_populated_identity_field_paths`) used to build that evidence in the
    first place — so the two cannot silently drift apart again.
    """
    identity = resolution.vehicle_identity
    if identity is None:
        return

    evidenced_paths = {fe.field_path for fe in resolution.field_evidence}
    populated_paths = set(_populated_identity_field_paths(identity).keys())
    missing = populated_paths - evidenced_paths
    if missing:
        raise InvariantViolation(
            f"Resolved field(s) asserted without attributable evidence: {sorted(missing)}"
        )


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
