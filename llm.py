r"""Обёртка над AITunnel. Ключ берётся из .env через config.py, в терминале не светится."""
from __future__ import annotations

import json
import random

import config

BASE_URL = "https://api.aitunnel.ru/v1"


def make_ask(model: str | None = None, mock: bool = False, temperature: float = 0.3):
    """Возвращает ask(messages) -> (text, usage)."""
    if mock:
        return lambda messages: (_mock(messages), _mock_usage(messages))

    from openai import OpenAI  # ленивый импорт: mock работает без SDK

    client = OpenAI(api_key=config.get_api_key(), base_url=BASE_URL)
    model = model or config.get_model()

    def ask(messages):
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=temperature
        )
        return resp.choices[0].message.content, {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }

    return ask


def _mock(messages) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if "план" in system.lower() and "json" in system.lower():
        return json.dumps({"steps": [
            "Собрать требования", "Выбрать инструменты", "Сделать прототип",
            "Проверить на данных", "Описать результат",
        ]}, ensure_ascii=False)
    if "проверяющий" in system.lower():
        return json.dumps({"verdict": "pass", "issues": []}, ensure_ascii=False)
    return f"[MOCK] Выполнено: {last[:60].strip()}"


def _mock_usage(messages) -> dict:
    p = sum(len(m["content"]) for m in messages) // 4
    c = random.randint(40, 120)
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}
