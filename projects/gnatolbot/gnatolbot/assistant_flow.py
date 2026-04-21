from __future__ import annotations

from dataclasses import dataclass

from .dialogue import has_time_reference, is_greeting, is_price_question, normalize_phone, summarize_complaint

CONSULTATION_PRICE_TEXT = 'Консультация стоит 2000 рублей.'
GREETING_REPLY = 'Здравствуйте. Я ассистент Ирины по записи на консультацию. Подскажите, пожалуйста, что именно Вас беспокоит?'
OUT_OF_SCOPE_REPLY = (
    'Я помогаю только по вопросам консультации у Ирины и передаче заявки администратору клиники. '
    'Если хотите записаться, напишите, пожалуйста, что Вас беспокоит, или оставьте номер телефона для связи.'
)
TIME_REPLY = (
    'Точные варианты записи подскажет администратор клиники после связи с Вами. '
    'Напишите, пожалуйста, номер телефона для связи, и я передам заявку.'
)
PRICE_REPLY = (
    f'{CONSULTATION_PRICE_TEXT} '
    'Если хотите, я могу передать Вашу заявку администратору клиники. '
    'Напишите, пожалуйста, номер телефона для связи.'
)
PHOTO_REPLY = (
    'В переписке мы не интерпретируем снимки и не ставим диагнозы. '
    'Если хотите записаться на консультацию, напишите, пожалуйста, что Вас беспокоит, и оставьте номер телефона для связи.'
)


@dataclass(slots=True)
class FlowDecision:
    reply: str
    next_state: str
    store_complaint: bool = False
    store_time: bool = False
    ask_phone: bool = False
    ask_name: bool = False
    finish: bool = False
    reset_lead: bool = False


def classify_opening(text: str) -> FlowDecision:
    clean = ' '.join((text or '').split())
    phone = normalize_phone(clean)

    if not clean or is_greeting(clean):
        return FlowDecision(reply=GREETING_REPLY, next_state='complaint', reset_lead=True)

    if is_price_question(clean) and has_time_reference(clean):
        return FlowDecision(
            reply=f'{CONSULTATION_PRICE_TEXT} Точные варианты записи подскажет администратор после связи. Напишите, пожалуйста, номер телефона для связи.',
            next_state='phone',
            ask_phone=True,
        )

    if is_price_question(clean):
        return FlowDecision(reply=PRICE_REPLY, next_state='phone', ask_phone=True)

    if has_time_reference(clean):
        return FlowDecision(reply=TIME_REPLY, next_state='phone', ask_phone=True)

    if phone:
        return FlowDecision(reply='Спасибо. Как к Вам можно обращаться?', next_state='name', ask_name=True)

    return FlowDecision(
        reply='Подскажите, пожалуйста, что именно Вас беспокоит?',
        next_state='complaint',
        store_complaint=False,
    )


def handle_complaint_step(text: str) -> FlowDecision:
    clean = ' '.join((text or '').split())
    if not clean or is_greeting(clean):
        return FlowDecision(reply=GREETING_REPLY, next_state='complaint', reset_lead=True)

    if is_price_question(clean) and has_time_reference(clean):
        return FlowDecision(
            reply=f'{CONSULTATION_PRICE_TEXT} Точные варианты записи подскажет администратор после связи. Напишите, пожалуйста, номер телефона для связи.',
            next_state='phone',
            ask_phone=True,
            store_complaint=False,
        )

    if is_price_question(clean):
        return FlowDecision(reply=PRICE_REPLY, next_state='phone', ask_phone=True)

    return FlowDecision(
        reply='Подскажите, пожалуйста, есть ли пожелания по времени записи: будни или выходные, утро, день или вечер?',
        next_state='preferred_time',
        store_complaint=True,
    )


def handle_time_step(text: str) -> FlowDecision:
    clean = ' '.join((text or '').split())
    if not clean or is_greeting(clean):
        return FlowDecision(reply=GREETING_REPLY, next_state='complaint', reset_lead=True)

    if is_price_question(clean):
        return FlowDecision(reply=PRICE_REPLY, next_state='phone', ask_phone=True)

    return FlowDecision(
        reply='Напишите, пожалуйста, номер телефона для связи или нажмите «Поделиться контактом».',
        next_state='phone',
        store_time=True,
        ask_phone=True,
    )


def normalize_name(text: str) -> str:
    return summarize_complaint(text or '')
