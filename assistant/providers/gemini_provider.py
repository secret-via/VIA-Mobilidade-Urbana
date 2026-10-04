"""Provedor Google Gemini (camada gratuita) via REST puro - sem SDK extra,
usando `requests` (já é dependência do projeto). Se a chamada falhar por
qualquer motivo (sem chave, sem internet, limite excedido), cai para o
NullProvider - o assistente nunca fica indisponível por causa da IA.
"""

import json
import os
import time

from .base import SYSTEM_PROMPT, LLMProvider, localize_timestamps

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRYABLE_STATUS = {429, 500, 503}


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()

    def available(self):
        return bool(self.api_key)

    def explain(self, question, data):
        if not self.available():
            return self._fallback(question, data)

        import requests

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Pergunta do usuário: {question}\n\n"
            f"Dados (única fonte de verdade, já calculados pelo sistema, horários já em "
            f"horário de Brasília): {json.dumps(localize_timestamps(data), ensure_ascii=False, default=str)}"
        )
        url = _ENDPOINT.format(model=self.model)
        body = {"contents": [{"parts": [{"text": prompt}]}]}

        # Uma nova tentativa em erros transitórios (modelo sobrecarregado,
        # limite de taxa) antes de cair para o NullProvider - visto na prática
        # que a API do Gemini responde 503 "high demand" ocasionalmente.
        for attempt in range(2):
            try:
                response = requests.post(url, params={"key": self.api_key}, json=body, timeout=25)
                if response.status_code in _RETRYABLE_STATUS and attempt == 0:
                    time.sleep(1.5)
                    continue
                response.raise_for_status()
                payload = response.json()
                text = payload["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip() or self._fallback(question, data)
            except Exception:
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                return self._fallback(question, data)

        return self._fallback(question, data)

    @staticmethod
    def _fallback(question, data):
        from .null_provider import NullProvider

        return NullProvider().explain(question, data)
