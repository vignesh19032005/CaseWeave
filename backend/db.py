"""
Stage 20 — MySQL (not SQLite). Real concurrent-writer-safe database instead
of SQLite's single-writer lock, which was fine for one demo case, not for
a department running multiple investigations at once.

Connects to an isolated Docker MySQL instance (caseweave-mysql container,
port 3307) — does not touch this machine's native MySQL80 service or its
root account at all. Credentials come from secrets_store.py (Credential
Manager), same pattern as the LLM API keys.

Compatibility layer: get_conn() returns a thin wrapper exposing .execute()
directly on the connection (like sqlite3 did) and dict-style row access
(row["col"]), so every other file in the codebase (api.py, auth.py,
pipeline/*.py) needed ZERO changes — same interface, different engine
underneath.
"""
import datetime as _dt
import hashlib
import hmac
import json
import os
import re

import pymysql
import pymysql.cursors

from secrets_store import get_or_create_secret, get_secret


def utcnow() -> _dt.datetime:
    """Naive UTC "now" (the format every timestamp column already uses) without the deprecated utcnow()."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _mysql_config() -> dict:
    return {
        "host": get_secret("MYSQL_HOST") or "127.0.0.1",
        "port": int(get_secret("MYSQL_PORT") or 3307),
        "user": get_secret("MYSQL_USER") or "caseweave",
        "password": get_secret("MYSQL_PASSWORD"),
        "database": get_secret("MYSQL_DATABASE") or "caseweave",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
        "charset": "utf8mb4",
    }


SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS cases (
        case_id VARCHAR(64) PRIMARY KEY,
        title TEXT,
        created_at VARCHAR(64)
    )""",
    """CREATE TABLE IF NOT EXISTS evidence_items (
        evidence_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        filename TEXT,
        file_hash VARCHAR(128),
        evidence_type VARCHAR(32),
        status VARCHAR(32),
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS observations (
        observation_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        description TEXT,
        classification VARCHAR(32),
        source_evidence_id VARCHAR(64),
        source_locator TEXT,
        extracted_time VARCHAR(32),
        limitations TEXT,
        subject TEXT,
        action TEXT,
        location TEXT,
        time_claim TEXT,
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS entities (
        entity_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        canonical_name TEXT,
        entity_type VARCHAR(32),
        aliases TEXT,
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS entity_mentions (
        mention_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        entity_id VARCHAR(64),
        observation_id VARCHAR(64),
        mention_text TEXT,
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS relationships (
        relationship_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        from_entity_id VARCHAR(64),
        to_entity_id VARCHAR(64),
        relationship_type VARCHAR(255),
        source_observation_id VARCHAR(64),
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        user_id VARCHAR(64) PRIMARY KEY,
        username VARCHAR(128) UNIQUE,
        password_hash VARCHAR(128),
        role VARCHAR(32),
        created_at VARCHAR(64),
        must_change_password TINYINT NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS timeline_events (
        event_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        event_time VARCHAR(32),
        description TEXT,
        source_observation_id VARCHAR(64),
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS conflicts (
        conflict_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        claim_a TEXT,
        source_a VARCHAR(64),
        time_a VARCHAR(32),
        claim_b TEXT,
        source_b VARCHAR(64),
        time_b VARCHAR(32),
        question TEXT,
        nature_of_conflict TEXT,
        transcript TEXT,
        review_status VARCHAR(32) DEFAULT 'unresolved',
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS evidence_links (
        link_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        claim_a TEXT,
        source_a VARCHAR(64),
        claim_b TEXT,
        source_b VARCHAR(64),
        link_type VARCHAR(32),
        reason TEXT,
        transcript TEXT,
        INDEX (case_id)
    )""",
    """CREATE TABLE IF NOT EXISTS conflict_reviews (
        review_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64),
        conflict_id VARCHAR(64),
        status VARCHAR(32),
        reason TEXT,
        actor_username VARCHAR(128),
        actor_role VARCHAR(32),
        timestamp VARCHAR(64),
        INDEX (conflict_id)
    )""",
    """CREATE TABLE IF NOT EXISTS audit_events (
        audit_id VARCHAR(255) PRIMARY KEY,
        case_id VARCHAR(64),
        actor_role VARCHAR(32),
        action VARCHAR(128),
        target VARCHAR(128),
        timestamp VARCHAR(64),
        prev_hash VARCHAR(128),
        this_hash VARCHAR(128),
        actor_user VARCHAR(128) NULL,
        hash_version INT NOT NULL DEFAULT 1,
        INDEX (case_id),
        INDEX (timestamp),
        INDEX idx_audit_case_ts (case_id, timestamp)
    )""",
    """CREATE TABLE IF NOT EXISTS audit_heads (
        case_id VARCHAR(64) PRIMARY KEY,
        head_hash VARCHAR(128) NOT NULL,
        event_count INT NOT NULL,
        updated_at VARCHAR(40)
    )""",
    """CREATE TABLE IF NOT EXISTS case_signatures (
        case_id VARCHAR(64) PRIMARY KEY,
        crime_category VARCHAR(64),
        point_of_entry VARCHAR(128),
        tools_used VARCHAR(255),
        target_goods VARCHAR(255),
        timing_window VARCHAR(64),
        suspect_count INT DEFAULT 1,
        signature_traits TEXT,
        mo_summary TEXT,
        synthesis_json LONGTEXT,
        matches_json LONGTEXT,
        computed_at VARCHAR(64),
        created_at VARCHAR(64)
    )""",
