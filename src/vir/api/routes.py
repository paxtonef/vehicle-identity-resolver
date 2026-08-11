from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from vir.domain.errors import VIRBaseError
from vir.domain.models import (
    VehicleIdentityRequest,
    VehicleIdentityResolution,
    ClarificationRequest,
)
from vir.application.resolve_vehicle import ResolveVehicleUseCase
from vir.application.clarify_resolution import ClarifyResolutionUseCase
from vir.application.build_handoff import HandoffBuilder
from vir.provider_registry import build_providers


# Wire up providers from the Provider Registry (single source of truth —
# see src/vir/resources/provider_registry.yaml). Previously hardcoded here
# and duplicated in cli/main.py; the two could silently drift apart.
_DEFAULT_PROVIDERS = build_providers()

app = FastAPI(
    title="Vehicle Identity Resolver",
    version="0.1.0",
    description="AMD Development Pack v0.1 — Resolve vehicle identifiers to canonical identities",
)


@app.exception_handler(VIRBaseError)
async def vir_exception_handler(_, exc: VIRBaseError):
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "recoverable": exc.http_status in (409, 422, 429, 503),
        },
    )


@app.post("/v1/vehicle-identities/resolve", response_model=VehicleIdentityResolution)
async def resolve_vehicle(request: VehicleIdentityRequest):
    use_case = ResolveVehicleUseCase(providers=_DEFAULT_PROVIDERS)
    try:
        return await use_case.execute(request)
    except VIRBaseError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/vehicle-identities/{resolution_id}/clarifications", response_model=VehicleIdentityResolution)
async def submit_clarifications(resolution_id: str, request: ClarificationRequest):
    # In production, retrieve the original resolution from a store
    # For v0.1, clarification requires the client to resubmit enriched input
    raise HTTPException(
        status_code=501,
        detail="Clarification with stored resolution not yet implemented in v0.1. Use resolve endpoint with enriched input.",
    )


@app.get("/v1/vehicle-identities/{resolution_id}", response_model=VehicleIdentityResolution)
async def get_resolution(resolution_id: str):
    # In production, retrieve from persistent store
    raise HTTPException(status_code=501, detail="Resolution retrieval not yet implemented in v0.1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/v1/vehicle-identities/{resolution_id}/handoff/diagnostic")
async def get_diagnostic_handoff(resolution_id: str):
    # In production, fetch resolution then build handoff
    raise HTTPException(status_code=501, detail="Handoff retrieval not yet implemented in v0.1")
