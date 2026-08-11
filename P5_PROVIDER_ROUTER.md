# Vehicle Identity Resolver — P5: Provider Router

**Scope taken:** formalize provider selection into a declarative registry +
a single governance decision point, replacing duplicated hardcoded lists
and duplicated permission checks. **Real Provider Adapters (actual
external HTTP APIs) are explicitly out of scope** — that requires choosing
real vendors/countries and provisioning credentials, which is a product
decision, not something to fabricate. This sandbox's network access is also
restricted to a small package-registry allowlist, so real external provider
calls couldn't be tested here even if built blindly.

**70/70 tests pass** (58 pre-existing + 12 new). No regressions.

---

## What Changed

### 1. Provider Registry (new)

`src/vir/resources/provider_registry.yaml` — single declarative source of
truth for which adapter classes exist:

```yaml
provider_registry:
  providers:
    - provider_id: manual_input
      module: vir.adapters.manual_adapter
      class_name: ManualAdapter
      countries: []
      identifier_types: [manual]
    # ... provider-fr-registration, vin-decoder-stub
```

`src/vir/provider_registry.py` loads and validates it with the same
integrity discipline as `vir.config` (P0.1) and `vir.governance` (P4):
RESOURCE EXISTS → READABLE → PARSES → SCHEMA VALID, raising
`ProviderRegistryError` explicitly rather than degrading silently.

**Beyond loading**, `build_providers()` cross-checks each instantiated
adapter against its registry declaration — if `provider_registry.yaml`
claims a class's `adapter_id`, `supported_countries`, or
`supported_identifier_types` are something they're not, loading fails
loudly instead of routing incorrectly at runtime.

**Replaces:** two previously-duplicated hardcoded `_DEFAULT_PROVIDERS`
lists in `api/routes.py` and `cli/main.py` — both entry points now call
`build_providers()`, so they cannot silently drift apart the way they were
structurally able to before.

### 2. Consolidated Governance Check

`ResolutionEngine._query_providers()` previously called
`RGG.is_provider_permitted()` three times, once per identifier-type branch
(vin/registration/manual), each duplicating the same two-line pattern.

Refactored into two small, focused steps:
- `_applicable_identifier(provider, request)` — pure capability matching,
  no governance decision
- One `RGG.is_provider_permitted(...)` call, applied uniformly regardless
  of identifier type
- `_dispatch(provider, identifier_type, request)` — the actual provider call

This is a refactor, not a behavior change — confirmed by the full
regression suite passing unchanged.

### 3. Tests (`tests/test_provider_registry.py`, 12 new)

- 6 integrity-chain tests (missing/unreadable/invalid YAML/missing keys —
  mirrors `test_config_integrity.py` and `test_governance.py`)
- 3 class/declaration parity tests (wrong declared `provider_id`, wrong
  declared `countries`, unimportable module — each must fail loudly)
- 1 positive control (`build_providers()` returns 3 real, working instances)
- 1 registry/RGM coverage guard: every registered provider must have a
  matching RGM allowlist entry — not a runtime failure (default:deny
  already handles an unlisted provider safely), but a test-suite failure
  that catches "you added a provider and forgot to update the RGM" before
  it ships as a silent, confusing denial.

## What Was Deliberately Not Done

- **No "cost/availability policy" scoring.** The original plan sketch
  mentioned this loosely; nothing in the current codebase (3 stub adapters,
  no real network calls) justifies building speculative selection logic
  with no real signal behind it. If/when real providers with actual
  latency/cost/availability characteristics exist, this is worth
  revisiting — not before.
- **No Real Provider Adapters.** Building real HTTP-backed adapters
  requires: choosing actual vendor(s) for VIN decoding and per-country
  registration lookups, provisioning API credentials, and deciding data
  retention/consent implications those integrations bring — all product
  and legal decisions, not engineering ones this session can make
  unilaterally. `RUNTIME_GOVERNANCE_MANIFEST.md`'s `outbound_network` and
  `external_services` sections are already structured to accept real
  entries once those decisions are made; the registry format
  (`provider_registry.yaml`) is likewise ready to declare a real adapter
  the same way it declares the stubs today.

## Verification Performed

- Fresh install → `pytest` → 70/70 passed
- Real wheel built and installed in a directory unrelated to the source
  tree → `build_providers()` returns the correct 3 instances
- CLI entry point (`vir resolve ...`) exercised from that clean install,
  confirmed working
- API entry point (`uvicorn vir.api.routes:app`) started, `/health` and a
  full `/resolve` call (French plate `AB-123-CD`) both exercised from that
  same clean install, confirmed correct `provisionally_resolved` output
  with full field evidence
