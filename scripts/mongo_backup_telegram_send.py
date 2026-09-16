#!/usr/bin/env python3
"""
Send the newest mongo backup .tar.gz to a Telegram chat (super-admin DM).

Requires the bot to have an existing private chat with the recipient
(user must have /start the bot once).

Environment:
  BOT_TOKEN
  BACKUP_TELEGRAM_CHAT_ID — your Telegram user ID (same as SUPER_ADMIN_IDS[0])
  BACKUP_DIR — folder containing *.tar.gz (default: ./backup_out)
  TELEGRAM_MAX_MB — max upload size (default 48, Telegram bot limit ~50MB)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def _latest_archive(backup_dir: Path) -> Path | None:
    archives = sorted(backup_dir.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return archives[0] if archives else None


def send_document(token: str, chat_id: int, path: Path, caption: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with path.open("rb") as fh:
        resp = requests.post(
            url,
            data={"chat_id": str(chat_id), "caption": caption[:1024]},
            files={"document": (path.name, fh, "application/gzip")},
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json()


def send_message(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(
        url,
        json={"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"},
        timeout=60,
    ).raise_for_status()


def main() -> int:
    token = os.environ.get("BOT_TOKEN", "").strip()
    chat_raw = os.environ.get("BACKUP_TELEGRAM_CHAT_ID", "").strip()
    backup_dir = Path(os.environ.get("BACKUP_DIR", "backup_out"))
    max_mb = int(os.environ.get("TELEGRAM_MAX_MB", "48"))

    if not token or not chat_raw:
        print("BOT_TOKEN and BACKUP_TELEGRAM_CHAT_ID are required", file=sys.stderr)
        return 1

    try:
        chat_id = int(chat_raw)
    except ValueError:
        print("BACKUP_TELEGRAM_CHAT_ID must be a numeric Telegram user ID", file=sys.stderr)
        return 1

    if not backup_dir.is_dir():
        print(f"BACKUP_DIR not found: {backup_dir}", file=sys.stderr)
        return 1

    archive = _latest_archive(backup_dir)
    if not archive:
        print(f"No .tar.gz in {backup_dir}", file=sys.stderr)
        return 1

    size_mb = archive.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        msg = (
            f"⚠️ <b>Mongo backup too large for Telegram</b> ({size_mb:.1f} MB &gt; {max_mb} MB).\n\n"
            f"File: <code>{archive.name}</code>\n"
            "Download the artifact from GitHub Actions or run backup locally.\n\n"
            "Restore: <code>python scripts/mongo_restore.py &lt;archive.tar.gz&gt;</code>"
        )
        send_message(token, chat_id, msg)
        print(f"Skipped upload (too large: {size_mb:.1f} MB); notified chat {chat_id}")
        return 0

    caption = (
        f"🗄 MongoDB backup\n{archive.name}\n"
        f"Size: {size_mb:.2f} MB\n\n"
        "Restore locally:\n"
        f"python scripts/mongo_restore.py {archive.name}"
    )
    send_document(token, chat_id, archive, caption)
    print(f"Sent {archive.name} to chat {chat_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
