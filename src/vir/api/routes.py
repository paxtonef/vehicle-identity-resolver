from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from vir.domain.errors import VIRBaseError, ResolutionNotFoundError
from vir.domain.models import (
    VehicleIdentityRequest,
    VehicleIdentityResolution,
    ClarificationRequest,
    DiagnosticIdentityContext,
)
from vir.application.resolve_vehicle import ResolveVehicleUseCase
from vir.application.clarify_resolution import ClarifyResolutionUseCase
from vir.application.build_handoff import HandoffBuilder
from vir.provider_registry import build_providers
from vir.persistence import STORE
from vir.web.routes import router as web_router


# Wire up providers from the Provider Registry (single source of truth —
# see src/vir/resources/provider_registry.yaml). Previously hardcoded here
# and duplicated in cli/main.py; the two could silently drift apart.
_DEFAULT_PROVIDERS = build_providers()

app = FastAPI(
    title="Vehicle Identity Resolver",
    version="0.1.0",
    description="AMD Development Pack v0.1 — Resolve vehicle identifiers to canonical identities",
)

app.include_router(web_router)


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
        resolution = await use_case.execute(request)
    except VIRBaseError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    STORE.save_resolution(request, resolution)
    return resolution


@app.post("/v1/vehicle-identities/{resolution_id}/clarifications", response_model=VehicleIdentityResolution)
async def submit_clarifications(resolution_id: str, request: ClarificationRequest):
    stored_resolution = STORE.get_resolution(resolution_id)
    stored_request = STORE.get_request(resolution_id)
    if stored_resolution is None or stored_request is None:
        raise ResolutionNotFoundError(resolution_id)

    use_case = ClarifyResolutionUseCase(providers=_DEFAULT_PROVIDERS)
    try:
        enriched_request, new_resolution = await use_case.execute(
            stored_request, stored_resolution, request.answers
        )
    except VIRBaseError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    STORE.save_resolution(enriched_request, new_resolution)
    return new_resolution


@app.get("/v1/vehicle-identities/{resolution_id}", response_model=VehicleIdentityResolution)
async def get_resolution(resolution_id: str):
    resolution = STORE.get_resolution(resolution_id)
    if resolution is None:
        raise ResolutionNotFoundError(resolution_id)
    return resolution


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get(
    "/v1/vehicle-identities/{resolution_id}/handoff/diagnostic",
    response_model=DiagnosticIdentityContext,
)
async def get_diagnostic_handoff(resolution_id: str):
    resolution = STORE.get_resolution(resolution_id)
    if resolution is None:
        raise ResolutionNotFoundError(resolution_id)
    return HandoffBuilder.build_diagnostic_context(resolution)
