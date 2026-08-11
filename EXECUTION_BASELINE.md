# VIR — P0 Execution Baseline

**Scope:** Packaging & Executability Baseline only. No business logic, RGG, provider,
or web UI changes. This document records verified facts, not intentions — every
line below was executed and observed during this session.

## 1. Root Cause of the Original Bug

The reported `ModuleNotFoundError: No module named 'vir'` was **not** a defect in
`pyproject.toml`. It was reproduced and confirmed to be caused by running `pytest`
in an environment where dependencies were installed but the `vir` package itself
was never installed (`pip install -e .` was skipped). Once the package is
installed, `pytest` passes with no `PYTHONPATH` manipulation — this was true even
before any changes were made to `pyproject.toml`.

## 2. Change Made

`pyproject.toml` had a working `[project]` section but no `[build-system]` table,
so pip fell back to an implicit default backend. This is fragile across pip/
setuptools versions and non-reproducible in CI. The following was added:

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project.scripts]
vir = "vir.cli.main:run"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
vir = []
```

This pins the build backend explicitly, declares the `src/` layout explicitly
(instead of relying on setuptools auto-discovery), and adds a `vir` console
script entry point so the CLI is invocable as `vir ...` instead of
`python -m vir.cli.main`.

## 3. Canonical Command Sequence (Verified)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python3 -c "import vir; print(vir.__version__)"
pytest
uvicorn vir.api.routes:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

No `PYTHONPATH` is required at any step.

## 4. Verification Log (this session, fresh `.venv`)

| Step | Command | Result |
|------|---------|--------|
| Editable install | `pip install -e ".[dev]"` | ✅ exit 0 |
| Import | `python3 -c "import vir"` | ✅ `0.1.0` |
| CLI entry point | `which vir` / `vir --help` | ✅ resolves to `.venv/bin/vir`, help text renders |
| Tests (project root) | `pytest` | ✅ 17 passed |
| Tests (from unrelated cwd `/tmp`, explicit path) | `pytest <path>/tests` | ✅ 17 passed |
| App startup | `uvicorn vir.api.routes:app --host 127.0.0.1 --port 8123` | ✅ `Application startup complete.` |
| Health check | `curl http://127.0.0.1:8123/health` | ✅ `{"status":"ok","version":"0.1.0"}` (HTTP 200) |
| End-to-end resolve | `POST /v1/vehicle-identities/resolve` (manual identity, no external lookup) | ✅ HTTP 200, correct `insufficient_data` status, confidence 0.46, evidence + limitations populated |
| CLI resolve | `vir resolve --manufacturer Renault --model Clio --year 2019 --output compact` | ✅ `insufficient_data\|0.46\|NONE` |
| Package metadata | `pip show vehicle-identity-resolver` | ✅ correct name/version, editable location shown |

## 5. Canonical Start Command (for Runner Execution Contract, P1)

```bash
uvicorn vir.api.routes:app --host 0.0.0.0 --port 8000
```

## 6. Minimal Health Verification (for Runner Execution Contract, P1)

```
GET /health  →  200 {"status": "ok", "version": "0.1.0"}
```
Already implemented in `src/vir/api/routes.py`. No changes needed for P0.

## 7. Known Endpoints Still Returning 501 (unchanged, out of P0 scope)

- `POST /v1/vehicle-identities/{resolution_id}/clarifications`
- `GET /v1/vehicle-identities/{resolution_id}`
- `GET /v1/vehicle-identities/{resolution_id}/handoff/diagnostic`

These require a persistent store (P-later: Persistence). Not touched in P0.

## 8. Explicitly Out of Scope for This Session

- No business logic changed
- No RGG / RGM work
- No provider adapter changes
- No web UI / User Interaction Contract work
- No persistence added

## 9. Result

✅ Executability baseline established. `install → test → start → health` works
end-to-end with zero manual environment manipulation, in a fresh virtual
environment, verified twice (from project root and from an unrelated cwd).
This baseline is the foundation P1 (Runner Execution Contract) can now be
written against — as facts, not intentions.
