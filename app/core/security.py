import re
from urllib.parse import urlparse

# Allowed Telegram HTML tags
ALLOWED_TAGS = ['b', 'i', 'u', 's', 'code', 'pre', 'a']

def sanitize_html(text: str) -> str:
    """Escape dangerous HTML, allow only safe Telegram HTML tags."""
    if not text:
        return text
    
    # Simple replace for brackets not belonging to allowed tags
    # A robust implementation would use a proper HTML parser, but for Telegram this is often enough
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Re-enable allowed tags
    for tag in ALLOWED_TAGS:
        if tag == 'a':
            # Handle <a> specially if needed, for now just allow standard <a href="...">...</a>
            # A more robust regex would be needed to safely re-enable href
            pass
        else:
            text = text.replace(f'&lt;{tag}&gt;', f'<{tag}>').replace(f'&lt;/{tag}&gt;', f'</{tag}>')
            
    # Naive href restoration (use with caution)
    text = re.sub(r'&lt;a href=&quot;(.*?)&quot;&gt;(.*?)&lt;/a&gt;', r'<a href="\1">\2</a>', text)
    return text

def validate_url(url: str) -> bool:
    """Check url is valid http/https, reasonable length, not localhost/private IPs."""
    if not url or len(url) > 2048:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        if parsed.hostname in ('localhost', '127.0.0.1', '::1') or parsed.hostname.startswith('192.168.') or parsed.hostname.startswith('10.'):
            return False
        return True
    except Exception:
        return False

def validate_button_text(text: str) -> bool:
    """Max 64 chars, not empty."""
    return bool(text) and len(text.strip()) > 0 and len(text) <= 64

def validate_callback_data(data: str) -> bool:
    """Max 64 bytes."""
    return bool(data) and len(data.encode('utf-8')) <= 64

def parse_and_validate_duration(text: str) -> int | None:
    """Parse '15m', '1h', '90m', '2h30m', etc. Returns seconds."""
    if not text:
        return None
        
    text = text.lower().replace(' ', '')
    pattern = r'^((?P<hours>\d+)h)?((?P<minutes>\d+)m)?((?P<seconds>\d+)s)?$'
    match = re.match(pattern, text)
    
    if not match:
        # Try pure number as minutes
        if text.isdigit():
            val = int(text) * 60
            return val if 0 <= val <= 259200 else None  # 3 days max
        return None
        
    parts = match.groupdict()
    if all(v is None for v in parts.values()):
        return None
        
    hours = int(parts['hours'] or 0)
    minutes = int(parts['minutes'] or 0)
    seconds = int(parts['seconds'] or 0)
    
    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    
    if 0 <= total_seconds <= 259200:  # 3 days max
        return total_seconds
    return None

def sanitize_message_text(text: str) -> str:
    """Strip null bytes, limit to 4096 chars."""
    if not text:
        return text
    text = text.replace('\x00', '')
    return text[:4096]

def is_valid_telegram_id(id: int) -> bool:
    return isinstance(id, int) and id != 0
