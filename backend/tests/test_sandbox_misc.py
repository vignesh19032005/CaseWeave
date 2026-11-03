"""Database migrations and run-to-run reproducibility measurement."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from pipeline import sandbox_geometry as geo  # noqa: E402


class _Cur:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    """Just enough of a database to see which statements a migration issues."""

    def __init__(self, tables, applied=()):
        self.tables, self.applied, self.executed, self.commits = set(tables), set(applied), [], 0

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        s = " ".join(sql.split())
        if s.startswith("SELECT COUNT(*) AS n FROM information_schema.tables"):
            return _Cur([{"n": 1 if params[0] in self.tables else 0}])
        if s.startswith("SELECT name FROM schema_migrations"):
            return _Cur([{"name": n} for n in self.applied])
        if s.startswith("RENAME TABLE"):
            old, new = s.split()[2], s.split()[4]
            self.tables.discard(old)
            self.tables.add(new)
        if s.startswith("INSERT INTO schema_migrations"):
            self.applied.add(params[0])
        return _Cur([])

    def commit(self):
        self.commits += 1


def renames(conn):
    return [" ".join(s.split()) for s, _ in conn.executed if s.strip().startswith("RENAME TABLE")]


def test_migration_renames_old_tables_and_never_drops_them():
    conn = FakeConn({"case_sandbox_scenarios", "case_sandbox_layout", "cases"})
    db._migration_001_retire_unversioned_sandbox_tables(conn)
    assert renames(conn) == ["RENAME TABLE case_sandbox_scenarios TO legacy_case_sandbox_scenarios", "RENAME TABLE case_sandbox_layout TO legacy_case_sandbox_layout"]
    assert not any("DROP" in s.upper() for s, _ in conn.executed), "old data is renamed, never dropped"
    assert conn.tables == {"legacy_case_sandbox_scenarios", "legacy_case_sandbox_layout", "cases"}


def test_migration_is_safe_on_fresh_and_already_migrated_databases():
    fresh = FakeConn({"cases"})
    db._migration_001_retire_unversioned_sandbox_tables(fresh)
    assert renames(fresh) == []
    both = FakeConn({"case_sandbox_scenarios", "legacy_case_sandbox_scenarios"})
    db._migration_001_retire_unversioned_sandbox_tables(both)
    assert renames(both) == [], "never overwrites an existing legacy copy"


def test_each_migration_runs_once_and_is_recorded():
    conn = FakeConn({"case_sandbox_layout"})
    db._run_migrations(conn)
    assert "001_retire_unversioned_sandbox_tables" in conn.applied and len(renames(conn)) == 1
    before = len(conn.executed)
    db._run_migrations(conn)
    assert len(renames(conn)) == 1 and all("RENAME" not in s for s, _ in conn.executed[before:]), "a recorded migration is not repeated"


def test_schema_has_the_versioned_tables_and_utf8():
    text = " ".join(db.SCHEMA_STATEMENTS)
    for t in ("sandbox_runs", "sandbox_scenarios", "case_narratives", "schema_migrations"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" in text
    assert "utf8mb4" in text and "case_sandbox_layout" not in text


# ---------------------------------------------------------------- reproducibility measure

def lay(width=10, extra_fixture=False, state="forced"):
    raw = {"rooms": [{"id": "a", "width_m": width, "length_m": 8}],
           "entry_points": [{"id": "rear", "room": "a", "wall": "north", "position_frac": 0.5, "width_m": 1.2, "state": state}],
           "fixtures": [{"id": "counter", "room": "a", "position_frac": [0.5, 0.5], "footprint_m": [2, 1]}]}
    if extra_fixture:
        raw["fixtures"].append({"id": "shelf", "room": "a", "position_frac": [0.1, 0.1], "footprint_m": [1, 0.5]})
    return geo.build_layout(raw, set())


def test_identical_layouts_are_fully_similar():
    s = geo.layout_similarity(lay(), lay())
    assert s["score"] == 1.0 and s["within_tolerance"]


def test_different_reading_of_the_same_evidence_is_measured():
    s = geo.layout_similarity(lay(), lay(width=14, extra_fixture=True, state="intact"))
    assert s["score"] < 0.9 and s["parts"]["door_conditions"] == 0.0 and s["parts"]["furniture"] == 0.5
    far = geo.layout_similarity(lay(), lay(width=30, extra_fixture=True, state="intact"))
    assert far["score"] < s["score"] and not far["within_tolerance"]
