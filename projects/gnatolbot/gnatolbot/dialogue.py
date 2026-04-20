from __future__ import annotations

from dataclasses import dataclass, field
import re

PRICE_HINT_RE = re.compile(r'(сколько.*стои|цена|стоимость)', re.IGNORECASE)
PHONE_RE = re.compile(r'\+?\d[\d\s\-()]{8,}\d')
TIME_HINT_RE = re.compile(r'(сегодня|завтра|в ближайшие дни|утр|дн[её]м|вечер|будни|выходн|когда удобно|окно|мест|запис)', re.IGNORECASE)
CONSULTATION_HINT_RE = re.compile(
    r'('
    r'запис|консультац|при[её]м|администратор|окно|время|стоим|цена|'
    r'челюст|гнатолог|прикус|щ[её]лка|щелкает|боль|болит|дискомфорт|'
    r'сустав|рот|зуб|зубы|скрежет|брукс|к[тт]|мрт|сним|обследован|'
    r'телефон|номер|контакт|меня зовут|мо[её] имя|как ко мне обращаться'
    r')',
    re.IGNORECASE,
)
OUT_OF_SCOPE_RE = re.compile(
    r'('
    r'формул|анкар|python|питон|код|программ|скрипт|sql|excel|таблиц|'
    r'курс валют|погод|новост|фильм|музык|рецепт|анекдот|шутк|'
    r'перевед|реферат|сочинен|математ|интеграл|уравнен|домашк|'
    r'биткоин|акци|крипт|гороскоп|биограф|истор|политик'
    r')',
    re.IGNORECASE,
)


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


def has_time_reference(text: str) -> bool:
    return bool(TIME_HINT_RE.search(text))


def is_consultation_related(text: str, lead: ConversationData | None = None) -> bool:
    clean = ' '.join((text or '').split())
    if not clean:
        return False

    if PHONE_RE.search(clean):
        return True

    if OUT_OF_SCOPE_RE.search(clean) and not CONSULTATION_HINT_RE.search(clean):
        return False

    if CONSULTATION_HINT_RE.search(clean) or TIME_HINT_RE.search(clean):
        return True

    if lead and (lead.complaint or lead.phone or lead.client_name or lead.preferred_time):
        short = clean.strip()
        if len(short) <= 80:
            return True

    return False


def summarize_complaint(text: str) -> str:
    clean = ' '.join(text.split())
    return clean[:500]
