"""
Stage 13 — Secrets management. Primary: Windows Credential Manager (via the
`keyring` package), encrypted at rest with DPAPI, scoped to the logged-in
Windows user account — this is what the local dev machine uses. Fallback:
a plaintext backend/.env file, so anyone who clones this repo on a
different machine (no Credential Manager entries of their own) can still
run it by copying .env.example to .env and filling in their own keys.

Lookup order per key: 1) already-set os.environ (real deployment env vars
take priority), 2) Windows Credential Manager, 3) backend/.env if present.
This keeps the local machine's secrets out of any file while staying
portable for anyone else who pulls this from GitHub.

Caveat, honest: Credential Manager is single-machine/single-user scoped.
It's the right fix for local dev now, not the right fix once Stage 20
moves this onto a shared server — that needs a real Vault/Secrets Manager
instead, since there's no single "logged-in user" on a server the same way.
"""
import os
from pathlib import Path

import keyring

SERVICE_NAME = "caseweave"
ENV_FALLBACK_PATH = Path(__file__).parent / ".env"

SECRET_KEYS = [
    "META_API_KEY",
    "META_API_BASE_URL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "GOOGLE_API_KEY",
    "GOOGLE_MODEL",
    "HUGGINGFACE_API_KEY",
    "JWT_SECRET",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
    "REDIS_HOST",
    "REDIS_PORT",
]


def _read_env_file() -> dict:
    if not ENV_FALLBACK_PATH.exists():
        return {}
    values = {}
    for line in ENV_FALLBACK_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key:
            values[key] = value
    return values


def get_secret(key: str) -> str:
    """Returns the stored value, checking os.environ, then Windows
    Credential Manager, then a local .env file (in that order). Empty
    string if not set anywhere."""
    if os.environ.get(key):
        return os.environ[key]
    value = keyring.get_password(SERVICE_NAME, key)
    if value:
        return value
    return _read_env_file().get(key, "")


def set_secret(key: str, value: str):
    keyring.set_password(SERVICE_NAME, key, value)


def delete_secret(key: str):
    try:
        keyring.delete_password(SERVICE_NAME, key)
    except keyring.errors.PasswordDeleteError:
        pass


def load_all_secrets() -> dict:
    """Returns all known secrets as a dict, same shape the old .env-based
    os.environ population produced."""
    return {key: get_secret(key) for key in SECRET_KEYS}
