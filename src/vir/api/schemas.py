from __future__ import annotations

from vir.domain.models import (
    VehicleIdentityRequest,
    VehicleIdentityResolution,
    ClarificationRequest,
    DiagnosticIdentityContext,
)


# Re-export domain models for API layer
__all__ = [
    "VehicleIdentityRequest",
    "VehicleIdentityResolution",
    "ClarificationRequest",
    "DiagnosticIdentityContext",
]
