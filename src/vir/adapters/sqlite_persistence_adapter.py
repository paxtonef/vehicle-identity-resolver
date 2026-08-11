"""SQLitePersistenceAdapter — the current PersistencePort implementation.

Scope decision (yours): SQLite for this first productisable version — real
persistence, real transactions, real schema, zero external service,
straightforward local/web demo and automated testing. PostgreSQL is the
likely target once the runner operates at scale, but introducing it now
would add an infrastructure dependency before the persistence *model*
itself is stabilized. This adapter exists precisely so that migration is a
new adapter, not a rewrite: Core and API depend on
`vir.ports.persistence_port.PersistencePort`, never on this class directly.

What this stores: resolution_id, the request as received at the API/Web
boundary (see note below on normalization), the current resolution result,
and timestamps. No raw provider payload (see PersistencePort's docstring).

Normalization note: `ResolutionEngine._normalize_identifiers()` performs
per-field normalization (uppercasing, dash cleanup) internally, on a copy
of the request, and does not return it — only the resulting resolution.
What is persisted here is the request *as received* by the API/Web layer,
before that internal step. This is a real, stated scope boundary, not an
oversight: exposing the internally-normalized request would require a
small change to ResolutionEngine's return contract, which is a Core change
and out of scope for this persistence-architecture pass.
"""
from __future__ import annotations

import sqlite3

from vir.domain.models import VehicleIdentityRequest, VehicleIdentityResolution
from vir.ports.persistence_port import PersistencePort, PersistenceError


class SQLitePersistenceAdapter(PersistencePort):
    """SQLite-backed implementation. Freely instantiable (not just a module
    singleton) so tests can use an isolated path or ':memory:'."""

    def __init__(self, database_path: str):
        self.database_path = database_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self.database_path)
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Could not open database at '{self.database_path}': {exc}"
            ) from exc

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resolutions (
                    resolution_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    resolution_json TEXT NOT NULL
                )
                """
            )
            conn.commit()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not create schema: {exc}") from exc
        finally:
            conn.close()

    def save_resolution(
        self, request: VehicleIdentityRequest, resolution: VehicleIdentityResolution
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO resolutions
                    (resolution_id, request_id, created_at, request_json, resolution_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    resolution.resolution_id,
                    resolution.request_id,
                    resolution.created_at.isoformat(),
                    request.model_dump_json(),
                    resolution.model_dump_json(),
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Could not save resolution '{resolution.resolution_id}': {exc}"
            ) from exc
        finally:
            conn.close()

    def get_resolution(self, resolution_id: str) -> VehicleIdentityResolution | None:
        row = self._fetch_row(resolution_id)
        if row is None:
            return None
        return VehicleIdentityResolution.model_validate_json(row[1])

    def get_request(self, resolution_id: str) -> VehicleIdentityRequest | None:
        row = self._fetch_row(resolution_id)
        if row is None:
            return None
        return VehicleIdentityRequest.model_validate_json(row[0])

    def _fetch_row(self, resolution_id: str) -> tuple[str, str] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT request_json, resolution_json FROM resolutions WHERE resolution_id = ?",
                (resolution_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Could not read resolution '{resolution_id}': {exc}"
            ) from exc
        finally:
            conn.close()
        return row
