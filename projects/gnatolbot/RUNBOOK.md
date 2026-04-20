# RUNBOOK

## Что нужно подготовить
1. Новый токен Telegram-бота от BotFather.
2. `CLINIC_CHAT_ID` — id группы/чата, куда отправлять лиды.
3. (Опционально) Google Sheets:
   - созданная таблица,
   - service account JSON,
   - доступ service account к таблице,
   - `GOOGLE_SHEET_ID`.
4. Доступ к VPS по SSH или репозиторий, который можно клонировать на сервер.

## Куда присылать новый токен
Не в обычный чат в открытом виде, если можно этого избежать. Лучше так:
- либо сразу положить его в `.env` на VPS/локальной машине,
- либо прислать один раз для настройки и потом сразу перевыпустить после теста.

## Как получить `CLINIC_CHAT_ID`
Простой способ:
1. Добавить бота в нужную группу/чат.
2. Написать в группу любое сообщение.
3. Временно запустить бота и посмотреть `getUpdates`/логи, либо использовать отдельный debug-скрипт.

## Что нужно для Google Sheets
1. Создать Google Cloud project.
2. Включить Google Sheets API.
3. Создать service account.
4. Скачать JSON-ключ.
5. Поделиться таблицей на email service account.
6. В `.env` выставить:
   - `GOOGLE_SHEETS_ENABLED=true`
   - `GOOGLE_SHEET_ID=...`
   - `GOOGLE_SERVICE_ACCOUNT_JSON='{...json...}'`

## Локальный запуск
```bash
cd /opt/gnatolbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполнить .env
python -m gnatolbot
```

## Запуск через systemd
```bash
sudo cp systemd/gnatolbot.service /etc/systemd/system/gnatolbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now gnatolbot
sudo systemctl status gnatolbot
```

## Запуск через Docker Compose
```bash
docker compose up -d --build
```

## GitHub-репозиторий
Имеет смысл создать отдельный private repo и хранить там код.
В репозиторий не коммитить:
- `.env`
- service-account JSON
- `data/*.db`

## Короткий план запуска
1. Создать новый токен.
2. Создать private repo на GitHub.
3. Залить туда `projects/gnatolbot`.
4. Получить `CLINIC_CHAT_ID`.
5. Решить: Sheets сразу или позже.
6. Дать SSH на VPS или самому клонировать repo на VPS.
7. Заполнить `.env`.
8. Запустить через systemd или docker compose.
9. Протестировать диалог.
10. Перевыпустить токен, если он где-то светился.
