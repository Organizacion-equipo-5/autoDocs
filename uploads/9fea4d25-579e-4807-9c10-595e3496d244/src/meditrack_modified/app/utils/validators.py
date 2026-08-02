"""
app/utils/validators.py
Validadores comunes reutilizables.
"""
import re
from datetime import datetime


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # HH:MM


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def is_valid_hora(hora: str) -> bool:
    """Valida formato HH:MM."""
    return bool(HORA_RE.match(hora or ""))


def is_strong_password(password: str) -> bool:
    """Mínimo 8 caracteres, al menos una letra y un número."""
    if len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit


def parse_date(date_str: str) -> datetime | None:
    """Intenta parsear fecha en formatos ISO y DD/MM/YYYY."""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def validate_required_fields(data: dict, fields: list) -> list:
    """Devuelve lista de campos requeridos que faltan."""
    return [f for f in fields if not data.get(f)]


def sanitize_string(value: str, max_len: int = 200) -> str:
    return str(value or "").strip()[:max_len]
