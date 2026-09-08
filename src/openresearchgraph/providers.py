from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import Settings


class LanguageProvider(ABC):
    is_remote: bool = False

    @abstractmethod
    async def complete(self, system: str, prompt: str) -> str:
        """Return a text completion without leaking provider details into agents."""


class DeterministicProvider(LanguageProvider):
    """Offline provider used for tests, demos, and reproducible evaluation."""

    async def complete(self, system: str, prompt: str) -> str:
        payload = {"mode": "deterministic", "system": system[:48], "input": prompt[:160]}
        return json.dumps(payload, ensure_ascii=False)


class OpenAICompatibleProvider(LanguageProvider):
    is_remote = True

    def __init__(self, settings: Settings) -> None:
        if not settings.use_remote_llm:
            raise ValueError("Remote LLM configuration is incomplete")
        self._url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        self._model = settings.llm_model
        self._api_key = settings.llm_api_key

    async def complete(self, system: str, prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self._url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"])


def build_provider(settings: Settings) -> LanguageProvider:
    if settings.use_remote_llm:
        return OpenAICompatibleProvider(settings)
    return DeterministicProvider()
