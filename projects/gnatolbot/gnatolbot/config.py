from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    bot_token: str
    clinic_chat_id: str
    bot_username: str
    db_path: Path
    google_sheets_enabled: bool
    google_sheet_id: str | None
    google_service_account_json: str | None
    timezone: str
    llm_enabled: bool
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None


    @classmethod
    def from_env(cls) -> 'Settings':
        bot_token = os.getenv('BOT_TOKEN', '').strip()
        clinic_chat_id = os.getenv('CLINIC_CHAT_ID', '').strip()
        if not bot_token:
            raise ValueError('BOT_TOKEN is required')
        if not clinic_chat_id:
            raise ValueError('CLINIC_CHAT_ID is required')
        return cls(
            bot_token=bot_token,
            clinic_chat_id=clinic_chat_id,
            bot_username=os.getenv('BOT_USERNAME', 'gnatolbot').strip() or 'gnatolbot',
            db_path=Path(os.getenv('DB_PATH', 'data/leads.db')).expanduser(),
            google_sheets_enabled=os.getenv('GOOGLE_SHEETS_ENABLED', 'false').lower() == 'true',
            google_sheet_id=os.getenv('GOOGLE_SHEET_ID') or None,
            google_service_account_json=os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON') or None,
            timezone=os.getenv('TIMEZONE', 'Europe/Moscow').strip() or 'Europe/Moscow',
            llm_enabled=os.getenv('LLM_ENABLED', 'false').lower() == 'true',
            llm_base_url=os.getenv('LLM_BASE_URL') or None,
            llm_api_key=os.getenv('LLM_API_KEY') or None,
            llm_model=os.getenv('LLM_MODEL') or None,
        )
