# Testing assistant flow

## What changed
The bot now follows a deterministic assistant flow instead of relying on free-form LLM-generated client replies:
- consultation price = 2000 RUB
- no promises about exact slots
- no diagnosis
- goal is to collect complaint + phone + name and hand off to clinic admin
- after handoff, the flow closes cleanly
- a later message starts a fresh flow

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

## Current preferred model
`GigaChat`

Why it is better for the current stage:
- Russian-first model and provider
- live auth + chat request already succeeded in testing
- avoids OpenRouter free-pool rate-limit issues
- better fit for short client-facing Russian replies

## Alternative fallback
`qwen/qwen3-next-80b-a3b-instruct:free` via OpenRouter can remain as a fallback option, but free OpenRouter models were rate-limited upstream during testing.

## Expected behavior
- On greeting: ask what exactly is bothering the client.
- On price questions: explicitly say 2000 RUB.
- On slot questions: say exact slots are provided by the clinic administrator after contact.
- On symptom messages: avoid diagnosis and move toward collecting contact.
- On handoff completion: confirm transfer to administrator and close the scenario.
- On a later new message after completion: start a fresh scenario without stale state.
