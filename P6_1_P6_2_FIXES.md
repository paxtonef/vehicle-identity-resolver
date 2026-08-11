# Vehicle Identity Resolver — P6.1 & P6.2: Clarification Integrity + Mapping Completeness

**Sequencing (yours):** fix both before Real Provider Adapters — no point
bringing in higher-quality external data onto a chain that still loses
part of it internally.

**103/103 tests pass** (97 pre-existing + 6 new). Both fixes verified
end-to-end: API, web UI, and a deliberately-reintroduced-then-caught
regression test.

---

## P6.1 — Clarification State Integrity

**Invariant (yours), now enforced in code and tests:**
> Clarification MUST preserve all previously accepted identification
> inputs unless the user explicitly corrects them.

**Root cause:** `ClarifyResolutionUseCase._reconstruct_request()`
rebuilt an approximate request from the *resolved identity*
(`CanonicalVehicleIdentity`), which never carried
`identifiers.registration_number` forward. Any clarification on a
registration-based resolution silently lost the plate number and fell
back to manual-only re-resolution.

**Fix:** `ClarifyResolutionUseCase.execute()` now takes the actual
original request — fetched from `PersistencePort.get_request()`, not
reconstructed — and applies answers on top of it. Since the P6.1 refactor
made `PersistencePort` store the real request alongside every resolution,
this fix was a matter of *using* data that already existed, not adding
new storage.

**Generalization beyond registration_number:** the fix is structural, not
a special case for one field — starting from the real original request
means VIN, country, manufacturer/model, and any other already-submitted
field is preserved by construction, not by a growing list of special
cases. Verified directly: `test_clarification_preserves_vin_when_...`,
`test_clarification_preserves_manual_fields_already_confirmed`.

**Side fix, same discipline:** answer application now resolves
`target_field` from the resolution's own `clarification_questions`
instead of matching hardcoded `question_id` strings
(`"VIR-Q-001"`/`"VIR-Q-VIN"`). `test_apply_answers_uses_target_field_not_hardcoded_question_id`
proves an answer to a *differently-named* question with the same
`target_field` is still applied correctly — this generalizes to any
clarification question the engine might generate in the future, not just
the two that exist today.

## P6.2 — Mapping Completeness Contract

**Invariant (yours), now enforced in code and tests:**
> Each supported attribute must either traverse the whole chain (Provider
> data → normalized candidate → resolution → field evidence → API/Web
> output), or be explicitly rejected/ignored. It must not disappear
> silently.

**Root cause:** `ResolutionEngine._dispatch()`'s manual-identifier branch
forwarded only `manufacturer`, `model`, `year`, `fuel_type` to
`ManualAdapter.retrieve_vehicle_configuration()` — even though
`ManualIdentityInput` carries (and `ManualAdapter` reads)
`engine_displacement_cc`, `engine_power_kw`, and `transmission_type` too.
A user-supplied or clarification-supplied engine power never reached the
adapter, and therefore never appeared anywhere downstream.

**Fix:** `_dispatch()` now forwards all seven `ManualIdentityInput`
fields.

**Where this fix sits in the chain, per your diagram:**
```
Provider data → normalized candidate → resolution → field evidence → API/Web output
     ^ fixed here (P6.2)                    ^ already fixed in P2.5
```
The `resolution → field evidence → output` half of the chain was already
closed in P2.5 (evidence generalized from 6 hardcoded fields to every
populated identity field). P6.2 closes the other half:
`request → provider call`. Together, an attribute that enters the system
now either reaches the output or is explicitly not asked for — not lost
silently in the middle.

**Generalized, not just patched:** rather than only testing that the 3
specific fields found this session are now forwarded,
`test_mapping_completeness_every_manual_identity_field_is_forwarded`
introspects `ManualIdentityInput.model_fields` directly and asserts every
field it declares is present in the dispatch call — with a self-check
(`assert set(field_values.keys()) == set(ManualIdentityInput.model_fields.keys())`)
that fails loudly if someone adds a new field to the model without
updating this test's fixture. A future field silently dropped from
`_dispatch` fails the test suite instead of shipping.

**Proven to actually catch regressions, not just pass today:** the fix
was temporarily reverted and the test suite re-run — both the concrete
and the generalized completeness test failed with a clear message
(`_dispatch failed to forward: {'engine_displacement_cc',
'transmission_type', 'engine_power_kw'}`), then the fix was restored. This
wasn't asserted, it was demonstrated.

## Verified End-to-End

- **API**: resolve `AM-BIG-01` (ambiguous) → clarify with `power_kw=81` →
  response shows `identifiers.registration_number: "AM-BIG-01"` (was
  `null`) and `engine.power_kw: 81.0`, `source_summary` shows
  `provider-fr-registration` re-queried (was `manual_input` only)
- **Web UI**: same scenario through the HTML forms — result page shows
  `Immatriculation: AM-BIG-01` and `Moteur: PureTech 110 (81.0 kW)`
- **Full regression**: 103/103, no change to any pre-existing test's
  behavior

## Result

✅ P6.1 invariant enforced structurally (real request preserved, not
   reconstructed) and proven for VIN, registration, and manual fields
✅ P6.2 mapping-completeness contract enforced and proven with a
   self-checking, introspection-based test — not a hardcoded field list
✅ Both regressions proven catchable: fixes were reverted, tests failed
   with clear messages, fixes restored
✅ 103/103 tests pass; verified via API, Web UI, and unit/contract tests
✅ Per your framing: VIR core/product v1 is now architecturally complete.
   Real Provider Adapters (P7) become a capability extension, not a repair.
