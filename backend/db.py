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
import hashlib
import json
import re

import pymysql
import pymysql.cursors

from secrets_store import get_secret


def _mysql_config() -> dict:
    return {
        "host": get_secret("MYSQL_HOST") or "127.0.0.1",
        "port": int(get_secret("MYSQL_PORT") or 3307),
        "user": get_secret("MYSQL_USER") or "caseweave",
        "password": get_secret("MYSQL_PASSWORD"),
        "database": get_secret("MYSQL_DATABASE") or "caseweave",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
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
        created_at VARCHAR(64)
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
        INDEX (case_id),
        INDEX (timestamp)
    )""",
]


def _translate_sql(sql: str) -> str:
    """Translates sqlite-isms to MySQL dialect so every call site elsewhere
    in the codebase (api.py, auth.py, pipeline/*.py) keeps working
    unchanged: '?' placeholders -> '%s', and 'INSERT OR REPLACE INTO' ->
    MySQL's 'REPLACE INTO' (no 'OR' in MySQL's grammar)."""
    sql = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "REPLACE INTO", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\?", "%s", sql)
    return sql


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

    def close(self):
        self._conn.close()


def get_conn() -> _ConnWrapper:
    raw = pymysql.connect(**_mysql_config())
    return _ConnWrapper(raw)


def init_db():
    conn = get_conn()
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()
    conn.close()


def reset_db():
    """Drops and recreates every table — used by tests, NOT for production
    use (that's what Stage 18's retention/deletion policy is for)."""
    conn = get_conn()
    conn.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in [
        "cases", "evidence_items", "observations", "entities", "entity_mentions",
        "relationships", "users", "timeline_events", "conflicts", "evidence_links",
        "conflict_reviews", "audit_events",
    ]:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    conn.close()
    init_db()


def file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_audit_event(conn, case_id, actor_role, action, target):
    import datetime

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
        cur.execute(
            "SELECT this_hash FROM audit_events WHERE case_id=? ORDER BY timestamp DESC LIMIT 1",
            (case_id,),
        )
        row = cur.fetchone()
        prev_hash = row["this_hash"] if row else "GENESIS"

        timestamp = datetime.datetime.utcnow().isoformat(timespec="microseconds")
        audit_id = f"audit_{case_id}_{timestamp}_{action}"[:255]
        payload = json.dumps(
            {"prev_hash": prev_hash, "action": action, "target": target, "timestamp": timestamp},
            sort_keys=True,
        )
        this_hash = hashlib.sha256(payload.encode()).hexdigest()

        cur.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
            (audit_id, case_id, actor_role, action, target, timestamp, prev_hash, this_hash),
        )
        conn.commit()
    finally:
        cur.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
    return this_hash


def verify_audit_chain(conn, case_id) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM audit_events WHERE case_id=? ORDER BY timestamp ASC", (case_id,)
    )
    rows = cur.fetchall()
    prev = "GENESIS"
    for row in rows:
        payload = json.dumps(
            {
                "prev_hash": prev,
                "action": row["action"],
                "target": row["target"],
                "timestamp": row["timestamp"],
            },
            sort_keys=True,
        )
        expected = hashlib.sha256(payload.encode()).hexdigest()
        if expected != row["this_hash"]:
            return False
        prev = row["this_hash"]
    return True
