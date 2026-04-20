from __future__ import annotations

from dataclasses import dataclass, field
import re

PRICE_HINT_RE = re.compile(r'(сколько.*стои|цена|стоимость)', re.IGNORECASE)
PHONE_RE = re.compile(r'\+?\d[\d\s\-()]{8,}\d')


@dataclass(slots=True)
class ConversationData:
    complaint: str | None = None
    preferred_time: str | None = None
    phone: str | None = None
    client_name: str | None = None
    notes: list[str] = field(default_factory=list)


def normalize_phone(text: str) -> str | None:
    match = PHONE_RE.search(text)
    if not match:
        return None
    digits = re.sub(r'\D', '', match.group(0))
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    if len(digits) == 11 and digits.startswith('7'):
        return '+' + digits
    return match.group(0).strip()


def is_price_question(text: str) -> bool:
    return bool(PRICE_HINT_RE.search(text))


def summarize_complaint(text: str) -> str:
    clean = ' '.join(text.split())
    return clean[:500]
