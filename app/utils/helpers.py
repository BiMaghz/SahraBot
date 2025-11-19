import io
import random
import re
import string
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Tuple

import qrcode
from qrcode.main import QRCode

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32

def format_traffic(n_bytes: Optional[Union[int, float]], precision: int = 2) -> str:
    if n_bytes is None:
        return "N/A"
    if n_bytes == 0:
        return "0 B"
    if n_bytes < 0:
        return "Invalid"

    power = 1024
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}

    while n_bytes >= power and n < len(power_labels):
        n_bytes /= power
        n += 1

    return f"{n_bytes:.{precision}f} {power_labels[n]}"

def format_expiry(expiry_date: Optional[datetime]) -> str:
    if not expiry_date:
        return "No expiration"
    if expiry_date.tzinfo is None:
        expiry_date = expiry_date.replace(tzinfo=timezone.utc)

    now_dt = datetime.now(timezone.utc)
    remaining_delta = expiry_date - now_dt
    date_str = expiry_date.strftime("%Y-%m-%d")

    if remaining_delta.total_seconds() <= 0:
        return f"{date_str} (Expired)"

    days = remaining_delta.days
    if days > 0:
        return f"{date_str} (in {days} days)"
    
    hours, remainder = divmod(remaining_delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{date_str} (in {int(hours)}h {int(minutes)}m)"

def format_time_ago(dt_obj: Optional[datetime]) -> str:
    if not dt_obj:
        return "-"
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    diff = now - dt_obj
    seconds = diff.total_seconds()
    if seconds < 60:
        return "just now"
    
    minutes = seconds / 60
    if minutes < 60:
        return f"about {int(minutes)} minutes ago"

    hours = minutes / 60
    if hours < 24:
        return f"about {int(hours)} hours ago"
        
    days = hours / 24
    return f"about {int(days)} days ago"

def parse_duration_to_datetime(duration_str: str) -> Optional[datetime]:
    duration_str = duration_str.strip().lower()
    if duration_str == '0':
        return None  # No expiration

    match = re.match(r'(\d+)([dmy])', duration_str)
    if match:
        value, unit = int(match.group(1)), match.group(2)
        now = datetime.now(timezone.utc)
        delta = timedelta()
        if unit == 'd':
            delta = timedelta(days=value)
        elif unit == 'm':
            delta = timedelta(days=value * 30)
        elif unit == 'y':
            delta = timedelta(days=value * 365)
        return now + delta
    try:
        expire_date = datetime.strptime(duration_str, '%Y-%m-%d')
        expire_date = expire_date.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        return expire_date
    except ValueError:
        return None

def generate_qr_code(link: str) -> io.BytesIO:
    qr: QRCode = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf

def generate_random_username(length: int = 8) -> str:
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def extract_subscription_data(link: str) -> Optional[Tuple[str, str]]:
    try:
        path = urlparse(link).path
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[0] == 'sub':
            username = parts[1]
            key = parts[2]
            return username, key

    except Exception:
        pass
    return None

def extract_inline_username(text: str) -> str | None:
        match = re.search(r"(?mi)Username:\s*([^\n\r]+)", text)
        if match:
            return match.group(1).strip(" `")
        match = re.search(r"(?mi)Username:\s*([^\n\r]+)", text)
        if match:
            return match.group(1).strip(" `")
        return None

def validate_username(username: str) -> bool:
    if not (USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH):
        return False
    return re.match(r'^[a-zA-Z0-9_]+$', username) is not None