<<<<<<< HEAD
    """CREATE TABLE IF NOT EXISTS case_simulations (
        case_id VARCHAR(64) PRIMARY KEY,
        frames_json LONGTEXT,
        trajectory_json LONGTEXT,
        scene_config_json LONGTEXT,
        telemetry_json LONGTEXT,
        computed_at VARCHAR(64),
        created_at VARCHAR(64)
=======
    """CREATE TABLE IF NOT EXISTS sandbox_runs (
        run_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        is_current TINYINT NOT NULL DEFAULT 0,
        schema_version INT NOT NULL,
        mode VARCHAR(24),
        evidence_hash VARCHAR(64),
        layout_json LONGTEXT,
        layout_hash VARCHAR(64),
        assessment_json LONGTEXT,
        evidence_index_json LONGTEXT,
        generation_meta_json LONGTEXT,
        status_message TEXT,
        approved_by VARCHAR(128),
        approved_at VARCHAR(40),
        created_by VARCHAR(128),
        created_at VARCHAR(40),
        completed_at VARCHAR(40),
        INDEX (case_id),
        INDEX (case_id, is_current)
    ) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS sandbox_scenarios (
        scenario_id VARCHAR(64) PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL,
        case_id VARCHAR(64) NOT NULL,
        scenario_type VARCHAR(24) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'active',
        rank_order INT,
        content_json LONGTEXT,
        content_hash VARCHAR(64),
        interview_json LONGTEXT,
        created_by VARCHAR(128),
        created_at VARCHAR(40),
        retracted_by VARCHAR(128),
        retracted_at VARCHAR(40),
        retracted_reason TEXT,
        INDEX (run_id),
        INDEX (case_id)
    ) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS case_narratives (
        narrative_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64) NOT NULL,
        evidence_hash VARCHAR(64),
        content_json LONGTEXT,
        content_hash VARCHAR(64),
        created_by VARCHAR(128),
        created_at VARCHAR(40),
        INDEX (case_id)
    ) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS sandbox_photo_links (
        link_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64) NOT NULL,
        run_id VARCHAR(64),
        layout_hash VARCHAR(64),
        content_json LONGTEXT,
        content_hash VARCHAR(64),
        created_by VARCHAR(128),
        created_at VARCHAR(40),
        INDEX (case_id)
    ) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS sandbox_reviews (
        review_id VARCHAR(64) PRIMARY KEY,
        case_id VARCHAR(64) NOT NULL,
        run_id VARCHAR(64),
        layout_hash VARCHAR(64),
        status VARCHAR(16),
        message VARCHAR(500),
        content_json LONGTEXT,
        content_hash VARCHAR(64),
        created_by VARCHAR(128),
        created_at VARCHAR(40),
        completed_at VARCHAR(40),
        INDEX (case_id)
    ) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS schema_migrations (
        name VARCHAR(80) PRIMARY KEY,
        applied_at VARCHAR(40)
>>>>>>> feature/investigative-sandbox
    )""",
]


def _translate_sql(sql: str) -> str:
    """Translates sqlite-isms to MySQL dialect so every call site elsewhere
    in the codebase keeps working unchanged: '?' placeholders -> '%s' (only outside quoted
    string literals, so a '?' inside text is left alone), and 'INSERT OR REPLACE INTO' ->
    MySQL's 'REPLACE INTO' (no 'OR' in MySQL's grammar)."""
    sql = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "REPLACE INTO", sql, flags=re.IGNORECASE)
    out, quote = [], ""
    for ch in sql:
        if quote:
            if ch == quote:
                quote = ""
            out.append(ch)
        elif ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
        elif ch == "?":
            out.append("%s")
        else:
            out.append(ch)
    return "".join(out)


class _CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        self._cursor.execute(_translate_sql(sql), params)
        return self

    def executescript(self, sql):
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                self._cursor.execute(statement)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _ConnWrapper:
    """Mimics sqlite3.Connection's interface: .execute() directly on the
    connection, .cursor() for an explicit cursor, dict-style row access."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is not None:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(_translate_sql(sql), params)
        return _CursorWrapper(cur)

    def executescript(self, sql):
        cur = self._conn.cursor()
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                cur.execute(statement)

    def cursor(self):
        return _CursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_conn() -> _ConnWrapper:
    raw = pymysql.connect(**_mysql_config())
    return _ConnWrapper(raw)


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = ?", (name,)
    ).fetchone()
    return bool(row and row["n"])


