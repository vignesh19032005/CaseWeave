"""
Stage 12 — Real auth + enforced RBAC. Pilot-grade minimal: actual login
(JWT), actual per-endpoint role checks. NOT SSO, NOT multi-tenant — a real
single-department login system, nothing more (see PLAN.md's "pilot-grade
minimal" line for what's deliberately out).

Stage 13: JWT_SECRET is stored in the OS keyring (secrets_store.py), not a
hardcoded fallback string. Generated once on first run if not already set,
so no secret ever exists in source code.

Hardening on top of that:
- the role used for every request is read from the database, not trusted from
  the token, so a demoted or deleted account loses access at once;
- a stolen token cannot outlive a password change (tokens carry a short
  fingerprint of the password hash);
- login takes the same time whether or not the username exists;
- accounts still on the shipped default password are flagged and must change it
  before they can do anything else.
"""
import os
import re
import uuid
import datetime

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException

from db import get_conn, utcnow
from secrets_store import get_or_create_secret

JWT_SECRET = os.environ.get("JWT_SECRET") or get_or_create_secret("JWT_SECRET")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 8

ROLES = ("investigator", "reviewer", "admin")
DEFAULT_ADMIN_PASSWORD = "changeme123"
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_BYTES = 72  # bcrypt ignores (or, in newer versions, rejects) anything longer
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")

# endpoint action -> roles allowed to perform it
PERMISSIONS = {
    "upload_evidence": ("investigator", "admin"),
    "generate_scenario": ("investigator", "admin"),
    "approve_layout": ("reviewer", "admin"),
    "view_case": ("investigator", "reviewer", "admin"),
    "create_case": ("investigator", "admin"),
    "confirm_conflict": ("reviewer", "admin"),
    "export_report": ("investigator", "reviewer", "admin"),  # whoever may view a case may export it; user management and deletion stay admin-only
    "manage_users": ("admin",),
    "delete_case": ("admin",),
}

# a hash to compare against when the username does not exist, so the response time does not give it away
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


def validate_new_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    if password == DEFAULT_ADMIN_PASSWORD:
        raise ValueError("choose a password other than the shipped default")


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = (password or "").encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, (password_hash or "").encode())
    except ValueError:
        return False


def _fingerprint(password_hash: str) -> str:
    return (password_hash or "")[-12:]


def create_user(username: str, password: str, role: str, must_change_password: bool = False, enforce_policy: bool = True) -> str:
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    if not USERNAME_RE.match(username or ""):
        raise ValueError("username must be 3-64 characters: letters, digits and . _ @ -")
    if enforce_policy:
        validate_new_password(password)
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ValueError(f"username already exists: {username}")
        user_id = f"USR-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, role, created_at, must_change_password) VALUES (?,?,?,?,?,?)",
            (user_id, username, hash_password(password), role, utcnow().isoformat(), 1 if must_change_password else 0),
        )
        conn.commit()
    return user_id


def authenticate(username: str, password: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username or "",)).fetchone()
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise ValueError("invalid username or password")
    return {"user_id": row["user_id"], "username": row["username"], "role": row["role"],
            "must_change_password": bool(row.get("must_change_password")), "pwd": _fingerprint(row["password_hash"])}


def create_token(user: dict) -> str:
    payload = {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "pwd": user.get("pwd", ""),
        "exp": utcnow() + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid token")


def _bearer(authorization) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing or malformed Authorization header")
    return authorization.removeprefix("Bearer ").strip()


def _load_user(authorization) -> dict:
    claims = decode_token(_bearer(authorization))
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (claims.get("user_id"),)).fetchone()
    if not row:
        raise HTTPException(401, "this account no longer exists")
    if claims.get("pwd", "") != _fingerprint(row["password_hash"]):
        raise HTTPException(401, "session ended because the password was changed")
    # the role comes from the database, never from the token
    return {"user_id": row["user_id"], "username": row["username"], "role": row["role"],
            "must_change_password": bool(row.get("must_change_password"))}


def get_user_even_if_password_change_pending(authorization: str = Header(None)) -> dict:
    """For /auth/me and /auth/change-password only."""
    return _load_user(authorization)


def get_current_user(authorization: str = Header(None)) -> dict:
    user = _load_user(authorization)
    if user["must_change_password"]:
        raise HTTPException(403, "password change required: sign in and choose a new password before continuing")
    return user


def enforce_permission(user: dict, action: str):
    allowed_roles = PERMISSIONS.get(action)
    if allowed_roles is None:
        raise ValueError(f"unknown permission action: {action}")
    if user["role"] not in allowed_roles:
        raise HTTPException(
            403, f"role '{user['role']}' cannot perform '{action}', requires one of {allowed_roles}"
        )


def require(action: str):
    """Dependency: the signed-in user, who must be allowed to perform `action`."""
    def dep(user: dict = Depends(get_current_user)) -> dict:
        enforce_permission(user, action)
        return user
    return dep


# ------------------------------------------------------------ account management ----

def change_password(user_id: str, old_password: str, new_password: str) -> None:
    validate_new_password(new_password)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or not verify_password(old_password, row["password_hash"]):
            raise ValueError("the current password is not correct")
        conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE user_id=?", (hash_password(new_password), user_id))
        conn.commit()


def list_users() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id, username, role, created_at, must_change_password FROM users ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def admin_reset_password(user_id: str, new_password: str) -> None:
    validate_new_password(new_password)
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
            raise ValueError("user not found")
        conn.execute("UPDATE users SET password_hash=?, must_change_password=1 WHERE user_id=?", (hash_password(new_password), user_id))
        conn.commit()


def delete_user(user_id: str, acting_user_id: str) -> None:
    if user_id == acting_user_id:
        raise ValueError("you cannot delete your own account")
    with get_conn() as conn:
        row = conn.execute("SELECT role FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            raise ValueError("user not found")
        if row["role"] == "admin" and conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin'").fetchone()["n"] <= 1:
            raise ValueError("the last administrator cannot be deleted")
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()


def bootstrap_admin() -> str | None:
    """First run only: creates an admin so there is a way to log in. The password comes from
    CASEWEAVE_ADMIN_PASSWORD when set; otherwise it is the shipped default and the account is forced to
    change it at first login. Returns a note to log, or None when users already exist."""
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return None
    chosen = os.environ.get("CASEWEAVE_ADMIN_PASSWORD", "").strip()
    if chosen:
        create_user("admin", chosen, "admin", must_change_password=False)
        return "Created the admin account with the password from CASEWEAVE_ADMIN_PASSWORD."
    create_user("admin", DEFAULT_ADMIN_PASSWORD, "admin", must_change_password=True, enforce_policy=False)
    return "Created the admin account admin / changeme123. It must change this password at first sign-in."


def flag_default_passwords() -> int:
    """Any account still on the shipped default password must change it before doing anything else."""
    flagged = 0
    with get_conn() as conn:
        for row in conn.execute("SELECT user_id, password_hash, must_change_password FROM users").fetchall():
            if not row["must_change_password"] and verify_password(DEFAULT_ADMIN_PASSWORD, row["password_hash"]):
                conn.execute("UPDATE users SET must_change_password=1 WHERE user_id=?", (row["user_id"],))
                flagged += 1
        conn.commit()
    return flagged
