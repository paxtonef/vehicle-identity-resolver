# Vehicle Identity Resolver — P6: Persistence + Web Product Layer

**Decisions taken (yours):** SQLite for Persistence; server-rendered
HTML/Jinja2, no JS framework, for the Web Product Layer.

**90/90 tests pass** (70 pre-existing + 20 new). No regressions. Verified
in a real wheel installed away from the source tree — templates included
correctly (same discipline P0.1 established for config, applied here).

---

## Persistence (SQLite)

`src/vir/persistence.py` — one table (`resolutions`), full resolution JSON
keyed by `resolution_id`. Unblocks the 3 previously-501 endpoints:

- `GET /v1/vehicle-identities/{id}` — now returns the stored resolution, or
  a proper `404` (`VIR-ERR-010`, new) instead of crashing
- `POST /v1/vehicle-identities/{id}/clarifications` — now works (see below)
- `GET /v1/vehicle-identities/{id}/handoff/diagnostic` — now returns the
  real diagnostic handoff built from the stored resolution

**What this does NOT do**, stated plainly rather than assumed:
- Does **not** activate `RUNTIME_GOVERNANCE_MANIFEST.md`'s
  `data_export.raw_provider_payload` flag. Nothing in the current adapter
  layer produces a raw provider payload to begin with
  (`ProviderVehicleRecord.raw_payload_reference` is always `None`) — only
  the already-normalized resolution is ever persisted. That flag remains
  `DORMANT`, honestly, not fabricated into looking active.
- No retention/expiry policy (User Interaction Contract section 9 — still
  an open product question, not decided here).
- No connection pooling; a short-lived `sqlite3` connection per operation.
  Correct for the dev/demo scope you chose, not sized for high concurrency
  — documented, not hidden.

## A Dormant Piece of Code, Reactivated

`src/vir/application/clarify_resolution.py`'s `ClarifyResolutionUseCase`
already existed, fully implemented — and was never wired to anything,
same pattern as the dormant invariants found in P2.5. Reused as-is rather
than reimplementing clarification-merge logic from scratch.

### Two pre-existing limitations this surfaced (not introduced by P6, not fixed — flagged for your decision)

1. **`_reconstruct_request()` drops the original registration number.**
   It rebuilds a request from the *resolved identity's* fields, but never
   carries forward `identifiers.registration_number` — only VIN (if the
   identity had one). A clarification round-trip on a registration-based
   lookup silently falls back to manual-only re-resolution on the second
   pass. Verified end-to-end: after clarifying `AM-BIG-01`, the new
   resolution's `source_summary` shows only `manual_input`, not
   `provider-fr-registration`.

2. **`_dispatch()`'s manual pathway never forwards engine/transmission
   fields.** `ResolutionEngine._dispatch()` calls
   `provider.retrieve_vehicle_configuration(manufacturer=..., model=...,
   year=..., fuel_type=...)` — it does not pass `engine_power_kw`,
   `engine_displacement_cc`, or `transmission_type`, even though
   `ManualIdentityInput` carries them and `ManualAdapter` reads them if
   given. This predates P6 (found by testing the reactivated clarify flow
   end-to-end with a real power_kw answer) — the answer is accepted and
   stored on the request, but the manual provider never receives it, so it
   doesn't end up in the new resolution's evidence.

Both are real, verified gaps in existing application code — not
documentation speculation. Neither was fixed here, per the established
process (P0.1, P2.5): application code changes need your go-ahead first.

## Web Product Layer (HTML/Jinja2)

`src/vir/web/` — `routes.py` + `templates/{base,index,result}.html`.
Mounted into the same FastAPI `app` (`api/routes.py`), so
`uvicorn vir.api.routes:app` remains the single, unchanged canonical start
command from `RUNNER_EXECUTION_CONTRACT.md`.

**New dependencies** (both required at runtime, not just dev):
`jinja2>=3.1` (templating) and `python-multipart>=0.0.9` (Starlette
requires this to parse *any* HTML form body, even simple
`application/x-www-form-urlencoded`).

**Routes:**
- `GET /` — intake form (VIN, registration+country, manual fields, consent
  checkbox — all shown together, since "no JS" rules out conditionally
  hiding sections)
- `POST /resolve` — runs the same `ResolveVehicleUseCase` the JSON API
  uses, saves via the same `STORE`, renders the result page
- `POST /clarify/{resolution_id}` — runs the same (now-wired)
  `ClarifyResolutionUseCase`, re-renders the result page

