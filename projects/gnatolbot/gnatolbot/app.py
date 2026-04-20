from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import Settings
from .dialogue import ConversationData, is_price_question, normalize_phone, summarize_complaint
from .models import Database
from .storage import LeadPayload, LeadRepository, SheetsExporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMPLAINT, PREFERRED_TIME, PHONE, NAME = range(4)
CONTACT_KEYBOARD: Final = ReplyKeyboardMarkup(
    [[{'text': 'Поделиться контактом', 'request_contact': True}]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lead'] = ConversationData()
    await update.message.reply_text(
        'Здравствуйте! Я ассистент Ирины. Помогу уточнить пару вопросов и передам администратору, '
        'чтобы Вас записали на консультацию. Я не врач и не ставлю диагнозы в переписке.\n\n'
        'Подскажите, пожалуйста, что именно Вас беспокоит?',
        reply_markup=ReplyKeyboardRemove(),
    )
    return COMPLAINT


async def complaint_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    text = update.message.text or ''
    if is_price_question(text):
        await update.message.reply_text(
            'Стоимость консультации подскажет администратор — она зависит от клиники, '
            'в которую Вас смогут записать.\n\n'
            'Подскажите, пожалуйста, что именно Вас беспокоит?'
        )
        return COMPLAINT

    lead: ConversationData = context.user_data['lead']
    lead.complaint = summarize_complaint(text)
    await update.message.reply_text(
        'Подскажите, пожалуйста, когда Вам удобнее: сегодня, завтра или в ближайшие дни? '
        'Если есть предпочтение, можно сразу указать время: утро, день или вечер.'
    )
    return PREFERRED_TIME


async def preferred_time_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    lead: ConversationData = context.user_data['lead']
    lead.preferred_time = summarize_complaint(update.message.text or '')
    await update.message.reply_text(
        'Напишите, пожалуйста, номер телефона для связи или нажмите «Поделиться контактом».',
        reply_markup=CONTACT_KEYBOARD,
    )
    return PHONE


async def phone_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    lead: ConversationData = context.user_data['lead']

    phone = None
    if update.message.contact and update.message.contact.phone_number:
        phone = normalize_phone(update.message.contact.phone_number)
    if not phone:
        phone = normalize_phone(update.message.text or '')
    if not phone:
        await update.message.reply_text(
            'Не вижу номер телефона. Напишите его, пожалуйста, в формате +7..., '
            'или нажмите «Поделиться контактом».'
        )
        return PHONE

    lead.phone = phone
    await update.message.reply_text('Как к Вам можно обращаться?', reply_markup=ReplyKeyboardRemove())
    return NAME


async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    settings: Settings = context.application.bot_data['settings']
    repo: LeadRepository = context.application.bot_data['repo']
    sheets: SheetsExporter | None = context.application.bot_data.get('sheets')
    lead: ConversationData = context.user_data['lead']

    lead.client_name = summarize_complaint(update.message.text or '')
    username = update.effective_user.username if update.effective_user else None
    saved = repo.save(
        LeadPayload(
            username=f'@{username}' if username else None,
            client_name=lead.client_name,
            phone=lead.phone or '',
            complaint=lead.complaint or '',
            preferred_time=lead.preferred_time or '',
        )
    )

    if sheets:
        try:
            sheets.append(saved)
        except Exception as exc:  # noqa: BLE001
            logger.exception('Failed to export lead to sheets: %s', exc)

    card = '\n'.join(
        [
            'Лид от Ирины',
            '- Канал: TG',
            f"- Username: @{username}" if username else '- Username: —',
            f"- Имя: {lead.client_name}",
            f"- Телефон: {lead.phone}",
            f"- Запрос: {lead.complaint}",
            f"- Удобное время: {lead.preferred_time}",
        ]
    )
    await context.bot.send_message(chat_id=settings.clinic_chat_id, text=card)
    await update.message.reply_text(
        'Спасибо! Передаю информацию администратору. Он обычно связывается в течение часа.'
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text('Хорошо, если понадобится — напишите /start.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


def build_app(settings: Settings) -> Application:
    db_path = settings.db_path
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parents[1] / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(f'sqlite:///{db_path}')
    db.create()
    repo = LeadRepository(db)
    sheets = None
    if settings.google_sheets_enabled:
        if not settings.google_service_account_json or not settings.google_sheet_id:
            raise ValueError('Google Sheets enabled, but GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SHEET_ID missing')
        sheets = SheetsExporter(settings.google_service_account_json, settings.google_sheet_id, settings.timezone)

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data['settings'] = settings
    app.bot_data['repo'] = repo
    if sheets:
        app.bot_data['sheets'] = sheets

    conversation = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            COMPLAINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, complaint_step)],
            PREFERRED_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, preferred_time_step)],
            PHONE: [
                MessageHandler(filters.CONTACT, phone_step),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_step),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )
    app.add_handler(conversation)
    return app


def main() -> None:
    settings = Settings.from_env()
    app = build_app(settings)
    app.run_polling(close_loop=False)
