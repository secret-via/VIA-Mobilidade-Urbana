"""Interface comum a qualquer provedor de IA — permite trocar o provedor
(Gemini, Ollama, outro) sem alterar nada fora deste pacote.

Regra de ouro: um LLMProvider nunca gera os números. Ele só recebe um JSON
já calculado pelo assistant/query_engine.py e o transforma em texto natural.
"""

import re
from abc import ABC, abstractmethod
from datetime import datetime

from config.config import BR_TIMEZONE

SYSTEM_PROMPT = (
    "Você é o assistente de dados do VIA, um painel de monitoramento de trânsito urbano. "
    "Você só pode usar os números presentes no campo 'dados' (JSON) fornecido nesta mensagem. "
    "Nunca invente, estime ou arredonde valores que não estejam explicitamente nesse JSON. "
    "Todos os horários no JSON já estão em horário de Brasília (UTC-3) e formatados como "
    "DD/MM/AAAA HH:MM - use-os exatamente como estão escritos, nunca tente converter fuso "
    "horário nem reinterpretar a hora. "
    "Se o campo has_data for false, diga claramente que não há dados suficientes para essa "
    "pergunta - não tente adivinhar um número mesmo assim. Responda sempre em português do "
    "Brasil, em no máximo 3 frases, tom direto e objetivo, sem repetir o JSON bruto na resposta. "
    "Fale como para um engenheiro de tráfego, não como um programador: nunca cite nomes de campos "
    "do JSON (como total_vehicles), códigos de evento em maiúsculas (como CONGESTION_STARTED) nem "
    "identificadores técnicos (como cam_local) - diga 'congestionamento iniciado', 'veículo parado', "
    "'a câmera local' e use o nome da câmera quando houver."
)

_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def localize_timestamps(value):
    """Converte recursivamente qualquer string ISO-8601 com fuso (como as
    gravadas em UTC por traffic/events.py) para horário de Brasília já
    formatado como texto legível, antes de mandar os dados para uma IA
    generativa.

    Sem isso, o JSON levava horários crus em UTC (ex. "19:45:00+00:00") para
    o prompt, e a IA às vezes esquecia de subtrair as 3 horas e às vezes não
    - por isso as respostas erravam o horário de forma inconsistente. Com o
    valor já convertido, a IA só precisa copiar o texto, nunca fazer conta de
    fuso horário sozinha.
    """
    if isinstance(value, dict):
        return {key: localize_timestamps(item) for key, item in value.items()}
    if isinstance(value, list):
        return [localize_timestamps(item) for item in value]
    if isinstance(value, str) and _ISO_TIMESTAMP_RE.match(value):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return moment.astimezone(BR_TIMEZONE).strftime("%d/%m/%Y %H:%M (horário de Brasília)")
        except ValueError:
            return value
    return value


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def available(self):
        """True se este provedor está configurado e utilizável agora."""

    def extract_intent(self, text, known_cameras):
        """Extração de intenção via IA - usada apenas quando o parser local
        (assistant/nlu/parser.py) não consegue resolver a pergunta com
        confiança. Implementação opcional; None desativa esse caminho.
        """
        return None

    @abstractmethod
    def explain(self, question, data):
        """Transforma o resultado (já calculado) de assistant/query_engine.py
        em uma resposta em português. Deve sempre retornar texto, nunca
        lançar exceção para o chamador (falhas viram fallback)."""
