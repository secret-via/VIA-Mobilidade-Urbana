import unittest
from datetime import date, time
from unittest import mock

from assistant import chat_service
from assistant.nlu.parser import parse


class TriageTests(unittest.TestCase):
    DADOS = [
        "Qual foi o horário de pico hoje?", "Resuma o fluxo da última semana", "Houve alguma ocorrência incomum?",
        "e as ocorrências?", "quantos carros passaram em 20/09/2026?", "compare 8h às 10h com 14h às 16h",
        "e de manhã?", "qual câmera tem mais fluxo?", "e ontem?", "Quantas motos tem na camera local",
        "boa tarde, qual o pico de hoje?",
    ]
    FORA = [
        "o via é um bom app?", "qual a capital da França?", "me conta uma piada", "que horas são?",
        "como faço um bolo", "você é uma IA?", "quanto custa o plano?", "o dia está bonito",
    ]

    def test_data_questions_go_to_the_engine(self):
        for q in self.DADOS:
            self.assertEqual(chat_service.triage(q), "data", q)

    def test_off_topic_never_reaches_the_engine(self):
        for q in self.FORA:
            self.assertEqual(chat_service.triage(q), "out_of_scope", q)

    def test_greetings_and_thanks(self):
        for q in ("oi", "Olá!", "bom dia", "boa tarde", "boa noite"):
            self.assertEqual(chat_service.triage(q), "greeting", q)
        for q in ("obrigado!", "valeu"):
            self.assertEqual(chat_service.triage(q), "thanks", q)

    def test_off_topic_answer_has_no_numbers_and_no_query(self):
        with mock.patch.object(chat_service, "compute_summary", side_effect=AssertionError("não deve consultar")), \
                mock.patch.object(chat_service, "get_occurrences", side_effect=AssertionError("não deve consultar")), \
                mock.patch.object(chat_service, "get_provider", side_effect=AssertionError("não deve chamar IA")):
            r = chat_service.answer_question("o via é um bom app?", org_id=1)
        self.assertEqual(r["data"], {"has_data": False})
        self.assertIsNone(r["intent"])
        self.assertIn("dados de trânsito", r["answer"])
        self.assertFalse(any(ch.isdigit() for ch in r["answer"]))


class IntentFlagsTests(unittest.TestCase):
    TODAY = date(2026, 10, 4)

    def test_flags_tell_what_the_question_said(self):
        vazio = parse("e as ocorrências?", today=self.TODAY)
        self.assertFalse(vazio.date_explicit or vazio.hour_explicit or vazio.camera_explicit)
        self.assertEqual(vazio.metric, "occurrences")

        completo = parse("fluxo ontem das 8h às 10h", today=self.TODAY)
        self.assertTrue(completo.date_explicit and completo.hour_explicit)
        self.assertFalse(completo.camera_explicit)

    def test_period_of_day_counts_as_explicit_hour(self):
        self.assertTrue(parse("e de manhã?", today=self.TODAY).hour_explicit)


class FollowUpContextTests(unittest.TestCase):
    PREVIOUS = {
        "metric": "flow", "date_from": "2026-09-20", "date_to": "2026-09-20",
        "hour_from": "08:00:00", "hour_to": "10:00:00", "camera_key": "cam_7", "confidence": 0.9,
    }

    def _run(self, question, previous):
        seen = {}

        def fake_summary(filters, *a, **k):
            seen["filters"] = filters
            return {"has_data": False}

        provider = mock.Mock()
        provider.name = "teste"
        provider.explain.return_value = "ok"
        with mock.patch.object(chat_service, "_known_cameras", return_value=[]), \
                mock.patch.object(chat_service, "compute_summary", side_effect=fake_summary), \
                mock.patch.object(chat_service, "get_occurrences", side_effect=fake_summary), \
                mock.patch.object(chat_service, "get_provider", return_value=provider):
            result = chat_service.answer_question(question, org_id=3, previous_intent=previous)
        return seen["filters"], result

    def test_follow_up_inherits_period_hours_and_camera(self):
        filters, result = self._run("e as ocorrências?", self.PREVIOUS)
        self.assertEqual((filters.date_from, filters.date_to), (date(2026, 9, 20), date(2026, 9, 20)))
        self.assertEqual((filters.hour_from, filters.hour_to), (time(8), time(10)))
        self.assertEqual(filters.camera_key, "cam_7")
        self.assertEqual(filters.org_id, 3)
        self.assertEqual(result["intent"]["metric"], "occurrences")
        self.assertEqual(result["intent"]["date_from"], "2026-09-20")

    def test_explicit_parts_override_the_previous_context(self):
        filters, _ = self._run("e em 21/09/2026?", self.PREVIOUS)
        self.assertEqual(filters.date_from, date(2026, 9, 21))
        self.assertEqual((filters.hour_from, filters.hour_to), (time(8), time(10)))  # horário continua herdado

    def test_without_previous_it_keeps_the_default_day(self):
        filters, _ = self._run("quantos carros?", None)
        self.assertEqual(filters.date_from, filters.date_to)
        self.assertIsNone(filters.hour_from)

    def test_garbage_previous_intent_is_ignored(self):
        for junk in ("x", 5, {"date_from": "naoédata"}, {}):
            self.assertIsNone(chat_service.restore_intent(junk))
        filters, _ = self._run("quantos carros?", {"date_from": "naoédata"})
        self.assertEqual(filters.date_from, filters.date_to)


if __name__ == "__main__":
    unittest.main()
