"""Seleciona o provedor de IA configurado (AI_PROVIDER no .env). Nunca lança
exceção - qualquer problema (dependência ausente, provedor indisponível)
cai para o NullProvider, que sempre responde por template.
"""

import os


def get_provider():
    backend = os.getenv("AI_PROVIDER", "none").strip().lower()

    try:
        if backend == "gemini":
            from .gemini_provider import GeminiProvider

            provider = GeminiProvider()
            if provider.available():
                return provider
        elif backend == "ollama":
            from .ollama_provider import OllamaProvider

            provider = OllamaProvider()
            if provider.available():
                return provider
    except Exception:
        pass

    from .null_provider import NullProvider

    return NullProvider()
