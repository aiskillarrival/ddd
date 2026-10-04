"""Shared pytest fixtures for the DDD investment example."""

from __future__ import annotations

import sqlite3

import pytest

from ddd.application.service import PortfolioService
from ddd.infrastructure.sqlite_repository import SqlitePortfolioRepository


@pytest.fixture()
def connection() -> sqlite3.Connection:
    """A fresh in-memory SQLite database per test."""
    conn = sqlite3.connect(":memory:")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def repository(connection: sqlite3.Connection) -> SqlitePortfolioRepository:
    return SqlitePortfolioRepository(connection)


@pytest.fixture()
def service(repository: SqlitePortfolioRepository) -> PortfolioService:
    return PortfolioService(repository)
