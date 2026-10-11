"""Backups: export everything to one .zip (JSON + images), and restore it.

Used by Admin > Backups (export) and by scripts/backup.py (export and import).
"""
import io
import json
import zipfile
from datetime import date, datetime

from sqlalchemy import Date, DateTime, LargeBinary, delete, insert, select

from extensions import db
from models import Base
from models.base import utcnow

FORMAT_VERSION = 1


def _tables():
    # sorted_tables puts parents before children, so inserts never break foreign keys.
    return list(Base.metadata.sorted_tables)


def export_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = {"format_version": FORMAT_VERSION, "exported_at": utcnow().isoformat(), "tables": {}}
        for table in _tables():
            rows = []
            for row in db.session.execute(select(table)).mappings():
                item = {}
                for col in table.columns:
                    value = row[col.name]
                    if isinstance(col.type, LargeBinary):
                        if value is not None:
                            path = f"blobs/{table.name}/{row[list(table.primary_key.columns)[0].name]}.{col.name}"
                            z.writestr(path, value)
                            item[col.name] = {"$blob": path}
                        else:
                            item[col.name] = None
                    elif isinstance(value, datetime):
                        item[col.name] = value.isoformat()
                    elif isinstance(value, date):
                        item[col.name] = value.isoformat()
                    else:
                        item[col.name] = value
                rows.append(item)
            z.writestr(f"tables/{table.name}.json", json.dumps(rows, ensure_ascii=False))
            manifest["tables"][table.name] = len(rows)
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    name = f"nightmare-backup-{utcnow().strftime('%Y-%m-%d-%H%M')}.zip"
    return buf.getvalue(), name


def import_zip(blob):
    """Replace EVERYTHING in the database with the backup. Returns row counts."""
    counts = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format_version") != FORMAT_VERSION:
            raise ValueError("This backup is from a different version of the site.")
        tables = _tables()
        for table in reversed(tables):
            db.session.execute(delete(table))
        for table in tables:
            path = f"tables/{table.name}.json"
            if path not in z.namelist():
                continue
            rows = json.loads(z.read(path))
            cleaned = []
            for item in rows:
                out = {}
                for col in table.columns:
                    value = item.get(col.name)
                    if value is None:
                        out[col.name] = None
                    elif isinstance(col.type, LargeBinary):
                        out[col.name] = z.read(value["$blob"])
                    elif isinstance(col.type, DateTime):
                        out[col.name] = datetime.fromisoformat(value)
                    elif isinstance(col.type, Date):
                        out[col.name] = date.fromisoformat(value)
                    else:
                        out[col.name] = value
                cleaned.append(out)
            if cleaned:
                db.session.execute(insert(table), cleaned)
            counts[table.name] = len(cleaned)
    db.session.commit()
    return counts
