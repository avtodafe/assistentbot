# Testing free-model replies

## What changed
The bot can now optionally use a free external chat-completions model to generate more flexible replies while still enforcing hard business rules:
- consultation price = 2000 RUB
- no promises about exact slots
- no diagnosis
- goal is to collect complaint + phone + name and hand off to clinic admin

## Env
Add to `.env`:

```env
LLM_ENABLED=true
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=...
LLM_MODEL=qwen/qwen3-next-80b-a3b-instruct:free
```

## Suggested test prompts
1. `Здравствуйте, сколько стоит консультация?`
2. `А на завтра есть время?`
3. `Щелкает челюсть, хочу записаться`
4. `Есть снимок, но не понимаю что делать`
5. `Хочу консультацию, мой номер +7 900 000 00 00`

## Chosen free model
`qwen/qwen3-next-80b-a3b-instruct:free`

Why this one:
- free on OpenRouter
- instruct-tuned and strong enough for short client-facing Russian replies
- better fit for flexible intent handling than tiny free models
- simpler and more predictable than using the generic `openrouter/free` router

## Expected behavior
- On price questions: should explicitly say 2000 RUB.
- On slot questions: should say exact slots are provided by the clinic administrator after contact.
- On symptom messages: should avoid diagnosis and move toward collecting contact.
- On mixed/free-form inputs: should stay short and politely steer to lead capture.
