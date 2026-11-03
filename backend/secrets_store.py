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
import secrets as _secrets
import threading
from pathlib import Path

import keyring

SERVICE_NAME = "caseweave"
ENV_FALLBACK_PATH = Path(__file__).parent / ".env"
# Generated secrets that could not be put in the OS keyring (for example on a Linux server without a keyring
# backend) are kept in this owner-only file instead, so the service still starts. It is git-ignored.
GENERATED_PATH = Path(__file__).parent / ".generated_secrets"
_gen_lock = threading.Lock()

SECRET_KEYS = [
    "META_API_KEY",
    "META_API_BASE_URL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "GOOGLE_API_KEY",
    "GOOGLE_MODEL",
    "HUGGINGFACE_API_KEY",
    "JWT_SECRET",
    "AUDIT_HMAC_KEY",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_PASSWORD",
    "BACKUP_ENCRYPTION_KEY",
    "LOCAL_LLM_BASE_URL",
    "LOCAL_LLM_MODEL",
    "LOCAL_LLM_API_KEY",
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
    if key in os.environ:
        # "__unset__" means "deliberately empty": Windows cannot hold an empty environment variable, and a test run
        # against a throwaway Redis has to be able to say "no password" even though the real one is in the keyring.
        return "" if os.environ[key] == "__unset__" else os.environ[key]
    try:
        value = keyring.get_password(SERVICE_NAME, key)
        if value:
            return value
    except Exception:
        pass
    return _read_env_file().get(key, "") or _read_generated().get(key, "")


def _read_generated() -> dict:
    if not GENERATED_PATH.exists():
        return {}
    out = {}
    for line in GENERATED_PATH.read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


def set_secret(key: str, value: str):
    """Stores a secret in the OS keyring; if no keyring backend exists, in an owner-only local file."""
    try:
        keyring.set_password(SERVICE_NAME, key, value)
        return
    except Exception:  # noqa: BLE001 - no usable keyring backend on this machine
        pass
    with _gen_lock:
        current = _read_generated()
        current[key] = value
        fd = os.open(GENERATED_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(f"{k}={v}" + chr(10) for k, v in current.items()))


def get_or_create_secret(key: str, nbytes: int = 32) -> str:
    """Returns the secret, generating and storing a random one the first time. Safe if two processes
    start together: after generating, it re-reads, and the stored value wins."""
    existing = get_secret(key)
    if existing:
        return existing
    with _gen_lock:
        existing = get_secret(key)
        if existing:
            return existing
        set_secret(key, _secrets.token_hex(nbytes))
    return get_secret(key)


def delete_secret(key: str):
    try:
        keyring.delete_password(SERVICE_NAME, key)
    except Exception:  # noqa: BLE001 - missing entry or no keyring backend
        pass


def load_all_secrets() -> dict:
    """Returns all known secrets as a dict, same shape the old .env-based
    os.environ population produced."""
    return {key: get_secret(key) for key in SECRET_KEYS}
