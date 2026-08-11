# Vehicle Identity Resolver — User Interaction Contract (UIC)

**Status:** written from verified facts about the existing API/CLI surface
(same discipline as REC/RGM), plus explicit new design for the parts that
didn't exist yet. Sections that depend on Persistence (not yet built) are
marked as such rather than invented.

**Audience:** whoever builds the Web Product Layer against this API. This
document is the contract between "what the runner actually does" and "what
a human using it should be told" — it does not change any runner behavior.

---

## 1. What the User Provides

One of three identifier types, plus a consent flag:

| Input | Required fields | Optional fields |
|---|---|---|
| VIN | `vin` (17 chars) | — |
| Registration | `registration.registration_number`, `registration.country_code` | — |
| Manual description | `manual_identity.manufacturer` + `manual_identity.model` | `production_year`, `fuel_type`, `engine_displacement_cc`, `engine_power_kw`, `transmission_type` |
| — | `consent.external_lookup_allowed` (always required) | — |

At least one identifier is mandatory (`VIR-IN-001`). A user can supply more
than one (e.g. VIN + manual description) — the resolution engine treats
every supplied source as evidence, not as a single choice.

## 2. What the Runner Explains

Every resolution response includes, regardless of outcome:
- `resolution_status` — one of 8 values (table below)
- `confidence.score` (0–1) and `confidence.level` (unresolved/low/medium/high/confirmed)
- `field_evidence` — every resolved field, with its source(s) and their
  reliability (generalized in P2.5 — this is not a curated summary, it's
  the complete evidence set)
- `limitations` — plain-language caveats (e.g. *"Exact factory
  configuration cannot be confirmed without VIN."*)
- `unresolved_fields` — which fields could not be determined at all

### `resolution_status` — meaning for the user

| Status | What it means to the user |
|---|---|
| `resolved` | High-confidence identity, safe to hand off downstream |
| `provisionally_resolved` | Usable identity, but not fully confirmed — treat as a starting point, not a final answer |
| `ambiguous` | More than one vehicle configuration fits the data given — the user needs to pick or provide more detail |
| `insufficient_data` | Not enough information was found or provided to identify anything |
| `contradictory` | The information provided (or found) conflicts with itself — needs the user to resolve which value is correct |
| `unsupported_country` | The registration's country isn't covered by any available provider |
| `provider_unavailable` | An external lookup was attempted but failed — the user's own data (if any) is still used, nothing is fabricated to fill the gap |
| `invalid_identifier` | The input itself was malformed (e.g. a 15-character VIN) |

## 3. What Uncertainty Looks Like

Uncertainty is never hidden behind a single "confidence score" alone —
it's always paired with *why*:
- `contradictions` — explicit conflicts between sources, each naming the
  conflicting values and their origins
- `alternative_candidates` — when more than one plausible identity exists,
  every candidate is returned, not just the top-scored one
- `limitations` — a human-readable list explaining what couldn't be
  verified and why (e.g. no VIN was supplied, so exact configuration is
  unconfirmed)

Per `VIR-INV-005`/`VIR-INV-007` (wired in P2.5), an `ambiguous` resolution
can never carry an inflated confidence score or a `confirmed` level — the
uncertainty signal and the confidence signal cannot contradict each other.

## 4. What a Clarification Means

A `clarification_questions` entry is a **targeted, optional** request for
one more piece of information — never a blocking requirement. Each has:
- `target_field` — exactly which field it would help resolve
- `reason` — why it's being asked (e.g. `multiple_engine_variants_found`)
- `prompt` — the actual human-readable question
- `choices` (when applicable) — a closed set of options, always including
  an explicit "I don't know" option where relevant
- `required: false` (in the current implementation) — a clarification is
  always a chance to improve the result, never a hard gate

**Known gap (Persistence-dependent):** `POST .../clarifications` currently
returns HTTP 501 — a client cannot yet submit a clarification answer
against a stored resolution; it must resubmit the full request with the
answer folded into the original input (e.g. as `manual_identity` data).
This UIC describes the intended experience once Persistence exists; it
does not claim the round-trip works today.

## 5. What Consent Means

`consent.external_lookup_allowed` is a single, binary, request-scoped
flag — not a stored preference. Setting it to `false`:
- Blocks any provider-capable call outright (VIN/registration lookups) if
  that identifier type was supplied — the request fails immediately with
  `ExternalLookupNotAuthorizedError` (HTTP 403), not silently degraded
- Manual-only input is unaffected — is always processed regardless of
  this flag, since it involves no external lookup

**What this flag does *not* do (documented gap, from
`RUNTIME_GOVERNANCE_MANIFEST.md`):** it is not scoped per-provider. A user
cannot currently say "look me up in the FR registry but not the VIN
decoder" — it's all-or-nothing. If a product requirement ever needs that
granularity, it requires a Core change (`ConsentInput`), not just a UI
change.

## 6. What Happens When a Provider Fails

Per `VIR-BR-009` (Core-enforced): a provider failure never invalidates
data the user already supplied, and never triggers fabricated fallback
data (`VIR-INV-008`). From the user's perspective:
- If a provider errors out or is denied by governance (P4's RGG), the
  resolution simply proceeds with whatever other sources are available
- If *no* source produces anything, the result is `insufficient_data` (or
  `provider_unavailable` when providers were queried but returned
  nothing) — never a fabricated identity
- The user is never shown *which* provider failed vs. was denied by
  governance vs. had no match — from their perspective these all reduce to
  "that source didn't help", by design (keeps `VIR-BR-009` simple and
  doesn't leak internal governance decisions into user-facing output)

## 7. What Can Be Corrected

**Not yet defined — blocked on Persistence.** Today, every resolution is
stateless: there is no stored resolution a user could return to and amend.
The only "correction" mechanism today is resubmitting `POST
/resolve` with different or additional input. Once Persistence exists,
this section needs real answers to:
- Can a user amend a past resolution, or only create a new one referencing it?
- Which fields are ever user-correctable vs. always provider/evidence-derived?
- Does a correction re-run the full resolution, or patch the stored result?

## 8. What Is Persisted

**Not yet defined — blocked on Persistence.** Confirmed in P1/REC: no
persistent store exists. `GET /v1/vehicle-identities/{id}`, `POST
.../clarifications`, and `GET .../handoff/diagnostic` all return HTTP 501
today. This section will need to specify, once Persistence lands:
- Whether the full resolution is stored, or a summary
- Whether raw provider payloads are ever stored (governed by
  `RUNTIME_GOVERNANCE_MANIFEST.md`'s `data_export.raw_provider_payload`,
  currently `DORMANT` — this UIC section and that RGM section must be
  designed together, not independently)
- Retention period and deletion mechanism

## 9. When a Resolution Expires

**Not yet defined — blocked on Persistence.** There is currently no
concept of resolution lifetime, since nothing is stored. Needs a real
answer once Persistence exists — vehicle data changes slowly (a car's
factory configuration doesn't change), so "expiry" likely means something
closer to *"how long do we trust a cached lookup before re-querying a
provider"* rather than *"when does this become invalid"* — but that's a
product decision, not assumed here.

---

## Summary

✅ Sections 1–6 are fully specified from real, verified API/CLI behavior —
nothing invented, nothing assumed beyond what the code actually does.
⏸️ Sections 7–9 are explicitly left open, not filled with plausible-sounding
placeholder content — they depend on Persistence design decisions this
document does not make unilaterally, consistent with the "facts not
intentions" discipline used throughout this project (P0.1, P3).