**Result page** shows, per `USER_INTERACTION_CONTRACT.md`: a plain-language
status label + description (French, mirroring the UIC's status table),
confidence, resolved identity fields, contradictions, alternative
candidates, unresolved fields, limitations, full field-by-field evidence
with sources, and — when applicable — a clarification form built directly
from `clarification_questions` (radio buttons for closed choices, text
input otherwise).

**Error handling:** a `VIRBaseError` (e.g. missing consent, invalid VIN,
resolution not found) is caught and re-rendered as a plain-language message
on the same page — never a raw 500 or a stack trace.

## Packaging Verified (P0.1 discipline applied to templates)

Built a real wheel, installed it in a directory unrelated to the source
tree, confirmed:
```
Web routes import OK, templates dir: .../site-packages/vir/web/templates
Templates dir exists: True
GET / -> HTTP:200
POST /resolve -> HTTP:200
```
Templates are resolved via a package-relative path
(`Path(__file__).parent / "templates"`), not a project-root-relative one —
the exact class of bug P0.1 fixed for `config.py`, avoided here from the
start rather than discovered and patched later.

## Test Coverage (20 new tests)

- `tests/test_persistence.py` (6) — CRUD round-trip, overwrite semantics,
  idempotent schema creation, unwritable-path error, nested-field fidelity
- `tests/test_api_persistence.py` (6) — the 3 JSON endpoints, each with a
  positive and a 404 case, plus the clarification round-trip
- `tests/test_web.py` (8) — form rendering, VIN/manual/ambiguous scenarios,
  consent-missing and invalid-VIN error rendering (verified as real
  rendered error `<div>`s, not false-positive substring matches against
  the page's always-present CSS class *definitions* — an early version of
  these tests had exactly that bug, caught and fixed before delivery)

## Result

✅ All 3 previously-501 endpoints work, backed by real SQLite persistence,
   accessed exclusively through `PersistencePort`
✅ A fully-implemented but previously-dormant use case (clarification
   merging) is now wired in, reused rather than reimplemented
✅ Two real, pre-existing limitations in that reactivated code path found
   and documented via genuine end-to-end testing, not fixed without approval
✅ Minimal server-rendered web UI covering the full flow from
   `USER_INTERACTION_CONTRACT.md`: intake → result → clarification →
   updated result
✅ Packaging correctness for templates verified via a real wheel install,
   proactively, using the exact lesson P0.1 taught for config
✅ 97/97 tests pass; an early test-quality bug (CSS-class-definition false
   positives) was caught and corrected before delivery, not shipped
✅ Persistence sits behind `PersistencePort`; SQLite is one interchangeable
   adapter, proven substitutable by an independent in-memory adapter that
   the API/Web layer runs against with zero code changes
✅ The persisted schema now includes the request itself (as received),
   not just the resolution — closing the gap your message identified

---

## Addendum — Architectural Refactor (Your Follow-Up)

Your message refined both decisions further. This addendum documents what
changed on top of the initial P6 delivery above; the rest of this document
still describes the overall shape correctly.

### Persistence: SQLite Behind a Real Port

**Before:** `PersistenceStore` was a concrete SQLite class, imported
directly by `api/routes.py` and `web/routes.py`.

**Now**, mirroring the existing `VehicleDataProvider` port/adapter pattern
exactly:

```
vir/ports/persistence_port.py        <- PersistencePort (ABC) + PersistenceError
vir/adapters/sqlite_persistence_adapter.py  <- SQLitePersistenceAdapter(PersistencePort)
vir/persistence.py                    <- wiring only: STORE: PersistencePort = SQLitePersistenceAdapter(...)
```

`api/routes.py` and `web/routes.py` import `STORE` from `vir.persistence`
exactly as before — the call sites didn't need to change, because they
already only used the two methods now formalized on the port. What changed
is that this is now *enforced by an abstract base class*, not just a
convention.

**Proven, not just asserted:** `tests/test_persistence_port.py` implements
a second, completely independent `PersistencePort` — a plain in-memory
dict-backed adapter, sharing no code with SQLite — and runs the *real* API
and Web layers against it via dependency substitution. Both work
unchanged. This is the concrete evidence that Core/API depend on the
abstraction, not on SQLite specifically, and that a future
`PostgreSQLAdapter` is a new file, not a rewrite.

### Schema Extended: the Request Is Now Persisted Too

Per your message's list of what should be stored, `resolution_id` +
"requête normalisée" (among others) — the schema gained a `request_json`
column. `PersistencePort.save_resolution()` now takes both `request` and
`resolution`; `get_request()` is a new port method.

**Scope boundary, stated precisely:** what's stored is the request *as
received* at the API/Web boundary — not the internally re-normalized
version `ResolutionEngine._normalize_identifiers()` produces on a copy,
which is never returned outward. Exposing that would require a small
`ResolutionEngine` return-contract change, which is Core work, out of
scope for this persistence-architecture pass. Documented in
`SQLitePersistenceAdapter`'s docstring, not silently assumed away.

**Not used yet to fix Limitation #1** (registration number lost on
clarification): `ClarifyResolutionUseCase._reconstruct_request()` still
rebuilds from the resolved identity, not from the newly-available stored
request. Now that the request is persisted, wiring it in *would* fix that
limitation cleanly — but that's a behavioral change to existing
(reactivated) business logic, and per this project's standing rule,
still waiting on your go-ahead rather than done silently alongside an
architecture refactor.

**One additive, low-risk signature change**: `ClarifyResolutionUseCase.execute()`
now returns `tuple[VehicleIdentityRequest, VehicleIdentityResolution]`
instead of just the resolution — needed so callers can pass both to
`save_resolution()`. This class was inert before this session (P6
reactivated it) and has exactly one caller in each of `api/routes.py` and
`web/routes.py`, both updated. Not treated as a "found a pre-existing bug,
needs approval" situation, since no previously-shipped behavior changed.

### Web Product Layer: Confirmed, No Change Needed

Your constraint — "Jinja2 ne doit jamais devenir la couche métier" — was
already true structurally in the original P6 delivery:
`web/routes.py` calls the exact same `ResolveVehicleUseCase` /
`ClarifyResolutionUseCase` the JSON API calls, and now the exact same
`STORE: PersistencePort`. `tests/test_persistence_port.py`'s
`test_web_layer_works_unchanged_against_a_non_sqlite_adapter` extends the
substitutability proof to the web layer too. No template or route logic
needed to change for this refinement — the architecture already matched
your requirement; this pass made the persistence side of it provably true
as well.

### Verification

- **97/97 tests pass** (90 from initial P6 + 7 new: 3 persistence-port
  tests for request storage/retrieval, 5 substitutability tests)
- Real wheel built and installed away from the source tree:
  `isinstance(STORE, PersistencePort)` → `True`,
  concrete type `SQLitePersistenceAdapter` — confirms the wiring survives
  packaging, not just editable-install
- Full endpoint smoke test (resolve → get) against that clean install,
  200 on both
