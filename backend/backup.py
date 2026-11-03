"""
Stage 19 — Backup (stopgap, not full DR). Keeps ONE always-current backup of the database, the object store
and the vector stores, stored outside the project directory so a project-folder disaster doesn't take the
backup with it.

What changed from the first version, and why it matters for evidence:
- the new backup is built in a temporary folder next to the old one and swapped in only if everything
  succeeded, so a failed run can never replace the last good backup with an empty or partial one;
- mysqldump is found on PATH or via MYSQLDUMP_PATH (not a hard-coded Windows path), and the database password
  is passed through the environment (MYSQL_PWD), never on the command line where other users could read it;
- every problem is returned in the result ("errors") instead of being swallowed;
- the destination can be set with CASEWEAVE_BACKUP_DIR (default: Desktop/CaseWeave_Backup).

This is NOT real disaster recovery (that needs offsite/geographically separate storage, encryption at rest, a
tested restore procedure, and a real retention schedule — see PLAN.md Stage 19/20).
"""
import datetime
import os
import shutil
import stat
import subprocess
from pathlib import Path

from secrets_store import get_secret

BACKEND_DIR = Path(__file__).parent


def backup_dir() -> Path:
    return Path(os.environ.get("CASEWEAVE_BACKUP_DIR") or (Path.home() / "Desktop" / "CaseWeave_Backup"))


def _find_mysqldump() -> str | None:
    explicit = os.environ.get("MYSQLDUMP_PATH")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("mysqldump")
    if found:
        return found
    for candidate in (r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe", r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe"):
        if Path(candidate).exists():
            return candidate
    return None


def _backup_mysql(dest: Path) -> tuple[bool, str]:
    """Dumps the database into dest/caseweave.sql. Returns (ok, error message)."""
    exe = _find_mysqldump()
    if not exe:
        return False, "mysqldump was not found (install the MySQL client or set MYSQLDUMP_PATH)"
    env = {**os.environ, "MYSQL_PWD": get_secret("MYSQL_PASSWORD") or ""}
    cmd = [
        exe, f"-h{get_secret('MYSQL_HOST') or '127.0.0.1'}", f"-P{get_secret('MYSQL_PORT') or '3307'}",
        f"-u{get_secret('MYSQL_USER') or 'caseweave'}", "--single-transaction", "--routines", get_secret("MYSQL_DATABASE") or "caseweave",
    ]
    with open(dest / "caseweave.sql", "w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True, env=env, timeout=600)
    if result.returncode != 0:
        return False, f"mysqldump failed (exit {result.returncode}): {result.stderr.strip()[:300]}"
    if (dest / "caseweave.sql").stat().st_size == 0:
        return False, "mysqldump produced an empty file"
    return True, ""


def _rmtree(path: Path) -> None:
    def _onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_onerror)


def run_backup() -> dict:
    """Builds a complete new backup beside the old one and swaps it in only if the database dump worked.
    Returns {"backup_dir", "items_copied", "errors", "timestamp"}."""
    target = backup_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / (target.name + ".new")
    if staging.exists():
        _rmtree(staging)
    staging.mkdir(parents=True)

    copied, errors = [], []
    ok, err = _backup_mysql(staging)
    if ok:
        copied.append("caseweave.sql (mysqldump)")
    else:
        errors.append(err)

    for dir_name in ("object_store", "chroma_store", "report_data"):
        src = BACKEND_DIR / dir_name
        if src.exists():
            try:
                shutil.copytree(src, staging / dir_name)
                copied.append(dir_name)
            except Exception as e:  # noqa: BLE001 - reported, not hidden
                errors.append(f"could not copy {dir_name}: {e}")

    stamp = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    if errors:
        # keep the previous backup untouched; leave the incomplete one for inspection under a clear name
        failed = target.parent / (target.name + ".failed")
        if failed.exists():
            _rmtree(failed)
        staging.rename(failed)
        return {"backup_dir": str(target), "items_copied": copied, "errors": errors, "timestamp": stamp, "kept_previous_backup": target.exists()}

    (staging / "last_backup.txt").write_text(f"Last backup: {stamp}Z\n", encoding="utf-8")
    old = target.parent / (target.name + ".old")
    if old.exists():
        _rmtree(old)
    if target.exists():
        target.rename(old)
    staging.rename(target)
    if old.exists():
        _rmtree(old)
    return {"backup_dir": str(target), "items_copied": copied, "errors": [], "timestamp": stamp}


if __name__ == "__main__":
    result = run_backup()
    print(f"Backup folder: {result['backup_dir']}")
    print(f"Items: {result['items_copied']}")
    if result["errors"]:
        print("ERRORS (the previous backup was left in place):")
        for e in result["errors"]:
            print(" -", e)
        raise SystemExit(1)
