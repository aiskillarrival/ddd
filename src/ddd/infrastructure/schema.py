"""SQL schema for the personal investment application.

The table design follows a relational mapping of the aggregate:

* ``portfolios`` holds the aggregate-root state (identity + cash balance).
* ``holdings`` holds the child entities, keyed by portfolio and ticker.
* ``domain_events`` is an append-only event log (nice for auditing and
  for demonstrating that domain events are first-class).

Money is stored as an integer number of *minor units* (pence/cents) to
avoid floating-point rounding errors. Quantities are stored as text and
loaded as ``Decimal`` so that fractional shares survive round-trips.
"""

from __future__ import annotations

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS portfolios (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        currency      TEXT NOT NULL,
        cash_minor    INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS holdings (
        portfolio_id  TEXT NOT NULL,
        ticker        TEXT NOT NULL,
        quantity      TEXT NOT NULL,
        cost_minor    INTEGER NOT NULL,
        PRIMARY KEY (portfolio_id, ticker),
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS domain_events (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_id  TEXT NOT NULL,
        event_type    TEXT NOT NULL,
        payload       TEXT NOT NULL,
        occurred_at   TEXT NOT NULL,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
    )
    """,
)


def initialise_schema(connection) -> None:
    """Create the schema if it does not already exist."""
    with connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
