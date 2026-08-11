"""Persistence wiring — the single place that knows which concrete
PersistencePort implementation is in use.

Architecture (yours): Core and API depend only on
vir.ports.persistence_port.PersistencePort. Today's implementation is
SQLite. A future PostgreSQLAdapter can replace the line below without
touching api/routes.py, web/routes.py, or any use case — that's the whole
point of the port/adapter split.

    PersistencePort
          |
          +-- SQLitePersistenceAdapter    <- now
          +-- PostgreSQLAdapter           <- later, not yet implemented
"""
from __future__ import annotations

from vir.config import settings
from vir.ports.persistence_port import PersistencePort, PersistenceError
from vir.adapters.sqlite_persistence_adapter import SQLitePersistenceAdapter

__all__ = ["STORE", "PersistencePort", "PersistenceError"]

# Eager singleton, schema created at import time — consistent with the
# "must be ready before serving requests" discipline used for config
# (P0.1), governance (P4), and the provider registry (P5).
STORE: PersistencePort = SQLitePersistenceAdapter(settings.vir_database_path)
