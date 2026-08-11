"""Web Product Layer routes — server-rendered HTML, no JS framework.

Wraps the same use cases the JSON API uses (ResolveVehicleUseCase,
ClarifyResolutionUseCase) and the same Persistence store — this is a
presentation layer, not a second implementation of resolution logic.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from vir.domain.errors import VIRBaseError, ResolutionNotFoundError
from vir.domain.models import (
    VehicleIdentityRequest,
    RegistrationInput,
    ManualIdentityInput,
    ConsentInput,
    ClarificationAnswer,
)
from vir.domain.enums import ResolutionStatus, FuelType
from vir.application.resolve_vehicle import ResolveVehicleUseCase
from vir.application.clarify_resolution import ClarifyResolutionUseCase
from vir.provider_registry import build_providers
from vir.persistence import STORE

# Package-relative path (not project-root-relative) — must resolve the same
# way whether this runs from an editable install or a real installed wheel.
# See P0.1 for why this distinction matters: a path relative to the source
# tree silently breaks once the package is installed elsewhere.
_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()

_PROVIDERS = build_providers()

# Plain-language status labels/descriptions — mirrors
# USER_INTERACTION_CONTRACT.md section 2's table.
_STATUS_INFO: dict[ResolutionStatus, tuple[str, str]] = {
    ResolutionStatus.RESOLVED: (
        "Résolu",
        "Identité à haute confiance, exploitable en aval.",
    ),
    ResolutionStatus.PROVISIONALLY_RESOLVED: (
        "Résolu provisoirement",
        "Identité exploitable mais non totalement confirmée — à traiter comme un point de départ.",
    ),
    ResolutionStatus.AMBIGUOUS: (
        "Ambigu",
        "Plusieurs configurations correspondent aux informations fournies.",
    ),
    ResolutionStatus.INSUFFICIENT_DATA: (
        "Données insuffisantes",
        "Pas assez d'informations trouvées ou fournies pour identifier le véhicule.",
    ),
    ResolutionStatus.CONTRADICTORY: (
        "Contradictoire",
        "Les informations se contredisent — une clarification est nécessaire.",
    ),
    ResolutionStatus.UNSUPPORTED_COUNTRY: (
        "Pays non pris en charge",
        "Aucun fournisseur disponible pour ce pays d'immatriculation.",
    ),
    ResolutionStatus.PROVIDER_UNAVAILABLE: (
        "Source indisponible",
        "Une consultation externe a échoué — rien n'a été inventé pour compenser.",
    ),
    ResolutionStatus.INVALID_IDENTIFIER: (
        "Identifiant invalide",
        "L'identifiant fourni est mal formé.",
    ),
}


def _status_info(status: ResolutionStatus) -> tuple[str, str]:
    return _STATUS_INFO.get(status, (status.value, ""))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"form_values": {}, "error_message": None}
    )


def _build_request_from_form(form: dict) -> VehicleIdentityRequest:
    vin = (form.get("vin") or "").strip() or None

    registration_number = (form.get("registration_number") or "").strip() or None
    country_code = (form.get("country_code") or "FR").strip() or None

    manufacturer = (form.get("manufacturer") or "").strip() or None
    model = (form.get("model") or "").strip() or None
    production_year_raw = (form.get("production_year") or "").strip()
    production_year = int(production_year_raw) if production_year_raw else None
    fuel_type_raw = (form.get("fuel_type") or "").strip() or None
    fuel_type = FuelType(fuel_type_raw) if fuel_type_raw else None

    consent = form.get("consent") == "yes"

    return VehicleIdentityRequest(
        request_id=f"WEB-{__import__('uuid').uuid4().hex[:12].upper()}",
        vin=vin,
        registration=RegistrationInput(
            registration_number=registration_number,
            country_code=country_code if registration_number else None,
        ),
        manual_identity=ManualIdentityInput(
            manufacturer=manufacturer,
            model=model,
            production_year=production_year,
            fuel_type=fuel_type,
        ),
        consent=ConsentInput(external_lookup_allowed=consent),
    )


@router.post("/resolve", response_class=HTMLResponse)
async def resolve_form(request: Request):
    form = dict(await request.form())

    try:
        vir_request = _build_request_from_form(form)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"form_values": form, "error_message": f"Entrée invalide : {exc}"},
        )

    use_case = ResolveVehicleUseCase(providers=_PROVIDERS)
    try:
        resolution = await use_case.execute(vir_request)
    except VIRBaseError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"form_values": form, "error_message": exc.message},
        )

    STORE.save_resolution(vir_request, resolution)
    label, description = _status_info(resolution.resolution_status)
    return templates.TemplateResponse(
        request,
        "result.html",
        {"resolution": resolution, "status_label": label, "status_description": description},
    )


@router.post("/clarify/{resolution_id}", response_class=HTMLResponse)
async def clarify_form(request: Request, resolution_id: str):
    stored = STORE.get_resolution(resolution_id)
    if stored is None:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"form_values": {}, "error_message": f"Résolution introuvable : {resolution_id}"},
        )

    form = dict(await request.form())
    answers = [
        ClarificationAnswer(question_id=key[len("answer__"):], value=value)
        for key, value in form.items()
        if key.startswith("answer__") and value != ""
    ]

    use_case = ClarifyResolutionUseCase(providers=_PROVIDERS)
    try:
        enriched_request, new_resolution = await use_case.execute(stored, answers)
    except VIRBaseError as exc:
        label, description = _status_info(stored.resolution_status)
        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "resolution": stored,
                "status_label": label,
                "status_description": description,
                "error_message": exc.message,
            },
        )

    STORE.save_resolution(enriched_request, new_resolution)
    label, description = _status_info(new_resolution.resolution_status)
    return templates.TemplateResponse(
        request,
        "result.html",
        {"resolution": new_resolution, "status_label": label, "status_description": description},
    )
