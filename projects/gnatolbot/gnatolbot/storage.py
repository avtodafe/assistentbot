from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from .models import Database, Lead


@dataclass(slots=True)
class LeadPayload:
    username: str | None
    client_name: str | None
    phone: str
    complaint: str
    preferred_time: str
    channel: str = 'telegram'


class LeadRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, payload: LeadPayload) -> Lead:
        with self.db.SessionLocal() as session:
            lead = Lead(**asdict(payload))
            session.add(lead)
            session.commit()
            session.refresh(lead)
            return lead


class SheetsExporter:
    HEADERS = [
        'created_at_msk',
        'channel',
        'username',
        'name',
        'phone',
        'complaint',
        'preferred_time',
        'status',
    ]

    def __init__(self, credentials_json: str, sheet_id: str, timezone: str) -> None:
        info = json.loads(credentials_json)
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(sheet_id).sheet1
        self.timezone = ZoneInfo(timezone)
        self._ensure_headers()

    def _ensure_headers(self) -> None:
        values = self.sheet.row_values(1)
        if values != self.HEADERS:
            self.sheet.update('A1:H1', [self.HEADERS])

    def append(self, lead: Lead) -> None:
        created_at = lead.created_at.replace(tzinfo=ZoneInfo('UTC')).astimezone(self.timezone)
        row = [
            created_at.strftime('%Y-%m-%d %H:%M:%S'),
            lead.channel,
            lead.username or '',
            lead.client_name or '',
            lead.phone,
            lead.complaint,
            lead.preferred_time,
            lead.status,
        ]
        self.sheet.append_row(row, value_input_option='USER_ENTERED')
