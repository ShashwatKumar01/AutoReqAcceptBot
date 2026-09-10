#!/usr/bin/env python3
"""
Restore MongoDB from a backup folder (or extracted .tar.gz contents).

Usage:
  python scripts/mongo_restore.py backups/request_accept_bot_20260101T120000Z
  python scripts/mongo_restore.py backups/request_accept_bot_20260101T120000Z.tar.gz

  # New host after leaving Railway:
  MONGODB_URI=mongodb+srv://user:pass@cluster/ python scripts/mongo_restore.py ...

Options:
  --drop   Drop each collection before import (full replace)
  --dry-run   Count only, no writes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import tempfile
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


def resolve_backup_path(path: Path) -> Path:
    if path.suffixes == [".tar", ".gz"] or path.suffix == ".gz":
        tmp = Path(tempfile.mkdtemp(prefix="mongo_restore_"))
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(tmp)
        subs = [p for p in tmp.iterdir() if p.is_dir()]
        if len(subs) == 1:
            return subs[0]
        return tmp
    return path


def restore_folder(uri: str, folder: Path, *, drop: bool, dry_run: bool) -> None:
    manifest_path = folder / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        db_name = manifest.get("database") or os.environ.get("MONGODB_DATABASE", "RequestAcceptBot")
        collections = manifest.get("collections", {})
        files = {name: folder / meta["file"] for name, meta in collections.items()}
    else:
        db_name = os.environ.get("MONGODB_DATABASE", "RequestAcceptBot")
        files = {p.stem: p for p in folder.glob("*.jsonl")}

    client = MongoClient(uri, serverSelectionTimeoutMS=30_000)
    client.admin.command("ping")
    db = client[db_name]

    for coll_name, jsonl_path in sorted(files.items()):
        if not jsonl_path.is_file():
            print(f"Skip missing {jsonl_path}")
            continue
        docs = []
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    docs.append(json_util.loads(line))
        print(f"{coll_name}: {len(docs)} documents")
        if dry_run:
            continue
        if drop:
            db[coll_name].drop()
        if docs:
            db[coll_name].insert_many(docs, ordered=False)

    client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore MongoDB from JSONL backup")
    parser.add_argument("backup", type=Path, help="Backup folder or .tar.gz")
    parser.add_argument("--drop", action="store_true", help="Drop collections before import")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        print("MONGODB_URI is required", file=sys.stderr)
        return 1
    if not args.backup.exists():
        print(f"Not found: {args.backup}", file=sys.stderr)
        return 1

    folder = resolve_backup_path(args.backup)
    print(f"Restoring from {folder}")
    restore_folder(uri, folder, drop=args.drop, dry_run=args.dry_run)
    print("Restore finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
