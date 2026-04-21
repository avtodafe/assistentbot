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

from .assistant_flow import (
    GREETING_REPLY,
    OUT_OF_SCOPE_REPLY,
    classify_opening,
    handle_complaint_step,
    handle_time_step,
    normalize_name,
)
from .config import Settings
from .dialogue import (
    ConversationData,
    is_consultation_related,
    is_greeting,
    normalize_phone,
    summarize_complaint,
)
from .llm import GigaChatLLM, OpenRouterLLM
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


def ensure_lead(context: ContextTypes.DEFAULT_TYPE) -> ConversationData:
    lead = context.user_data.get('lead')
    if not lead:
        lead = ConversationData()
        context.user_data['lead'] = lead
    return lead


async def llm_or_fallback_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, *, text: str) -> str | None:
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lead'] = ConversationData()
    if update.message:
        await update.message.reply_text(
            'Здравствуйте! Я ассистент Ирины. Помогу уточнить пару вопросов и передам администратору, '
            'чтобы Вас записали на консультацию. Я не врач и не ставлю диагнозы в переписке.\n\n'
            'Подскажите, пожалуйста, что именно Вас беспокоит?',
            reply_markup=ReplyKeyboardRemove(),
        )
    return COMPLAINT


async def start_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Позволяет начать сценарий без /start: первая текстовая реплика считается жалобой."""
    assert update.message is not None
    text = (update.message.text or '').strip()
    context.user_data['lead'] = ConversationData()
    lead = ensure_lead(context)

    if not is_consultation_related(text, lead) and not is_greeting(text):
        await update.message.reply_text(OUT_OF_SCOPE_REPLY, reply_markup=ReplyKeyboardRemove())
        return COMPLAINT

    decision = classify_opening(text)
    if decision.reset_lead:
        context.user_data['lead'] = ConversationData()
        lead = ensure_lead(context)
    if decision.store_complaint:
        lead.complaint = summarize_complaint(text)
    phone = normalize_phone(text)
    if phone:
        lead.phone = phone
    await update.message.reply_text(decision.reply, reply_markup=ReplyKeyboardRemove())
    return {
        'complaint': COMPLAINT,
        'preferred_time': PREFERRED_TIME,
        'phone': PHONE,
        'name': NAME,
    }[decision.next_state]


async def complaint_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    text = update.message.text or ''
    lead = ensure_lead(context)

    if not is_consultation_related(text, lead) and not is_greeting(text):
        await update.message.reply_text(OUT_OF_SCOPE_REPLY)
        return COMPLAINT

    decision = handle_complaint_step(text)
    if decision.reset_lead:
        context.user_data['lead'] = ConversationData()
        return await start(update, context)
    if decision.store_complaint:
        lead.complaint = summarize_complaint(text)
    await update.message.reply_text(decision.reply)
    return {
        'complaint': COMPLAINT,
        'preferred_time': PREFERRED_TIME,
        'phone': PHONE,
        'name': NAME,
    }[decision.next_state]


async def preferred_time_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    lead = ensure_lead(context)
    text = update.message.text or ''

    if not is_consultation_related(text, lead) and not is_greeting(text):
        await update.message.reply_text(OUT_OF_SCOPE_REPLY)
        return PREFERRED_TIME

    decision = handle_time_step(text)
    if decision.reset_lead:
        context.user_data['lead'] = ConversationData()
        return await start(update, context)
    if decision.store_time:
        lead.preferred_time = summarize_complaint(text)
    await update.message.reply_text(
        decision.reply,
        reply_markup=CONTACT_KEYBOARD if decision.ask_phone else ReplyKeyboardRemove(),
    )
    return {
        'complaint': COMPLAINT,
        'preferred_time': PREFERRED_TIME,
        'phone': PHONE,
        'name': NAME,
    }[decision.next_state]


async def phone_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    lead = ensure_lead(context)

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
    if lead.client_name:
        return await finish_lead(update, context)
    await update.message.reply_text('Как к Вам можно обращаться?', reply_markup=ReplyKeyboardRemove())
    return NAME


async def finish_lead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    settings: Settings = context.application.bot_data['settings']
    repo: LeadRepository = context.application.bot_data['repo']
    sheets: SheetsExporter | None = context.application.bot_data.get('sheets')
    lead = ensure_lead(context)

    username = update.effective_user.username if update.effective_user else None
    saved = repo.save(
        LeadPayload(
            username=f'@{username}' if username else None,
            client_name=lead.client_name or '',
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
            f"- Имя: {lead.client_name or '—'}",
            f"- Телефон: {lead.phone}",
            f"- Запрос: {lead.complaint}",
            f"- Удобное время: {lead.preferred_time or '—'}",
        ]
    )
    await context.bot.send_message(chat_id=settings.clinic_chat_id, text=card)
    await update.message.reply_text(
        'Спасибо. Я передала Вашу заявку администратору клиники. Для новой записи или нового вопроса можно написать сюда снова в любой момент.'
    )
    context.user_data.clear()
    return ConversationHandler.END


async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    lead = ensure_lead(context)

    lead.client_name = normalize_name(update.message.text or '')
    return await finish_lead(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text('Хорошо, если понадобится — напишите /start.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            'Я помогаю передать заявку на консультацию Ирине. Можно просто написать, что Вас беспокоит, '
            'или начать заново командой /start. Для отмены — /cancel.'
        )


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

    llm = None
    if settings.llm_enabled:
        if settings.llm_provider == 'gigachat':
            if not settings.llm_api_key or not settings.llm_model:
                raise ValueError('GigaChat enabled, but LLM_API_KEY or LLM_MODEL missing')
            llm = GigaChatLLM(
                credentials=settings.llm_api_key,
                model=settings.llm_model,
                scope=settings.llm_scope or 'GIGACHAT_API_PERS',
            )
        else:
            if not settings.llm_base_url or not settings.llm_api_key or not settings.llm_model:
                raise ValueError('LLM enabled, but LLM_BASE_URL or LLM_API_KEY or LLM_MODEL missing')
            llm = OpenRouterLLM(base_url=settings.llm_base_url, api_key=settings.llm_api_key, model=settings.llm_model)

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data['settings'] = settings
    app.bot_data['repo'] = repo
    if sheets:
        app.bot_data['sheets'] = sheets
    if llm:
        app.bot_data['llm'] = llm

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start_from_text),
        ],
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
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(conversation)
    return app


def main() -> None:
    settings = Settings.from_env()
    app = build_app(settings)
    app.run_polling(close_loop=False)