def _migration_001_retire_unversioned_sandbox_tables(conn):
    """The first sandbox kept one overwritable row per case. Those tables
    held derived, regenerable data in an older shape, so they are renamed
    (not dropped) and the versioned tables take over."""
    for old in ("case_sandbox_scenarios", "case_sandbox_layout"):
        if _table_exists(conn, old) and not _table_exists(conn, f"legacy_{old}"):
            conn.execute(f"RENAME TABLE {old} TO legacy_{old}")


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
        (table, column),
    ).fetchone()
    return bool(row and row["n"])


def _index_exists(conn, table: str, index: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = ? AND index_name = ?",
        (table, index),
    ).fetchone()
    return bool(row and row["n"])


def _migration_002_users_must_change_password(conn):
    if not _column_exists(conn, "users", "must_change_password"):
        conn.execute("ALTER TABLE users ADD COLUMN must_change_password TINYINT NOT NULL DEFAULT 0")


def _migration_003_audit_actor_and_version(conn):
    if not _column_exists(conn, "audit_events", "actor_user"):
        conn.execute("ALTER TABLE audit_events ADD COLUMN actor_user VARCHAR(128) NULL")
    if not _column_exists(conn, "audit_events", "hash_version"):
        conn.execute("ALTER TABLE audit_events ADD COLUMN hash_version INT NOT NULL DEFAULT 1")


def _migration_004_audit_case_timestamp_index(conn):
    if not _index_exists(conn, "audit_events", "idx_audit_case_ts"):
        conn.execute("CREATE INDEX idx_audit_case_ts ON audit_events (case_id, timestamp)")


def _migration_005_remove_seeded_fictional_cases(conn):
    """An earlier version wrote four fictional reference "cases" (CW-HIST-01..04) into the real cases table, where they showed
    up in every user's case list. They now live only in the pattern reference store, labelled synthetic. Only rows that still
    carry the exact seeded titles are removed, so a real case that happens to reuse an id is never touched."""
    seeded = {
        "CW-HIST-01": "Kilpauk Care Pharmacy Night Break-in",
        "CW-HIST-02": "Anna Nagar Apollo Pharmacy Rooftop Cut",
        "CW-HIST-03": "T. Nagar Kalyan Jewellers Showroom Sledgehammer Heist",
        "CW-HIST-04": "Vadapalani Diagnostic Center Storeroom Theft",
    }
    for case_id, title in seeded.items():
        conn.execute("DELETE FROM cases WHERE case_id=? AND title=?", (case_id, title))


