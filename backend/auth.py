"""
Stage 12 — Real auth + enforced RBAC. Pilot-grade minimal: actual login
(JWT), actual per-endpoint role checks. NOT SSO, NOT multi-tenant — a real
single-department login system, nothing more (see PLAN.md's "pilot-grade
minimal" line for what's deliberately out).

Stage 13: JWT_SECRET is stored in Windows Credential Manager (secrets_store.py),
not a hardcoded fallback string. Generated once on first run if not already
set, so no secret ever exists in source code or a plaintext file.
"""
import os
import secrets
import uuid
import datetime

import bcrypt
import jwt
from fastapi import Header, HTTPException

from db import get_conn
from secrets_store import get_secret, set_secret


def _get_or_create_jwt_secret() -> str:
    existing = get_secret("JWT_SECRET")
    if existing:
        return existing
    generated = secrets.token_hex(32)
    set_secret("JWT_SECRET", generated)
    return generated


JWT_SECRET = os.environ.get("JWT_SECRET") or _get_or_create_jwt_secret()
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 8

ROLES = ("investigator", "reviewer", "admin")

# endpoint action -> roles allowed to perform it
PERMISSIONS = {
    "upload_evidence": ("investigator", "admin"),
    "view_case": ("investigator", "reviewer", "admin"),
    "confirm_conflict": ("reviewer", "admin"),
    "export_report": ("admin",),
    "manage_users": ("admin",),
    "delete_case": ("admin",),
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_user(username: str, password: str, role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    conn = get_conn()
    existing = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        conn.close()
        raise ValueError(f"username already exists: {username}")
    user_id = f"USR-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?)",
        (user_id, username, hash_password(password), role, datetime.datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return user_id


def authenticate(username: str, password: str) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row or not verify_password(password, row["password_hash"]):
        raise ValueError("invalid username or password")
    return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}


def create_token(user: dict) -> str:
    payload = {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid token")


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    return decode_token(token)


def enforce_permission(user: dict, action: str):
    allowed_roles = PERMISSIONS.get(action)
    if allowed_roles is None:
        raise ValueError(f"unknown permission action: {action}")
    if user["role"] not in allowed_roles:
        raise HTTPException(
            403, f"role '{user['role']}' cannot perform '{action}', requires one of {allowed_roles}"
        )
