import json
import unittest
from pathlib import Path

from agent.memory import AgentMemory
from learning.evaluator import compare
from learning.sampler import LearningSampler
from traffic.events import EventLogger
from utils.counting import LineCounter
from utils.traffic import calculate_congestion


class CoreTests(unittest.TestCase):
    def test_line_counter_counts_once(self):
        counter = LineCounter({"entrada": ((0, 0), (10, 0))})
        counter.update(1, "car", (5, -1)); counter.update(1, "car", (5, 1)); counter.update(1, "car", (5, -1))
        self.assertEqual(counter.totals["entrada"], 1)

    def test_structured_event_and_memory_persist(self):
        event_path = Path(__file__).parent / "_events_runtime.jsonl"
        memory_path = Path(__file__).parent / "_memory_runtime.jsonl"
        try:
            EventLogger(event_path).emit("LOW_CONFIDENCE", confidence=.4)
            memory = AgentMemory(memory_path); memory.remember("LOW_CONFIDENCE", confidence=.4)
            self.assertEqual(json.loads(event_path.read_text())['type'], "LOW_CONFIDENCE")
            self.assertEqual(memory.recent()[0]['confidence'], .4)
        finally:
            for path in (event_path, memory_path):
                if path.exists(): path.unlink()

    def test_sampler_deduplicates_temporally(self):
        sampler = LearningSampler(.5, .65, 60, 2)
        record = {"class_name": "bike", "confidence": .4}
        self.assertTrue(sampler.should_collect(record)); self.assertFalse(sampler.should_collect(record))

    def test_candidate_requires_improvement(self):
        self.assertFalse(compare({"map50_95": .70}, {"map50_95": .705}, .01)["approved"])

    def test_congestion_is_marked_estimated(self):
        self.assertTrue(calculate_congestion(10, stopped_vehicles=5)["estimated"])


if __name__ == "__main__": unittest.main()
