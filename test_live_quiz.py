"""Общий старт, независимые клиенты, сохранность и конкурентные ответы."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from quiz_questions import QUIZ
from quiz_store import QuizError, QuizStore, normalize_name, normalize_public_url
from quiz_ui import cloud_html


APP = Path(__file__).with_name("app.py")


class StoreScenarios(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.store = QuizStore(self.directory.name)
        self.key = self.store.host_key
        self.round_id = self.store.current_round()["id"]

    def tearDown(self):
        self.directory.cleanup()

    def test_host_permissions_and_global_phases(self):
        self.assertFalse(self.store.authenticate("неверный код"))
        for operation in (lambda: self.store.start_round("bad"), lambda: self.store.close_round("bad"), lambda: self.store.new_round("bad"), lambda: self.store.board("bad"), lambda: self.store.set_public_url("bad", "https://example.ru")):
            with self.assertRaises(QuizError):
                operation()
        self.assertEqual(self.store.current_round()["status"], "waiting")
        self.store.start_round(self.key)
        started = self.store.current_round()["started_at"]
        self.store.start_round(self.key)
        self.assertEqual(self.store.current_round()["started_at"], started)
        self.store.close_round(self.key)
        self.assertEqual(self.store.current_round()["status"], "closed")
        with self.assertRaises(QuizError):
            self.store.start_round(self.key)

    def test_name_order_and_server_scoring(self):
        token = self.store.connect(self.round_id)
        with self.assertRaises(QuizError):
            self.store.register_name(self.round_id, token, "Иванов Иван Иванович")
        self.store.start_round(self.key)
        with self.assertRaises(QuizError):
            self.store.save_answer(self.round_id, token, 0, 0)
        self.store.register_name(self.round_id, token, "  Иванов   Иван Иванович ")
        with self.assertRaises(QuizError):
            self.store.save_answer(self.round_id, token, 3, 0)
        for i, question in enumerate(QUIZ):
            selected = question["answer"] if i != 1 else 0
            self.store.save_answer(self.round_id, token, i, selected)
            self.assertEqual(len(self.store.participant(self.round_id, token)["answers"]), i + 1)
            if i < 4:
                self.assertEqual(self.store.board(self.key)["finished"], [])
        person = self.store.participant(self.round_id, token)
        self.assertEqual(person["name"], "Иванов Иван Иванович")
        self.assertEqual(person["score"], 4)
        self.store.save_answer(self.round_id, token, 4, QUIZ[4]["answer"])
        self.assertEqual(self.store.participant(self.round_id, token)["completed_at"], person["completed_at"])
        with self.assertRaises(QuizError):
            self.store.save_answer(self.round_id, token, 0, 1)
        self.assertEqual(self.store.board(self.key)["distribution"], [0, 0, 0, 0, 1, 0])

    def test_resume_restart_and_new_round_archive(self):
        self.store.start_round(self.key)
        token = self.store.connect(self.round_id)
        self.store.register_name(self.round_id, token, "Петров Пётр Петрович")
        self.store.save_answer(self.round_id, token, 0, 0)
        restarted = QuizStore(self.directory.name)
        self.assertEqual(restarted.host_key, self.key)
        self.assertEqual(restarted.connect(self.round_id, token), token)
        self.assertEqual(restarted.participant(self.round_id, token)["answers"], {0: 0})
        self.assertEqual(restarted.board(self.key)["connected"], 1)
        new_id = restarted.new_round(self.key)
        self.assertNotEqual(new_id, self.round_id)
        self.assertEqual(restarted.current_round()["status"], "waiting")
        self.assertEqual(restarted.board(self.key)["connected"], 0)
        self.assertEqual(restarted.participant(self.round_id, token)["answers"], {0: 0})
        with self.assertRaises(QuizError):
            restarted.save_answer(self.round_id, token, 1, 1)

    def test_parallel_participants_have_independent_scores(self):
        self.store.start_round(self.key)

        def participate(index):
            token = self.store.connect(self.round_id)
            self.store.register_name(self.round_id, token, f"Участников{chr(0x410 + index)} Иван Иванович")
            target_score = index % 6
            for i, question in enumerate(QUIZ):
                choice = question["answer"] if i < target_score else (question["answer"] + 1) % 3
                self.store.save_answer(self.round_id, token, i, choice)
            return self.store.participant(self.round_id, token)["score"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            scores = list(pool.map(participate, range(24)))
        self.assertEqual(scores, [i % 6 for i in range(24)])
        board = self.store.board(self.key)
        self.assertEqual(board["connected"], 24)
        self.assertEqual(len(board["finished"]), 24)
        self.assertEqual(board["distribution"], [4, 4, 4, 4, 4, 4])
        self.assertEqual([q["correct"] for q in board["questions"]], [20, 16, 12, 8, 4])

    def test_close_rejects_late_answers_and_host_not_in_roster(self):
        token = self.store.connect(self.round_id)
        presenter = self.store.connect(self.round_id)
        self.store.exclude_presenter(self.key, presenter)
        self.store.start_round(self.key)
        self.store.register_name(self.round_id, token, "Сидорова Анна Игоревна")
        self.store.close_round(self.key)
        with self.assertRaises(QuizError):
            self.store.save_answer(self.round_id, token, 0, 0)
        self.assertEqual(self.store.board(self.key)["connected"], 1)
        self.assertEqual(self.store.board(self.key)["people"][0]["answered"], 0)

    def test_input_validation_and_public_qr_address(self):
        self.assertEqual(normalize_name("Петрова Анна-Мария Игоревна"), "Петрова Анна-Мария Игоревна")
        for value in ("Иван", "123 456", "<script>alert(1)</script>", "Иванов Ив4н Иванович"):
            with self.assertRaises(QuizError):
                normalize_name(value)
        for value in ("javascript:alert(1)", "https://user:password@example.ru", "example.ru", "https://example.ru:abc"):
            with self.assertRaises(QuizError):
                normalize_public_url(value)
        with patch.dict(os.environ, {"PUBLIC_APP_URL": ""}):
            self.assertEqual(self.store.join_url("http://localhost:8501/?presenter=1&ticket=private"), "http://localhost:8501/?join=1")
            self.assertEqual(self.store.join_url("https://example.ru/talk/?slide=12"), "https://example.ru/talk/?join=1")
        with patch.dict(os.environ, {"PUBLIC_APP_URL": "https://report.example.ru"}):
            self.assertEqual(self.store.join_url("http://localhost:8501/"), "https://report.example.ru/?join=1")
        self.store.set_public_url(self.key, "https://example.ru/talk/?slide=4#quiz")
        self.assertEqual(self.store.join_url(), "https://example.ru/talk/?join=1")
        cloud = cloud_html([{"name": "<img src=x>"}])
        self.assertNotIn("<img", cloud)
        self.assertIn("&lt;img", cloud)


class LiveUIScenarios(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"QUIZ_DATA_DIR": self.directory.name})
        self.environment.start()
        self.store = QuizStore(self.directory.name)

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def client(self, params=None, host=False):
        app = AppTest.from_file(str(APP), default_timeout=20)
        app.query_params.update(params or {})
        if host:
            app.session_state["host_key"] = self.store.host_key
        app.run()
        self.assert_clean(app)
        return app

    def assert_clean(self, app):
        self.assertEqual(len(app.exception), 0, [item.message for item in app.exception])

    @staticmethod
    def register(app, name):
        app.text_input(key="participant_name").input(name)
        next(button for button in app.button if button.label == "Начать отвечать").click().run()

    def finish(self, app, score):
        round_id = self.store.current_round()["id"]
        for i, question in enumerate(QUIZ):
            choice = question["answer"] if i < score else (question["answer"] + 1) % 3
            app.radio(key=f"live_answer_{round_id}_{i}").set_value(choice).run()
            app.button(key=f"save_live_answer_{i}").click().run()
            self.assert_clean(app)

    def test_host_login_and_role_cannot_be_forged_by_url(self):
        host = self.client({"presenter": "1"})
        host.text_input(key="host_login_code").input("bad")
        next(button for button in host.button if button.label == "Войти").click().run()
        self.assertEqual(self.store.current_round()["status"], "waiting")
        self.assertTrue(host.error)
        host.text_input(key="host_login_code").input(self.store.host_key)
        next(button for button in host.button if button.label == "Войти").click().run()
        self.assert_clean(host)
        self.assertTrue(host.button(key="live_start"))
        host.button(key="live_start").click().run()
        guest = self.client({"slide": "1", "presenter": "1"})
        self.assertEqual(guest.title[0].value, "Вход ведущего")
        self.assertEqual(len(guest.selectbox), 0)
        self.assertFalse(any(button.key == "live_start" for button in guest.button))

    def test_short_deck_navigation_and_presenter_login_from_cover(self):
        app = self.client()
        cover = next(item.value for item in app.markdown if 'class="authors"' in item.value)
        self.assertIn("<span>Головачев Егор</span>", cover)
        self.assertEqual(cover.count("<span>"), 6)  # подпись «Студенты» и пять авторов
        next(button for button in app.sidebar.button if button.label == "Вход ведущего").click().run()
        app.text_input(key="host_login_code").input(self.store.host_key)
        next(button for button in app.button if button.label == "Войти").click().run()
        self.assertEqual(self.store.board(self.store.host_key)["connected"], 0)
        self.assertNotIn("ticket", app.query_params)
        self.assertTrue(app.slider(key="intro_days"))
        for slide in range(2, 13):
            next(button for button in app.button if button.label == "Далее →").click().run()
            self.assert_clean(app)
            self.assertEqual(app.query_params["slide"], [str(slide)])
            self.assertTrue(any(f"{slide:02d} / 12" in item.value for item in app.markdown))
        self.assertTrue(app.button(key="live_start"))

    def test_legacy_quiz_link_and_direct_slides_respect_start(self):
        app = self.client({"quiz": "1", "embed": "true"})
        self.assertEqual(app.title[0].value, "Скоро начинаем")
        ticket = app.query_params["ticket"]
        app.button(key="return_to_deck").click().run()
        self.assertNotIn("quiz", app.query_params)
        self.assertEqual(app.query_params["ticket"], ticket)
        self.assertTrue(app.slider(key="intro_days"))
        guest_stage = self.client({"slide": "12"})
        self.assertFalse(any(button.key == "live_start" for button in guest_stage.button))
        self.store.start_round(self.store.host_key)
        for params in ({}, {"slide": "10"}, {"slide": "12"}, {"quiz": "1"}, {"join": "1"}):
            with self.subTest(params=params):
                guest = self.client(params)
                self.assertEqual(guest.title[0].value, "Представьтесь")
                self.assertEqual(len(guest.sidebar.button), 0)
                self.assertEqual(len(guest.dataframe), 0)

    def test_two_independent_participants_and_live_board(self):
        reader = self.client({"slide": "4"})
        self.assertTrue(reader.text_input(key="first_name"))
        first = self.client({"join": "1"})
        second = self.client({"quiz": "1"})
        self.assertEqual(first.title[0].value, "Скоро начинаем")
        host = self.client({"slide": "12"}, host=True)
        host.button(key="live_start").click().run()
        self.assert_clean(host)
        reader.run()
        self.assertEqual(reader.title[0].value, "Представьтесь")
        self.assertEqual(len(reader.selectbox), 0)
        self.assertEqual(len(reader.sidebar.button), 0)
        first.run()
        second.run()
        self.register(first, "Иванов Иван Иванович")
        self.register(second, "Иванов Иван Иванович")
        host.run()
        self.assertEqual(next(metric.value for metric in host.metric if metric.label == "Указали ФИО"), "2")
        self.finish(first, 5)
        self.assertEqual(first.metric[0].value, "5 / 5")
        self.assertEqual(len(first.expander), 0)
        host.run()
        self.assertEqual(next(metric.value for metric in host.metric if metric.label == "Завершили"), "1")
        cloud = next(item.proto.body for item in host.get("html") if 'class="finish-cloud"' in item.proto.body)
        self.assertEqual(cloud.count("Иванов Иван Иванович"), 1)
        self.finish(second, 3)
        host.run()
        self.assert_clean(host)
        self.assertEqual(next(metric.value for metric in host.metric if metric.label == "Завершили"), "2")
        self.assertEqual(self.store.board(self.store.host_key)["distribution"], [0, 0, 0, 1, 0, 1])
        self.assertEqual(host.dataframe[0].value["ФИО"].tolist(), ["Иванов Иван Иванович"] * 2)
        self.assertEqual(host.dataframe[0].value["Баллы"].tolist(), ["5 / 5", "3 / 5"])
        cloud = next(item.proto.body for item in host.get("html") if 'class="finish-cloud"' in item.proto.body)
        self.assertEqual(cloud.count("Иванов Иван Иванович"), 2)
        first.query_params["slide"] = "1"
        first.run()
        self.assertEqual(first.title[0].value, "Готово. Вы в облаке!")
        self.assertEqual(len(first.selectbox), 0)
        host.button(key="live_close").click().run()
        first.run()
        self.assertTrue(any(item.label == "Ответы и обсуждение" for item in first.expander))

    def test_reload_restores_attempt_and_new_round_resets_view(self):
        self.store.start_round(self.store.host_key)
        app = self.client({"join": "1"})
        self.register(app, "Сидорова Анна Игоревна")
        token = app.query_params["ticket"][0]
        round_id = self.store.current_round()["id"]
        app.radio(key=f"live_answer_{round_id}_0").set_value(0).run()
        app.button(key="save_live_answer_0").click().run()
        restored = self.client({"join": "1", "ticket": token})
        self.assertEqual(restored.title[0].value, QUIZ[1]["question"])
        self.assertEqual(self.store.board(self.store.host_key)["connected"], 1)
        self.store.new_round(self.store.host_key)
        restored.run()
        self.assert_clean(restored)
        self.assertEqual(restored.title[0].value, "Скоро начинаем")
        self.assertNotEqual(restored.query_params["ticket"][0], token)


if __name__ == "__main__":
    unittest.main()
