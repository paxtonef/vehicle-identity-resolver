# Vehicle Identity Resolver — Runtime Governance Manifest (P3)

**Scope discipline (per your framing):** this manifest does not restate
rules already enforced by VIR Core — see `GOVERNANCE_RULE_EXTRACTION.md`
(P2) and `P2_5_CORE_GOVERNANCE_CLOSURE.md`. It references those guarantees
and governs only what is *permitted at runtime* — external services,
network, consent scope, data export, persistence, audit, escalation.

**Status of this document:** specification only. The manifest below is not
yet loaded or enforced by any code — that is P4 (Lightweight RGG). Writing
the RGG without this manifest first would mean inventing policy ad hoc
inside enforcement code; this document exists so P4 has something real to
enforce.

---

```yaml
runtime_governance_manifest:
  version: "0.1.0"
  runner: vehicle-identity-resolver

  # What this manifest deliberately does NOT restate — it points at the
  # guarantees the VIR Core already provides, rather than duplicating them.
  core_assurances:
    invariant_set: vir-core-invariants-v1        # see P2_5_CORE_GOVERNANCE_CLOSURE.md
    evidence_policy: vir-evidence-v1              # generalized VIR-INV-003
    already_enforced_by_core:
      - owner_identity_forbidden                  # VIR-INV-004
      - unsupported_inference_prohibited           # VIR-BR-007
      - high_severity_contradiction_blocks_resolution  # VIR-BR-006
      - provider_failure_degrades_not_fabricates   # VIR-BR-009 / VIR-INV-008
      - field_evidence_required_for_every_resolved_field  # VIR-INV-003 (generalized)
      - registration_requires_country_context      # VIR-INV-009 / VIR-IN-002
      - external_lookup_requires_consent            # VIR-IN-005 (binary, see consent section below)

  # -- The one genuinely new RGM/RGG-level rule identified in P2/P2.5 -------
  external_services:
    default: deny
    allowed:
      - provider_id: manual_input
        countries: []
        identifier_types: [manual]
        network: none
      - provider_id: provider-fr-registration
        countries: [FR]
        identifier_types: [registration]
        network: none   # currently an in-memory stub; becomes outbound HTTPS
                         # once a real provider replaces it (tracked separately
                         # as "Real Provider Adapters")
      - provider_id: vin-decoder-stub
        countries: []
        identifier_types: [vin]
        network: none   # same note as above
    enforcement_status: NOT YET ENFORCED — see "Implementation Gap" below

  outbound_network:
    current_state: none
    evidence: >
      Confirmed in P1 (RUNNER_EXECUTION_CONTRACT.md): all three adapters are
      in-memory stubs; VIR_PROVIDER_TIMEOUT_MS / VIR_PROVIDER_API_KEY exist
      in Settings but are read by zero lines of code.
    future_policy: HTTPS only, to allow-listed provider endpoints only
    egress_default: deny

  consent:
    external_lookup:
      required: true
      enforced_by: "VIR Core — VIR-IN-005 / ExternalLookupNotAuthorizedError (HTTP 403)"
      scope_today: >
        Binary only. `ConsentInput.external_lookup_allowed` is a single
        boolean covering every provider-capable call; there is no
        per-provider or per-service consent field on the request model.
    gap: >
      If a deployment ever needs "consent to query the FR registration
      provider but not the VIN decoder", this manifest and VIR-IN-005 must
      evolve together — that is new Core validation work, not something the
      RGG can add on its own by filtering after the fact.

  data_export:
    forbidden_fields: [owner_name, owner_address, owner_phone, owner_email]
    enforced_by: "VIR Core — VIR-INV-004 (scans the full resolution JSON dump)"
    raw_provider_payload:
      default_storage: false
      current_state: >
        DORMANT. `VIR_STORE_RAW_PROVIDER_PAYLOAD` exists in Settings but is
        read by no code; no persistence layer exists, so nothing is stored
        today regardless of this flag's value. Confirmed in P2/P2.5 — not
        re-verified here, referenced as-is.
      activates_with: Persistence (future work item; this flag becomes a
        real, checkable requirement only once a persistence adapter exists
        to enforce it against)

  persistence:
    current_state: none
    evidence: >
      GET /v1/vehicle-identities/{id}, POST .../clarifications, and
      GET .../handoff/diagnostic all return HTTP 501 (confirmed in P1).
    future_scope: out of P3 — this manifest will need a `persistence:`
      section with real content once that work starts, not before.

  audit:
    field_provenance: required
    enforced_by: "VIR Core — VIR-INV-003, generalized in P2.5 (covers all
      ~23 leaf identity fields, not a fixed subset)"
    trace_retention: not yet defined — no persistence layer exists to
      retain anything against

  escalation:
    high_severity_contradiction:
      action: block_confirmed_resolution
      enforced_by: "VIR Core — VIR-BR-006"
    provider_failure:
      action: degrade_resolution_not_fabricate
      enforced_by: "VIR Core — VIR-BR-009 / VIR-INV-008"
    ambiguous_with_inflated_confidence:
      action: block_and_raise
      enforced_by: "VIR Core — VIR-INV-005 / VIR-INV-007, wired in P2.5"
```

