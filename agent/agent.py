from collections import Counter


class TrafficAgent:
    """Coordena regras locais; não é um chatbot nem substitui o detector."""
    def __init__(self, events, memory, collector=None, low_confidence=0.50):
        self.events, self.memory, self.collector = events, memory, collector
        self.low_confidence = low_confidence
        self.low_by_class = Counter()
        self.congested = False

    def observe(self, frame, detection, congestion):
        confidence = detection["confidence"]
        if confidence < self.low_confidence:
            self.low_by_class[detection["class_name"]] += 1
            event = self.events.emit("LOW_CONFIDENCE", **detection)
            self.memory.remember("LOW_CONFIDENCE", **detection)
            if self.collector:
                self.collector.collect(frame, detection, reason="low_confidence")
            return event
        level = congestion["level"]
        now_congested = level in {"moderado", "alto"}
        if now_congested != self.congested:
            self.congested = now_congested
            event_type = "CONGESTION_STARTED" if now_congested else "CONGESTION_ENDED"
            return self.events.emit(event_type, congestion=congestion)
        return None

    def explanation(self):
        if not self.low_by_class:
            return "Agente ativo: ainda não há baixa confiança recorrente."
        label, count = self.low_by_class.most_common(1)[0]
        return f"Identifiquei baixa confiança recorrente na classe {label}: {count} casos observados."
