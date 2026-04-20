from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты — ассистент Ирины для записи на консультацию по гнатологии.

Задача: отвечать вежливо, кратко, по-русски и доводить диалог до передачи заявки администратору клиники.

ЖЁСТКИЕ ПРАВИЛА:
- Консультация стоит 2000 рублей.
- Никогда не обещай конкретные окна/слоты/даты.
- Если спрашивают про запись или свободное время, отвечай: точные варианты предложит администратор после связи.
- Не ставь диагнозы и не интерпретируй снимки.
- Цель: собрать, если возможно, 3 вещи: что беспокоит, телефон, имя.
- Если телефона ещё нет, старайся мягко попросить телефон.
- Если имя ещё не получено, можно мягко попросить имя.
- Не пиши длинно. 1-3 коротких абзаца максимум.

Верни JSON-объект БЕЗ markdown и БЕЗ пояснений.
Схема:
{
  "reply": "текст ответа пользователю",
  "detected": {
    "complaint": "... или пустая строка",
    "preferred_time": "... или пустая строка",
    "name": "... или пустая строка",
    "phone": "... или пустая строка"
  },
  "should_ask_phone": true,
  "should_ask_name": true
}
""".strip()


@dataclass(slots=True)
class LLMResult:
    reply: str
    complaint: str = ""
    preferred_time: str = ""
    name: str = ""
    phone: str = ""
    should_ask_phone: bool = False
    should_ask_name: bool = False


class BaseLLM:
    async def respond(
        self,
        *,
        user_text: str,
        complaint: str,
        preferred_time: str,
        phone: str,
        name: str,
    ) -> LLMResult:
        raise NotImplementedError

    @staticmethod
    def _parse_result(content: str) -> LLMResult:
        logger.info("LLM raw response: %s", content)
        parsed = json.loads(content)
        detected = parsed.get("detected", {}) or {}
        return LLMResult(
            reply=(parsed.get("reply") or "").strip(),
            complaint=(detected.get("complaint") or "").strip(),
            preferred_time=(detected.get("preferred_time") or "").strip(),
            name=(detected.get("name") or "").strip(),
            phone=(detected.get("phone") or "").strip(),
            should_ask_phone=bool(parsed.get("should_ask_phone")),
            should_ask_name=bool(parsed.get("should_ask_name")),
        )

    @staticmethod
    def _user_payload(*, user_text: str, complaint: str, preferred_time: str, phone: str, name: str) -> str:
        return json.dumps(
            {
                "message": user_text,
                "known": {
                    "complaint": complaint,
                    "preferred_time": preferred_time,
                    "phone": phone,
                    "name": name,
                },
            },
            ensure_ascii=False,
        )


class OpenRouterLLM(BaseLLM):
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def respond(
        self,
        *,
        user_text: str,
        complaint: str,
        preferred_time: str,
        phone: str,
        name: str,
    ) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._user_payload(user_text=user_text, complaint=complaint, preferred_time=preferred_time, phone=phone, name=name)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_result(content)


class GigaChatLLM(BaseLLM):
    def __init__(self, *, credentials: str, model: str, scope: str = 'GIGACHAT_API_PERS') -> None:
        self.credentials = credentials
        self.model = model
        self.scope = scope
        self.auth_url = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
        self.chat_url = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            self.auth_url,
            headers={
                'Authorization': f'Basic {self.credentials}',
                'RqUID': str(uuid.uuid4()),
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
            data={'scope': self.scope},
        )
        response.raise_for_status()
        return response.json()['access_token']

    async def respond(
        self,
        *,
        user_text: str,
        complaint: str,
        preferred_time: str,
        phone: str,
        name: str,
    ) -> LLMResult:
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': self._user_payload(user_text=user_text, complaint=complaint, preferred_time=preferred_time, phone=phone, name=name)},
            ],
            'temperature': 0.2,
            'top_p': 0.9,
            'max_tokens': 400,
        }
        async with httpx.AsyncClient(timeout=60, verify=False) as client:
            token = await self._get_access_token(client)
            response = await client.post(
                self.chat_url,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = data['choices'][0]['message']['content']
        return self._parse_result(content)
