# Vehicle Identity Resolver — P2.5 Core Governance Closure

**Rationale (yours):** P2 revealed defects that belong to the VIR Core itself
— they must not be papered over by a future RGG. `DOMAIN/BUSINESS INVARIANTS
→ enforced by VIR Core`, then `RUNTIME/ACCESS/EXECUTION POLICIES → enforced
by RGG`. This closure fixes the Core side before P3 writes the RGM, so the
RGM references real guarantees instead of repeating unenforced invariants.

All three items — A, B, C — are implemented, wired, tested, and verified
end-to-end. **43/43 tests pass** (26 pre-existing + 17 new). No regressions.

---

## A — VIR-INV-001 (fixed, tested, wired)

**Before:** the function's body was a no-op — it didn't raise even in the
violation case its own docstring described.

**Fixed:** `invariant_001_raw_never_overwrites_normalized(raw, normalized)`
now raises `InvariantViolation` when a raw value was supplied but
normalization produced nothing usable — the scenario where a caller would
otherwise fall back to the raw value in a canonical field.

**Wired:** called in `ResolutionEngine._normalize_identifiers()`, immediately
after computing the normalized registration number and VIN, before either is
written into the request.

**Tested:** 4 unit tests (`tests/test_invariants.py`) — raises on
no-normalized-value, raises on blank-normalized, does not raise on a normal
successful normalization, does not raise when no raw value was given.

## B — VIR-INV-005 / 006 / 007 (wired, tested end-to-end)

**Before:** all three had correct logic but were never called anywhere.

**Wired:** all three (plus the pre-existing `invariant_004`) are now called
in `ResolutionEngine.resolve()`, right after the `VehicleIdentityResolution`
object is built:
```python
invariant_003_no_field_without_provenance(resolution)
invariant_004_no_owner_identity(resolution)
invariant_005_uncertainty_visible(resolution)
invariant_006_source_attribution_preserved(resolution.field_evidence)
invariant_007_ambiguous_not_confirmed(resolution)
```

**Tested at two levels:**
- Unit tests (`tests/test_invariants.py`) — each function raises/doesn't
  raise on hand-crafted inputs.
- **Integration test proving real value**
  (`tests/test_invariants_enforcement.py`): a fake single-source, two-candidate
  provider reproduces a scenario that is architecturally reachable through
  the real engine — `resolution_status = AMBIGUOUS` with
  `confidence.score = 0.9639` (CONFIRMED-level) — because ambiguity detection
  (candidate-score proximity) and confidence scoring don't share a signal.
  Before this closure, `resolve()` would have silently returned that
  resolution. Now it raises `InvariantViolation`. A companion test confirms
  normal, non-ambiguous resolutions are unaffected.

This is the concrete, non-theoretical gap your P2.5 framing anticipated:
these weren't decorative invariants, they were catching a real reachable
state.

## C — Evidence / Provenance Generalization (VIR-INV-003, elevated)

**Before:** `_build_field_evidence()` covered exactly 6 hardcoded fields
(manufacturer, model, production.year, fuel, engine.power_kw,
transmission.type) out of ~23 leaf fields on `CanonicalVehicleIdentity`.
`invariant_003` was a no-op claiming this was "checked inline" — it wasn't.

**Fixed:** a single shared helper,
`_populated_identity_field_paths(identity)` (in `domain/invariants.py`),
enumerates every non-None leaf field. It is used by **both**:
- `ResolutionEngine._build_field_evidence()` — to know what to build evidence for
- `invariant_003_no_field_without_provenance()` — to know what evidence is required

Because both sides now read from the same source of truth, they cannot
silently drift apart again the way the original 6-field subset did.

**Elevated to a canonical, generalized invariant**, per your framing:
> No asserted resolved field may exist without attributable evidence.

**Verified live** via the API: a VIN resolution that previously returned 6
`field_evidence` entries now returns **14** (generation, body.type,
body.door_count, engine.commercial_name, engine.displacement_cc,
engine.cylinders, transmission.gears, drivetrain, identifiers.vin, plus the
original 6) — every populated field on the resolved identity, not a fixed
subset.

---

## What Was Deliberately Left Alone

Per the agreed P2.5 scope (A, B, C only):
- **VIR-INV-002** — left as-is. Already effectively enforced via Pydantic's
  enum typing on `CanonicalVehicleIdentity` fields; no code change needed.
- **VIR-INV-008, 009** — left as-is. Already `ENFORCED` per P2's audit, via
  `_query_providers()`'s exception handling and `_validate_input()`'s
  country-code check, respectively — not this invariant module.
- **VIR-INV-010** — left `UNENFORCED`, out of the agreed A/B/C scope.
- **`allowed_external_services`** — deliberately **not** added to
  `ResolutionEngine`. Per your framing, this is a genuine RGM/RGG concern
  (a runtime permission layer sitting in front of provider calls), not a
  Core invariant. It belongs in P3/P4.
- **`VIR_STORE_RAW_PROVIDER_PAYLOAD`** — left as a dormant/not-yet-applicable
  flag. No code was added to make it "look" enforced while no persistence
  layer exists. It becomes a real, checkable requirement once Persistence
  lands.

## Updated Status (vs. the P2 extraction table)

| Rule | Old Status | New Status |
|---|---|---|
| VIR-INV-001 | UNENFORCED (dormant) | **ENFORCED** |
| VIR-INV-003 | PARTIAL | **ENFORCED (generalized)** |
| VIR-INV-005 | UNENFORCED (dormant) | **ENFORCED** |
| VIR-INV-006 | UNENFORCED (dormant) | **ENFORCED** |
| VIR-INV-007 | UNENFORCED (dormant) | **ENFORCED** |
| VIR-BR-008 (evidence trail) | PARTIAL | **ENFORCED (via generalized INV-003)** |
| RGM draft: audit / preserve provenance | PARTIAL | **ENFORCED (via generalized INV-003)** |

**Remaining non-`ENFORCED` rows after this closure**, all confirmed to
genuinely belong outside Core:
- `allowed_external_services` — MISSING, belongs in RGM/RGG (P3/P4)
- `VIR_STORE_RAW_PROVIDER_PAYLOAD` — dormant policy, activates with Persistence
- `VIR-BR-001` / `VIR-BR-003` / `VIR-BR-004` (variant-claim evidence, VIN
  authenticity, user-vs-provider typed distinction) — PARTIAL, output/provider
  layer concerns, not touched in this closure (not in the agreed A/B/C scope)
- `VIR-INV-010` — UNENFORCED, not in scope

## Result

✅ 43/43 tests pass (17 new: 13 unit + 3 integration + regression guard)
✅ No regressions — all pre-existing resolution scenarios behave identically
✅ End-to-end verified via live API call (field_evidence coverage visibly
   expanded from 6 to 14 entries on a real VIN resolution)
✅ A genuine, previously-silent defect class (ambiguous + inflated
   confidence) is now architecturally blocked, proven via a realistic
   integration test, not just a unit-level function check
✅ Core/Runtime separation preserved — nothing added here that belongs to
   P3/P4 instead

The 31-rule P2 table is now cleaner input for P3: the rows that were
Core-shaped defects are closed, and what remains genuinely belongs to
runtime governance.
