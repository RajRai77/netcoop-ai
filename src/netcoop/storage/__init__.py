"""Evidence ledger persistence (repository contract + SQL implementation)."""

from netcoop.storage.engine import make_engine
from netcoop.storage.sql_store import SqlEvidenceStore


def open_store(url: str) -> SqlEvidenceStore:
    return SqlEvidenceStore(make_engine(url))


__all__ = ["SqlEvidenceStore", "make_engine", "open_store"]
