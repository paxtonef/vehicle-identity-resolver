# Vehicle Identity Resolver — Runner Execution Contract (P1)

**Status:** Written from verified facts (P0 baseline + this session's inspection),
not from intentions. Every claim below was either read directly from source code
or tested empirically. No business logic was changed to produce this document.

---

## Runtime

```yaml
runtime:
  language: Python
  version: ">=3.12"
  verified_on:
    - "Python 3.12.3 (Linux, sandbox)"
    - "Python 3.14.2 (macOS, darwin)"
```

Note: `pyproject.toml` declares `requires-python = ">=3.12"`, and has been verified
working on both 3.12 and 3.14 in this session.

## Interfaces

```yaml
interfaces:
  http_rest:
    framework: FastAPI
    asgi_server: Uvicorn
    status: implemented, verified
  cli:
    entry_point: "vir"
    framework: argparse
    status: implemented, verified (console_scripts entry point added in P0)
```

## Dependencies

```yaml
dependencies:
  runtime:
    - pydantic>=2.0
    - pydantic-settings>=2.0
    - fastapi>=0.100
    - "uvicorn[standard]>=0.23"
    - pyyaml>=6.0
  dev:
    - pytest>=7.4
    - pytest-asyncio>=0.21
    - httpx>=0.24
```
Source: `pyproject.toml` (unchanged from P0, dependency list itself was already correct).

## Startup

```yaml
startup:
  canonical_command: "uvicorn vir.api.routes:app --host 0.0.0.0 --port 8000"
  cli_alternative: "vir resolve --manufacturer <name> --model <name> --year <year>"
  startup_time_observed: "< 1s (in-process, no external service calls at boot)"
```

## Configuration

```yaml
configuration:
  mechanism: pydantic-settings (env vars, optional .env file)
  variables:
    VIR_LOG_LEVEL:
      default: INFO
      required: false
    VIR_DEFAULT_LOCALE:
      default: fr-FR
      required: false
    VIR_PROVIDER_TIMEOUT_MS:
      default: 5000
      required: false
      note: "declared but not read by any current adapter (all adapters are in-memory stubs)"
    VIR_PROVIDER_API_KEY:
      default: null
      required: false
      note: "declared but not read by any current adapter — reserved for future real providers"
    VIR_STORE_RAW_PROVIDER_PAYLOAD:
      default: false
      required: false
```
Source: `src/vir/config.py`, `.env.example`.

## Network Requirements

```yaml
network:
  inbound:
    - "HTTP on configured port (FastAPI/Uvicorn), no TLS termination built in"
  outbound:
    current_state: "NONE — all three adapters (Manual, FrenchRegistrationProvider,
      VINDecoder) are in-memory stubs with zero outbound HTTP calls"
    declared_but_unused: "VIR_PROVIDER_TIMEOUT_MS / VIR_PROVIDER_API_KEY exist in
      Settings but are not consumed anywhere in adapter code today"
    future_state: "outbound HTTPS to real vehicle-data providers, once real
      adapters replace the stubs (tracked separately as 'Real Provider Adapters')"
```

## Storage Requirements

```yaml
storage:
  persistent_store: NONE
  evidence: >
    GET /v1/vehicle-identities/{id}, POST .../clarifications, and
    GET .../handoff/diagnostic all return HTTP 501 — the code comments
    explicitly state persistence is not yet implemented.
  packaged_configuration_resources:
    - vir/resources/business_rules.yaml   (required)
    - vir/resources/confidence_weights.yaml (required)
    - vir/resources/vehicle_taxonomy.yaml   (required)
  filesystem_writes: NONE
```

### ✅ Resolved — Configuration Integrity Chain (P0.1)

**Original defect:** `src/vir/config.py` resolved `config/` relative to
`__file__`, three directories up from the module. This worked only under
`pip install -e .` (editable install), and was confirmed broken — silently
returning `{}` with no exception — when installed from a real wheel outside
the source tree (a normal production `pip install`, or most Dockerfiles).

**Fix applied and verified in this session:**

```
RESOURCE EXISTS
      ↓
RESOURCE READABLE
      ↓
YAML PARSES
      ↓
SCHEMA VALID
      ↓
REQUIRED RULES PRESENT
      ↓
RUNNER READY
```

1. The three YAML files moved from root `config/` into `src/vir/resources/`
   and are now packaged via `[tool.setuptools.package-data]` — verified
   present inside a real built wheel.
2. `vir/config.py` now loads them via `importlib.resources` (package-relative,
   not filesystem-path-relative), so the loading mechanism is independent of
   install layout.
3. A new `vir.config.ConfigurationError` is raised — not a silent `{}` — at
   the first failing stage of the chain above, with a message identifying
   which resource and which stage failed.
4. All three resources are treated as required; each is schema-validated
   (`business_rules.yaml` needs a non-empty `rules` list with `id`+`rule`
   per entry; `confidence_weights.yaml` needs non-empty `weights` and
   `levels` mappings; `vehicle_taxonomy.yaml` needs a non-empty `taxonomy`
   mapping).
5. Loading is eager at module-import time, so a configuration defect blocks
   `import vir` — and therefore blocks both API and CLI startup — instead of
   letting the process come up "operational" with empty rules.

**Verified this session:**
- Build a real wheel → install in a directory with zero relation to the
  source tree → `import vir.config` → all three resources load with correct
  content (10 business rules, 5 confidence weight keys, 4 taxonomy
  categories).
- Negative tests (missing resource, corrupt YAML, empty document, empty
  required list, missing sub-key) all raise `ConfigurationError` and block
  import, confirmed both by manual reproduction and by 9 new permanent
  pytest tests in `tests/test_config_integrity.py`.
- Full regression: 26/26 tests pass (17 original + 9 new), on a fresh
  editable install.
- End-to-end: app starts, `/health` returns 200, in the same session.

**Runtime impact of the original defect, for the record:** zero in the
current codebase — `ConfidenceEngine` (`domain/confidence.py`) already used
its own hardcoded default weights, identical in value to
`confidence_weights.yaml`, and no code anywhere referenced
`business_rules_config` or `taxonomy_config` outside `config.py` itself. The
defect was latent, not yet triggering incorrect behavior — but the values
matching exactly is a strong signal that wiring was intended, which is
exactly why this was treated as P0.1-blocking rather than deferred.

## Provider Requirements

```yaml
providers:
  interface: vir.ports.vehicle_provider.VehicleDataProvider (ABC)
  required_methods:
    - resolve_registration(number, country)
    - decode_vin(vin)
    - retrieve_vehicle_configuration(**kwargs)
  current_implementations:
    - id: manual_input
      type: stub
      supported_countries: []
      supported_identifiers: [manual]
    - id: provider-fr-registration
      type: stub (in-memory fixture dict, 3 known plates)
      supported_countries: [FR]
      supported_identifiers: [registration]
    - id: vin-decoder-stub
      type: stub (1 known full-decode VIN, WMI-based partial fallback for others)
      supported_countries: []
      supported_identifiers: [vin]
  none_are_network_backed: true
```

## Health Verification

```yaml
health:
  endpoint: "GET /health"
  response: '{"status": "ok", "version": "0.1.0"}'
  http_status: 200
  verified: true
```

## Test Command

```yaml
tests:
  command: "pytest"
  working_directory: "project root (no PYTHONPATH needed after P0 fix)"
  count: 17
  result: "17 passed"
  verified_on:
    - "Linux sandbox, Python 3.12.3, pytest 9.1.1"
    - "macOS, Python 3.14.2, pytest 9.1.1"
  gotcha_observed: >
    On zsh, a `pytest` binary resolved before venv activation can be cached by
    the shell's command hash table and keep running even after activating a
    new venv (symptom: wrong pytest/plugin versions in the header, or the
    old ModuleNotFoundError reappearing). Fix: `hash -r` after activating,
    or invoke as `python3 -m pytest` to bypass shell path caching entirely.
```

## Supported Execution Environments

```yaml
supported_execution:
  macOS_development:
    status: verified
    detail: "macOS, Python 3.14.2, install → test → start → health all passed"
  linux:
    status: verified
    detail: "Linux sandbox, Python 3.12.3, install → test → start → health,
      resolve, and CLI all passed"
  docker:
    status: NOT VERIFIED THIS SESSION
    detail: "No Docker available in the verification sandbox. A Dockerfile is
      not yet written. Given the config-loading risk above, any Dockerfile
      must be written after that risk is resolved, or it will silently
      reproduce the empty-config bug (COPY src/ without config/ is the
      textbook way to trigger it)."
  cloud:
    status: NOT ASSESSED
    detail: "No cloud-specific requirements identified yet (no persistent
      volumes, no external service bindings beyond optional future HTTP
      egress to providers). Revisit once Persistence and Real Provider
      Adapters land."
```

## Runtime Verification Checklist (for CI / deployment gates)

```yaml
runtime_verification:
  - step: package_import
    command: 'python3 -c "import vir"'
    status: automatable, verified
  - step: config_validation
    command: 'python3 -c "import vir.config"'
    status: >
      SAFE TO AUTOMATE (P0.1 fix applied and verified). A broken or missing
      required resource now raises vir.config.ConfigurationError and blocks
      import instead of silently degrading to an empty config. This command
      alone is now a valid CI gate for configuration integrity.
  - step: provider_availability
    status: "N/A today — all providers are in-memory stubs, always available"
  - step: store_availability
    status: "N/A today — no persistent store exists yet"
  - step: api_health
    command: "curl -f http://localhost:8000/health"
    status: automatable, verified
```

---

## Summary

✅ Runtime, interfaces, dependencies, startup, health, and test command are all
verified facts, consistent across two OSes and two Python versions.
✅ No outbound network today; declared-but-unused provider settings are
documented so they aren't mistaken for active behavior.
✅ Configuration integrity chain fixed and verified (P0.1): required YAML is
now packaged, loaded via importlib.resources, schema-validated, and any
failure blocks startup with a clear diagnostic instead of degrading silently.
26/26 tests pass, including 9 new negative tests for this exact chain.
⏸️ Docker and cloud execution are explicitly marked unverified rather than
assumed, per the "facts not intentions" rule for this document. Now that the
config-loading risk is resolved, writing a Dockerfile is unblocked.
