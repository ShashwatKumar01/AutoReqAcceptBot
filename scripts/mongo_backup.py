#!/usr/bin/env python3
"""
Export all MongoDB collections for RequestAcceptBot to a timestamped folder + .tar.gz.

Usage (local, with .env):
  python scripts/mongo_backup.py

From Railway (uses service env; reaches private Mongo):
  railway link
  railway run python scripts/mongo_backup.py

Environment:
  MONGODB_URI, MONGODB_DATABASE (same as the bot)
  BACKUP_DIR — output parent folder (default: ./backups)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def export_database(uri: str, db_name: str, out_dir: Path) -> dict:
    client = MongoClient(uri, serverSelectionTimeoutMS=30_000)
    client.admin.command("ping")
    db = client[db_name]
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "database": db_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "collections": {},
    }

    for name in sorted(db.list_collection_names()):
        coll = db[name]
        path = out_dir / f"{name}.jsonl"
        count = 0
        with path.open("w", encoding="utf-8") as fh:
            for doc in coll.find({}):
                fh.write(json_util.dumps(doc, ensure_ascii=False))
                fh.write("\n")
                count += 1
        manifest["collections"][name] = {"file": path.name, "documents": count}

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    client.close()
    return manifest


def make_archive(folder: Path) -> Path:
    archive = folder.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(folder, arcname=folder.name)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup MongoDB to JSONL + tar.gz")
    parser.add_argument(
        "--out",
        default=os.environ.get("BACKUP_DIR", str(ROOT / "backups")),
        help="Parent directory for backup folders",
    )
    parser.add_argument("--no-archive", action="store_true", help="Skip .tar.gz creation")
    args = parser.parse_args()

    uri = os.environ.get("MONGODB_URI", "").strip()
    db_name = os.environ.get("MONGODB_DATABASE", "RequestAcceptBot").strip()
    if not uri:
        print("MONGODB_URI is required", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(args.out) / f"{db_name}_{stamp}"
    print(f"Exporting {db_name} -> {folder}")
    manifest = export_database(uri, db_name, folder)
    total = sum(c["documents"] for c in manifest["collections"].values())
    print(f"Done: {len(manifest['collections'])} collections, {total} documents")

    if not args.no_archive:
        archive = make_archive(folder)
        print(f"Archive: {archive} ({archive.stat().st_size // 1024} KiB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
