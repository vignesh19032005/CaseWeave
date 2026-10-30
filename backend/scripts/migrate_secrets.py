"""
One-time Stage 13 migration: reads backend/.env, writes every value into
Windows Credential Manager via secrets_store.py, then tells you it's safe
to delete .env. Run once: python scripts/migrate_secrets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from secrets_store import set_secret, SECRET_KEYS

ENV_PATH = Path(__file__).parent.parent / ".env"


def main():
    if not ENV_PATH.exists():
        print(f"No .env file found at {ENV_PATH} — nothing to migrate.")
        return

    values = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key in SECRET_KEYS:
            values[key] = value

    migrated = 0
    for key in SECRET_KEYS:
        value = values.get(key, "")
        if value:
            set_secret(key, value)
            print(f"  migrated: {key} ({'*' * min(len(value), 8)}...)")
            migrated += 1
        else:
            print(f"  skipped (not set): {key}")

    print(f"\nMigrated {migrated} secret(s) into Windows Credential Manager under service 'caseweave'.")
    print(f"Verify with: python -c \"from secrets_store import load_all_secrets; print(load_all_secrets())\"")
    print(f"Once verified, delete {ENV_PATH} — it's no longer needed.")


if __name__ == "__main__":
    main()
