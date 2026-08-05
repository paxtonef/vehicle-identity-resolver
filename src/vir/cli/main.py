#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import yaml

from vir.domain.models import VehicleIdentityRequest, ManualIdentityInput, ConsentInput, RegistrationInput
from vir.application.resolve_vehicle import ResolveVehicleUseCase
from vir.application.build_handoff import HandoffBuilder
from vir.adapters.manual_adapter import ManualAdapter
from vir.adapters.registration_provider_adapter import FrenchRegistrationProviderAdapter
from vir.adapters.vin_decoder_adapter import VINDecoderAdapter


_DEFAULT_PROVIDERS = [
    ManualAdapter(),
    FrenchRegistrationProviderAdapter(),
    VINDecoderAdapter(),
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vir",
        description="Vehicle Identity Resolver CLI v0.1",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # resolve
    resolve = subparsers.add_parser("resolve", help="Resolve a vehicle identity")
    resolve.add_argument("--registration", type=str, default=None, help="Registration number")
    resolve.add_argument("--country", type=str, default="FR", help="Registration country code")
    resolve.add_argument("--vin", type=str, default=None, help="Vehicle Identification Number")
    resolve.add_argument("--manufacturer", type=str, default=None)
    resolve.add_argument("--model", type=str, default=None)
    resolve.add_argument("--year", type=int, default=None)
    resolve.add_argument("--fuel", type=str, default=None)
    resolve.add_argument("--displacement", type=int, default=None)
    resolve.add_argument("--power", type=float, default=None)
    resolve.add_argument("--transmission", type=str, default=None)
    resolve.add_argument("--json-input", type=str, default=None, help="Raw JSON request file")
    resolve.add_argument("--output", choices=["human", "json", "yaml", "compact"], default="human")
    resolve.add_argument("--no-external", action="store_true", help="Disable external lookups")

    # handoff
    handoff = subparsers.add_parser("handoff", help="Build diagnostic handoff from a resolution JSON")
    handoff.add_argument("resolution_file", type=str, help="Path to resolution JSON file")

    return parser


def _build_request(args: argparse.Namespace) -> VehicleIdentityRequest:
    if args.json_input:
        with open(args.json_input) as f:
            data = json.load(f)
        return VehicleIdentityRequest(**data)

    return VehicleIdentityRequest(
        request_id="CLI-REQUEST-001",
        locale="fr-FR",
        registration=RegistrationInput(
            registration_number=args.registration,
            country_code=args.country,
        ),
        vin=args.vin,
        manual_identity=ManualIdentityInput(
            manufacturer=args.manufacturer,
            model=args.model,
            production_year=args.year,
            fuel_type=args.fuel,
            engine_displacement_cc=args.displacement,
            engine_power_kw=args.power,
            transmission_type=args.transmission,
        ),
        consent=ConsentInput(external_lookup_allowed=not args.no_external),
    )


def _render_human(resolution: Any) -> str:
    lines = [
        "==============================================================",
        "           VEHICLE IDENTITY RESOLUTION RESULT                 ",
        "==============================================================",
        "",
        f"Resolution ID : {resolution.resolution_id}",
        f"Status        : {resolution.resolution_status.value}",
        f"Confidence    : {resolution.confidence.score:.2f} ({resolution.confidence.level.value})",
        "",
    ]

    if resolution.vehicle_identity:
        v = resolution.vehicle_identity
        lines.extend([
            "- Canonical Identity -",
            f"  Manufacturer : {v.manufacturer or '-'}",
            f"  Model        : {v.model or '-'}",
            f"  Generation   : {v.generation or '-'}",
            f"  Year         : {v.production.year or '-'}",
            f"  Body         : {v.body.type.value if v.body.type else '-'}",
            f"  Fuel         : {v.fuel.primary_type.value if v.fuel.primary_type else '-'}",
            f"  Engine       : {v.engine.commercial_name or '-'}",
            f"    Power      : {v.engine.power_kw or '-'} kW",
            f"    Disp.      : {v.engine.displacement_cc or '-'} cc",
            f"  Transmission : {v.transmission.type.value if v.transmission.type else '-'}",
            f"  VIN          : {v.identifiers.vin or '-'}",
            f"  Plate        : {v.identifiers.registration_number or '-'}",
            "",
        ])

    if resolution.unresolved_fields:
        lines.append("- Unresolved Fields -")
        for f in resolution.unresolved_fields:
            lines.append(f"  - {f}")
        lines.append("")

    if resolution.contradictions:
        lines.append("- Contradictions Detected -")
        for c in resolution.contradictions:
            vals = " vs ".join(str(v.value) for v in c.values)
            lines.append(f"  - {c.field_path}: {vals} [{c.severity}]")
        lines.append("")

    if resolution.clarification_questions:
        lines.append("- Clarification Needed -")
        for q in resolution.clarification_questions:
            lines.append(f"  [{q.question_id}] {q.prompt}")
            if q.choices:
                for ch in q.choices:
                    lines.append(f"      - {ch.label}")
        lines.append("")

    if resolution.limitations:
        lines.append("- Limitations -")
        for lim in resolution.limitations:
            lines.append(f"  - {lim}")
        lines.append("")

    lines.append(f"Sources: {len(resolution.source_summary)} provider(s) consulted")
    return "\n".join(lines)


def _render_compact(resolution: Any) -> str:
    v = resolution.vehicle_identity
    if not v:
        return f"{resolution.resolution_status.value}|{resolution.confidence.score:.2f}|NONE"
    return (
        f"{resolution.resolution_status.value}|"
        f"{resolution.confidence.score:.2f}|"
        f"{v.manufacturer or ''}|{v.model or ''}|{v.production.year or ''}|"
        f"{v.fuel.primary_type.value if v.fuel.primary_type else ''}"
    )


async def _cmd_resolve(args: argparse.Namespace) -> int:
    request = _build_request(args)
    use_case = ResolveVehicleUseCase(providers=_DEFAULT_PROVIDERS)
    resolution = await use_case.execute(request)

    if args.output == "json":
        print(resolution.model_dump_json(indent=2))
    elif args.output == "yaml":
        print(yaml.safe_dump(resolution.model_dump(mode="json"), allow_unicode=True, sort_keys=False))
    elif args.output == "compact":
        print(_render_compact(resolution))
    else:
        print(_render_human(resolution))

    return 0


async def _cmd_handoff(args: argparse.Namespace) -> int:
    import os
    if not os.path.exists(args.resolution_file):
        print(f"Error: file not found: {args.resolution_file}", file=sys.stderr)
        return 1

    with open(args.resolution_file) as f:
        data = json.load(f)

    from vir.domain.models import VehicleIdentityResolution
    resolution = VehicleIdentityResolution(**data)
    handoff = HandoffBuilder.build_diagnostic_context(resolution)
    print(handoff.model_dump_json(indent=2))
    return 0


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "resolve":
        return await _cmd_resolve(args)
    elif args.command == "handoff":
        return await _cmd_handoff(args)

    return 0


def run() -> None:
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    run()
