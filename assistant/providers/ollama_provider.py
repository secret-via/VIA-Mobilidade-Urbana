"""Provedor local via Ollama (100% gratuito e offline) - alternativa ao
Gemini para quando não há internet disponível na apresentação. Só é usado se
AI_PROVIDER=ollama no .env; não é o padrão do projeto.
"""

import json
import os

from .base import SYSTEM_PROMPT, LLMProvider, localize_timestamps


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

    def available(self):
        import requests

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def explain(self, question, data):
        import requests

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Pergunta do usuário: {question}\n\n"
            f"Dados (única fonte de verdade, já calculados pelo sistema, horários já em "
            f"horário de Brasília): {json.dumps(localize_timestamps(data), ensure_ascii=False, default=str)}"
        )

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=30,
            )
            response.raise_for_status()
            text = response.json().get("response", "").strip()
            return text or self._fallback(question, data)
        except Exception:
            return self._fallback(question, data)

    @staticmethod
    def _fallback(question, data):
        from .null_provider import NullProvider

        return NullProvider().explain(question, data)
