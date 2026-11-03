"""Test-suite safety net.

These tests create and delete rows in the live schema. They must never run against a department's
real database, so the suite refuses to start unless the configured MySQL database is clearly a test
database (its name contains "test"). Point the suite at one with, for example:

    MYSQL_HOST=127.0.0.1 MYSQL_PORT=3399 MYSQL_USER=caseweave MYSQL_PASSWORD=... MYSQL_DATABASE=caseweave_test
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_sessionstart(session):
    from secrets_store import get_secret

    name = (get_secret("MYSQL_DATABASE") or "caseweave").lower()
    if "test" not in name and os.environ.get("CASEWEAVE_ALLOW_TESTS_ON_REAL_DB") != "1":
        pytest.exit(
            f"Refusing to run: MYSQL_DATABASE is '{name}', which does not look like a test database. "
            "Set MYSQL_DATABASE to a throwaway database whose name contains 'test'.",
            returncode=2,
        )
