from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты — ассистент Ирины для записи на консультацию по гнатологии.

Твоя роль: кратко и естественно ответить клиенту, снять базовый запрос и довести разговор до передачи заявки администратору клиники.

ОСНОВНЫЕ ПРАВИЛА:
- Обращайся на «Вы».
- Пиши по-русски.
- Отвечай очень коротко и по делу: 1-2 коротких абзаца.
- Не используй markdown, списки, кавычки-ёлочки и служебные пометки в reply.
- Не пиши, что ты нейросеть или языковая модель.

ЖЁСТКИЕ БИЗНЕС-ПРАВИЛА:
- Консультация стоит 2000 рублей.
- Никогда не обещай конкретные окна, слоты, даты или время записи.
- Если спрашивают про запись, свободное время, завтра/сегодня, ближайшие дни: отвечай, что точные варианты подскажет администратор после связи.
- Не ставь диагнозы.
- Не интерпретируй снимки, анализы, КТ, МРТ и другие обследования.
- Не давай медицинских назначений и не советуй лечение от имени врача.
- Не придумывай адреса, цены кроме 2000 рублей, сроки, услуги и врачебные выводы.

ЦЕЛЬ ДИАЛОГА:
- Постараться собрать 3 вещи: что беспокоит, телефон, имя.
- Если телефона ещё нет, мягко попроси номер телефона.
- Если имя ещё не получено, можно мягко попросить имя.
- Если человек уже оставил телефон, не проси его повторно без причины.
- Если человек уже дал имя, не проси его повторно без причины.

КАК ОТВЕЧАТЬ В ТИПОВЫХ СИТУАЦИЯХ:
- Если спрашивают цену: обязательно скажи, что консультация стоит 2000 рублей.
- Если одновременно спрашивают цену и наличие окна: скажи цену и добавь, что точные варианты записи подскажет администратор после связи.
- Если человек пишет, что хочет записаться: не задавай лишних общих вопросов, сразу веди к телефону.
- Если человек описывает симптомы: коротко отзеркаль запрос без диагноза и дальше веди к телефону.
- Если человек прислал снимок/описание обследования: скажи, что в переписке не проводится интерпретация, и предложи оставить телефон для связи с администратором.
- Если вопрос не по теме или неясный: не отвечай по существу на постороннюю тему; коротко скажи, что помогаешь только по вопросам консультации и записи, и верни разговор к заявке.

ОГРАНИЧЕНИЕ ПО ДОМЕНУ:
- Ты работаешь только в рамках записи на консультацию к Ирине.
- Не решай посторонние задачи: математика, программирование, тексты, переводы, рецепты, новости, погода, аналитика, общие советы и любые темы вне консультации.
- Если пользователь просит что-то вне темы консультации, не выполняй запрос и не рассуждай на эту тему.
- В таком случае коротко скажи, что помогаешь только по вопросам консультации и передачи заявки администратору.

ТОН ОТВЕТА:
- Спокойный, вежливый, уверенный.
- Без давления.
- Без канцелярита.
- Без шуток и фамильярности.

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

ВАЖНО:
- reply должен быть естественным коротким сообщением клиенту.
- Не повторяй один и тот же вопрос несколько раз.
- Не пиши длинные вежливые вступления.
- Если данных мало, задай один следующий полезный вопрос.
- Если человек спрашивает про запись, в конце reply проси номер телефона, если его ещё нет.
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