MIGRATIONS = [
    ("001_retire_unversioned_sandbox_tables", _migration_001_retire_unversioned_sandbox_tables),
    ("002_users_must_change_password", _migration_002_users_must_change_password),
    ("003_audit_actor_and_version", _migration_003_audit_actor_and_version),
    ("004_audit_case_timestamp_index", _migration_004_audit_case_timestamp_index),
    ("005_remove_seeded_fictional_cases", _migration_005_remove_seeded_fictional_cases),
]


def _run_migrations(conn):
    applied = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    for name, fn in MIGRATIONS:
        if name in applied:
            continue
        fn(conn)
        conn.execute("INSERT INTO schema_migrations (name, applied_at) VALUES (?,?)", (name, utcnow().isoformat()))
        conn.commit()


def init_db():
    conn = get_conn()
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()
    _run_migrations(conn)
    conn.close()


def reset_db():
    """Drops and recreates every table. Test use only: it destroys users, cases and the audit trail, so it
    refuses to run unless the caller sets CASEWEAVE_ALLOW_DB_RESET=1 AND the configured database is clearly a
    test database (its name contains "test")."""
    name = (get_secret("MYSQL_DATABASE") or "caseweave").lower()
    if os.environ.get("CASEWEAVE_ALLOW_DB_RESET") != "1" or "test" not in name:
        raise RuntimeError(
            f"reset_db() refused: it deletes every case, user and audit record in database '{name}'. "
            "It only runs against a database whose name contains 'test' and with CASEWEAVE_ALLOW_DB_RESET=1."
        )
    conn = get_conn()
    conn.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in [
        "cases", "evidence_items", "observations", "entities", "entity_mentions",
        "relationships", "users", "timeline_events", "conflicts", "evidence_links",
        "conflict_reviews", "sandbox_scenarios", "sandbox_runs", "sandbox_photo_links", "sandbox_reviews",
        "case_narratives", "case_signatures", "schema_migrations", "audit_events", "audit_heads",
    ]:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    conn.close()
    init_db()


