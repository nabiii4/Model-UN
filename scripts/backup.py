"""Backups for maintainers.

  python scripts/backup.py export              -> writes nightmare-backup-<date>.zip here
  python scripts/backup.py export backups/     -> writes it into the backups/ folder
  python scripts/backup.py import my-backup.zip  -> REPLACES everything with the backup (asks first)
"""
import _path  # noqa: F401

import sys
from pathlib import Path

from app import create_app
from logic.backup import export_zip, import_zip


def main(argv):
    if len(argv) < 2 or argv[1] not in ("export", "import"):
        print(__doc__)
        return 1
    app = create_app()
    with app.app_context():
        if argv[1] == "export":
            folder = Path(argv[2]) if len(argv) > 2 else Path(".")
            folder.mkdir(parents=True, exist_ok=True)
            blob, name = export_zip()
            path = folder / name
            path.write_bytes(blob)
            print(f"Saved {path} ({len(blob) // 1024} KB). Keep it somewhere safe.")
            return 0
        if len(argv) < 3:
            print("Which file? Example: python scripts/backup.py import nightmare-backup.zip")
            return 1
        path = Path(argv[2])
        if not path.exists():
            print(f"Can't find {path}.")
            return 1
        answer = input("This REPLACES everything in the database with the backup. Type YES to continue: ")
        if answer.strip() != "YES":
            print("Cancelled. Nothing changed.")
            return 1
        counts = import_zip(path.read_bytes())
        print("Restored:", ", ".join(f"{k}={v}" for k, v in counts.items() if v))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
