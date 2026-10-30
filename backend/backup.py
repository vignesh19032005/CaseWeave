"""
Stage 19 — Backup (stopgap, not full DR). SQLite + local object_store/ has
zero redundancy today — one disk failure loses a case. This keeps ONE
always-current backup, overwritten each run, stored outside the project
directory so a project-folder disaster doesn't take the backup with it.

Portable by design: uses Path.home() to resolve the Desktop location, so
this works correctly on any machine/user if the repo is cloned elsewhere —
nothing here is hardcoded to this machine's username or path.

This is NOT real disaster recovery (that needs offsite/geographically
separate storage, a tested restore procedure, and a real retention
schedule — see PLAN.md Stage 19/20). It's the honest stopgap: "don't lose
everything to one disk failure" — nothing more.
"""
import shutil
import subprocess
from pathlib import Path

from secrets_store import get_secret

BACKEND_DIR = Path(__file__).parent
BACKUP_DIR = Path.home() / "Desktop" / "CaseWeave_Backup"

MYSQLDUMP_PATH = r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"


def _backup_mysql() -> bool:
    """Dumps the MySQL database to a .sql file via mysqldump (uses the
    native client to connect to the isolated caseweave-mysql container)."""
    host = get_secret("MYSQL_HOST") or "127.0.0.1"
    port = get_secret("MYSQL_PORT") or "3307"
    user = get_secret("MYSQL_USER") or "caseweave"
    password = get_secret("MYSQL_PASSWORD")
    database = get_secret("MYSQL_DATABASE") or "caseweave"

    dump_path = BACKUP_DIR / "caseweave.sql"
    with open(dump_path, "w", encoding="utf-8") as f:
        result = subprocess.run(
            [MYSQLDUMP_PATH, f"-h{host}", f"-P{port}", f"-u{user}", f"-p{password}", database],
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
        )
    return result.returncode == 0


def run_backup() -> dict:
    """Overwrites the single standing backup with the current state of the
    DB, object store, and chroma vector store. Returns a summary dict."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    copied = []

    if _backup_mysql():
        copied.append("caseweave.sql (mysqldump)")

    for dir_name in ("object_store", "chroma_store"):
        src = BACKEND_DIR / dir_name
        if src.exists():
            dest = BACKUP_DIR / dir_name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            copied.append(dir_name)

    import datetime
    marker = BACKUP_DIR / "last_backup.txt"
    marker.write_text(f"Last backup: {datetime.datetime.utcnow().isoformat()}Z\n", encoding="utf-8")

    return {"backup_dir": str(BACKUP_DIR), "items_copied": copied, "timestamp": datetime.datetime.utcnow().isoformat()}


if __name__ == "__main__":
    result = run_backup()
    print(f"Backed up to: {result['backup_dir']}")
    print(f"Items: {result['items_copied']}")
