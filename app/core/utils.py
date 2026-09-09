import uuid
from datetime import datetime, timezone
from typing import Generator, Any

def format_duration(seconds: int) -> str:
    if seconds < 0:
        return "0 seconds"
    if seconds == 0:
        return "0 seconds"
        
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs > 1 else ''}")
        
    return " ".join(parts)

def format_number(n: int) -> str:
    return f"{n:,}"

def truncate_text(text: str, max_len: int = 100) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."

def substitute_variables(template: str, context: dict) -> str:
    if not template:
        return ""
    try:
        # Use safe substitution by manually replacing or using format_map with a defaultdict
        class SafeDict(dict):
            def __missing__(self, key):
                return f"{{{key}}}"
        return template.format_map(SafeDict(**context))
    except Exception:
        # Fallback if something weird happens
        for k, v in context.items():
            template = template.replace(f"{{{k}}}", str(v))
        return template

def build_mention(user_id: int, first_name: str) -> str:
    # Telegram HTML mention
    safe_name = first_name.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def chunk_list(lst: list[Any], size: int) -> Generator[list[Any], None, None]:
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def generate_job_id() -> str:
    return uuid.uuid4().hex


def build_broadcast_payload(message) -> dict | None:
    """Build a broadcast payload dict from an aiogram Message."""
    payload: dict = {"parse_mode": "HTML"}
    if message.text:
        payload["type"] = "text"
        payload["text"] = message.html_text or message.text
    elif message.photo:
        payload["type"] = "photo"
        payload["photo"] = message.photo[-1].file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    elif message.video:
        payload["type"] = "video"
        payload["video"] = message.video.file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    elif message.document:
        payload["type"] = "document"
        payload["document"] = message.document.file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    elif message.animation:
        payload["type"] = "animation"
        payload["animation"] = message.animation.file_id
        if message.caption:
            payload["caption"] = message.html_text or message.caption
    else:
        return None
    return payload
