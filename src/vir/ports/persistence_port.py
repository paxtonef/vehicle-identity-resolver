from __future__ import annotations

from abc import ABC, abstractmethod

from vir.domain.models import VehicleIdentityRequest, VehicleIdentityResolution


class PersistenceError(RuntimeError):
    """Raised for genuine persistence failures (e.g. the backing store
    cannot be opened or written) — not used for a normal "not found" case,
    which is an expected, valid outcome the caller handles directly.

    Part of the port's contract: every PersistencePort implementation
    raises this same exception type for failures, so callers (Core, API,
    Web) never need to know which concrete adapter (SQLite today,
    PostgreSQL later) is behind the port."""


class PersistencePort(ABC):
    """Abstract port for resolution persistence.

    Core and API code depend only on this interface, never on a concrete
    backing store. Today's implementation is SQLite
    (vir.adapters.sqlite_persistence_adapter.SQLitePersistenceAdapter). A
    PostgreSQL (or other) adapter can be introduced later — for scale, for
    real concurrency, for migrations — by implementing this same port and
    changing only the wiring in vir.persistence, with no change to any
    caller.

    What is persisted (per the User Interaction Contract's scope): the
    resolution_id, the request as received (normalization detail: this is
    the request at the API/Web boundary, before ResolutionEngine's
    internal per-field normalization — see SQLitePersistenceAdapter's
    docstring), the current resolution result (status, confidence,
    evidence, clarification questions, contradictions), and timestamps.
    No raw provider payload is ever persisted — that policy
    (RUNTIME_GOVERNANCE_MANIFEST.md's data_export.raw_provider_payload)
    remains dormant, since nothing in the current adapter layer produces a
    raw payload to begin with.
    """

    @abstractmethod
    def save_resolution(
        self, request: VehicleIdentityRequest, resolution: VehicleIdentityResolution
    ) -> None:
        """Persist a resolution together with the request that produced it."""
        ...

    @abstractmethod
    def get_resolution(self, resolution_id: str) -> VehicleIdentityResolution | None:
        """Fetch a previously persisted resolution, or None if not found."""
        ...

    @abstractmethod
    def get_request(self, resolution_id: str) -> VehicleIdentityRequest | None:
        """Fetch the request that produced a previously persisted
        resolution, or None if not found."""
        ...