---

## Implementation Gap — `external_services` is Not Yet Enforced

This is the one section of the manifest above that describes a policy with
**no corresponding runtime check today**. Confirmed in P2:

```
Provider registered
      +
identifier supported
      +
country supported
      ↓
CALL PROVIDER
```

There is no governance decision point between "this provider matches the
request" and "call it". The manifest's `external_services.default: deny`
with an explicit allowlist is aspirational until a real check exists:

```
Provider registered
      +
technical compatibility
      ↓
Governance policy   <-- does not exist yet
      ↓
Is this provider permitted?
      ├─ NO → block
      └─ YES → execute
```

**This is deliberately not implemented in this document.** Per your
framing, this is exactly the kind of rule that belongs to P4 (Lightweight
RGG), not to a retrofit inside `ResolutionEngine`. Writing the enforcement
now, without the RGG's request/response interception point designed first,
would risk scattering governance logic back into business code — the
mistake P2.5 just finished undoing for the Core side.

## What P3 Deliberately Does Not Do

- **Does not implement `default: deny` enforcement.** That's P4.
- **Does not add per-provider consent scoping.** Flagged as a gap, not
  silently assumed away — if it's needed, it requires new Core validation
  work (a new field on `ConsentInput`), not just an RGG rule.
- **Does not invent a `persistence:` policy body.** There's nothing to
  govern yet; adding placeholder content here would misrepresent the
  runner's actual current state, the same failure mode P0.1 fixed for
  configuration.
- **Does not repeat the 15 already-`ENFORCED` Core rules from the P2 table**
  as if they were RGM rules. They're referenced once, under
  `core_assurances`, not duplicated as executable-looking YAML that nothing
  in the RGG layer would actually need to re-check.

## Verification Hook (for P1's Runner Execution Contract)

Once P4 exists, `RUNNER_EXECUTION_CONTRACT.md`'s `runtime_verification`
checklist should gain a step:

```yaml
  - step: rgm_loaded_and_valid
    command: "(P4-defined — e.g. python3 -c \"from vir.governance import load_rgm; load_rgm()\")"
    status: NOT YET DEFINABLE — no RGM loader exists until P4
```

Not added to the REC yet, since the loader doesn't exist. Noted here so P4
picks it up rather than rediscovering the gap.

## Result

✅ RGM written from the P2/P2.5 audit, not from assumption — every
`enforced_by` reference points at a real, previously-verified Core
mechanism.
✅ Exactly one genuinely new runtime-governance rule identified
(`external_services` allowlist) — not buried among restated Core invariants.
✅ Its lack of enforcement is stated plainly, not implied as "done" by the
manifest's mere existence.
⏸️ No code touched. Enforcement is P4's job, against this specification.