def file_hash(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------- audit trail ----
# Each event is chained to the one before it. Version 1 rows (older installs) used a plain SHA-256 over
# {prev_hash, action, target, timestamp}. Version 2 rows are an HMAC (keyed with a secret that is not stored in
# the database) over EVERY field including case, role and user, so editing any of them, or recomputing the
# chain without the key, is detected. audit_heads keeps the newest hash and the count per case, so deleting the
# most recent events is detected too.

AUDIT_V2 = 2


def _audit_key() -> bytes:
    return get_or_create_secret("AUDIT_HMAC_KEY").encode()


def _v1_hash(prev_hash, action, target, timestamp) -> str:
    payload = json.dumps({"prev_hash": prev_hash, "action": action, "target": target, "timestamp": timestamp}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _v2_hash(case_id, actor_role, actor_user, action, target, timestamp, prev_hash) -> str:
    payload = json.dumps(
        {"v": AUDIT_V2, "case_id": case_id, "actor_role": actor_role, "actor_user": actor_user or "", "action": action,
         "target": target, "timestamp": timestamp, "prev_hash": prev_hash},
        sort_keys=True,
    )
    return hmac.new(_audit_key(), payload.encode(), hashlib.sha256).hexdigest()


def _insert_audit(cur, case_id, actor_role, actor_user, action, target):
    """Reads the chain head and inserts the next event. The caller holds the per-case lock."""
    cur.execute("SELECT this_hash FROM audit_events WHERE case_id=? ORDER BY timestamp DESC LIMIT 1 FOR UPDATE", (case_id,))
    row = cur.fetchone()
    prev_hash = row["this_hash"] if row else "GENESIS"
    timestamp = utcnow().isoformat(timespec="microseconds")
    audit_id = f"audit_{case_id}_{timestamp}_{action}"[:255]
    this_hash = _v2_hash(case_id, actor_role, actor_user, action, target, timestamp, prev_hash)
    cur.execute(
        "INSERT INTO audit_events (audit_id, case_id, actor_role, action, target, timestamp, prev_hash, this_hash, actor_user, hash_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (audit_id, case_id, actor_role, action, target, timestamp, prev_hash, this_hash, actor_user, AUDIT_V2),
    )
    cur.execute("SELECT COUNT(*) AS n FROM audit_events WHERE case_id=?", (case_id,))
    count = cur.fetchone()["n"]
    cur.execute(
        "REPLACE INTO audit_heads (case_id, head_hash, event_count, updated_at) VALUES (?,?,?,?)",
        (case_id, this_hash, count, timestamp),
    )
    return this_hash


def append_audit_event(conn, case_id, actor_role, action, target, actor_user=None):
    cur = conn.cursor()
    # Serialize appends per case across processes (API + worker). Without
    # this, two concurrent writers read the same latest hash and both chain
    # off it, forking the chain so verify_audit_chain fails.
    lock_name = f"cw_audit_{case_id}"[:64]
    cur.execute("SELECT GET_LOCK(?, 10) AS got", (lock_name,))
    if not cur.fetchone()["got"]:
        raise RuntimeError(f"could not acquire audit lock for {case_id}")
    try:
        conn.commit()  # end any open snapshot so the read below sees the latest row
        this_hash = _insert_audit(cur, case_id, actor_role, actor_user, action, target)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
    return this_hash


def append_audit_event_txn(conn, case_id, actor_role, action, target, actor_user=None):
    """Appends an audit event inside the caller's open transaction.

    The event and the record it attests to are committed together or not at
    all. The per-case audit lock is taken here and held until the caller has
    committed (or rolled back) and calls the returned release function, so no
    other writer can fork the hash chain in between. Returns (this_hash, release).
    """
    cur = conn.cursor()
    lock_name = f"cw_audit_{case_id}"[:64]
    cur.execute("SELECT GET_LOCK(?, 10) AS got", (lock_name,))
    if not cur.fetchone()["got"]:
        raise RuntimeError(f"could not acquire audit lock for {case_id}")

    def release():
        try:
            cur2 = conn.cursor()
            cur2.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
        except Exception:  # noqa: BLE001 - connection already closed
            pass

    try:
        this_hash = _insert_audit(cur, case_id, actor_role, actor_user, action, target)
    except Exception:
        release()
        raise
    return this_hash, release


def verify_audit_chain_detail(conn, case_id) -> dict:
    """{"ok": bool, "events": n, "reason": str}. Checks every link, every v2 HMAC and the stored head."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_events WHERE case_id=? ORDER BY timestamp ASC", (case_id,))
    rows = cur.fetchall()
    prev = "GENESIS"
    for i, row in enumerate(rows):
        if row["prev_hash"] != prev:
            return {"ok": False, "events": len(rows), "reason": f"event {i + 1} does not follow the one before it"}
        if int(row.get("hash_version") or 1) >= AUDIT_V2:
            expected = _v2_hash(row["case_id"], row["actor_role"], row.get("actor_user"), row["action"], row["target"], row["timestamp"], prev)
        else:
            expected = _v1_hash(prev, row["action"], row["target"], row["timestamp"])
        if not hmac.compare_digest(expected, row["this_hash"] or ""):
            return {"ok": False, "events": len(rows), "reason": f"event {i + 1} ({row['action']}) was altered"}
        prev = row["this_hash"]
    cur.execute("SELECT head_hash, event_count FROM audit_heads WHERE case_id=?", (case_id,))
    head = cur.fetchone()
    if head and (head["head_hash"] != prev or int(head["event_count"]) != len(rows)):
        return {"ok": False, "events": len(rows), "reason": "the newest audit events were removed or replaced"}
    return {"ok": True, "events": len(rows), "reason": ""}


def verify_audit_chain(conn, case_id) -> bool:
    return verify_audit_chain_detail(conn, case_id)["ok"]
