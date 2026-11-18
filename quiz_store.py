"""Общее состояние квиза и атомарное сохранение ответов разных браузеров."""

from contextlib import closing, contextmanager
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

from quiz_questions import QUIZ


class QuizError(ValueError):
    pass


def normalize_name(value: str) -> str:
    name = " ".join(value.split())
    parts = name.split()
    if not 2 <= len(parts) <= 6 or not 4 <= len(name) <= 120:
        raise QuizError("Укажите фамилию, имя и отчество, если оно есть. От 4 до 120 символов.")
    if not all(re.fullmatch(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", part, re.UNICODE) for part in parts):
        raise QuizError("В ФИО допустимы буквы, пробелы, дефис и апостроф.")
    return name


def normalize_public_url(value: str) -> str:
    value = value.strip()
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError
        if any(char.isspace() for char in value) or len(value) > 500:
            raise ValueError
        _ = parts.port
    except ValueError as exc:
        raise QuizError("Укажите адрес приложения вида https://example.ru, без логина и пароля.") from exc
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


class QuizStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.directory / "quiz.sqlite3"
        self.key_path = self.directory / "host_code.txt"
        self.host_key = os.environ.get("QUIZ_HOST_KEY", "").strip()
        if not self.host_key:
            try:
                with self.key_path.open("x", encoding="utf-8") as file:
                    file.write(secrets.token_urlsafe(18) + "\n")
            except FileExistsError:
                pass
            self.host_key = self.key_path.read_text(encoding="utf-8").strip()
        if not self.host_key:
            raise RuntimeError("Не задан код ведущего. Проверьте QUIZ_HOST_KEY или runtime/host_code.txt.")
        with closing(sqlite3.connect(self.db_path, timeout=20)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rounds (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('waiting', 'running', 'closed')),
                    created_at REAL NOT NULL,
                    started_at REAL,
                    closed_at REAL
                );
                CREATE TABLE IF NOT EXISTS participants (
                    token TEXT PRIMARY KEY,
                    round_id TEXT NOT NULL REFERENCES rounds(id),
                    name TEXT NOT NULL DEFAULT '',
                    joined_at REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    completed_at REAL,
                    score INTEGER,
                    excluded INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS participants_round ON participants(round_id);
                CREATE TABLE IF NOT EXISTS answers (
                    token TEXT NOT NULL REFERENCES participants(token),
                    question INTEGER NOT NULL CHECK (question BETWEEN 0 AND 4),
                    selected INTEGER NOT NULL CHECK (selected BETWEEN 0 AND 2),
                    saved_at REAL NOT NULL,
                    PRIMARY KEY (token, question)
                );
            """)
            db.commit()
        with self._transaction() as db:
            if not db.execute("SELECT 1 FROM settings WHERE key='current_round'").fetchone():
                self._create_round(db)
            db.execute("INSERT OR IGNORE INTO settings VALUES ('public_url', '')")

    @contextmanager
    def _transaction(self, write: bool = True):
        db = sqlite3.connect(self.db_path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def authenticate(self, key: str) -> bool:
        return isinstance(key, str) and secrets.compare_digest(key.encode("utf-8"), self.host_key.encode("utf-8"))

    def _require_host(self, key: str) -> None:
        if not self.authenticate(key):
            raise QuizError("Для этого действия нужен код ведущего.")

    @staticmethod
    def _create_round(db) -> str:
        round_id = uuid.uuid4().hex
        db.execute("INSERT INTO rounds(id,status,created_at) VALUES (?, 'waiting', ?)", (round_id, time.time()))
        db.execute("INSERT OR REPLACE INTO settings VALUES ('current_round', ?)", (round_id,))
        return round_id

    @staticmethod
    def _current_round(db) -> dict:
        return dict(db.execute("SELECT r.* FROM rounds r JOIN settings s ON s.value=r.id WHERE s.key='current_round'").fetchone())

    def current_round(self) -> dict:
        with self._transaction(False) as db:
            return self._current_round(db)

    def start_round(self, key: str) -> None:
        self._require_host(key)
        with self._transaction() as db:
            current = self._current_round(db)
            if current["status"] == "closed":
                raise QuizError("Этот раунд уже закрыт. Создайте новый раунд.")
            db.execute("UPDATE rounds SET status='running', started_at=COALESCE(started_at, ?) WHERE id=?", (time.time(), current["id"]))

    def close_round(self, key: str) -> None:
        self._require_host(key)
        with self._transaction() as db:
            current = self._current_round(db)
            if current["status"] == "waiting":
                raise QuizError("Квиз ещё не запущен.")
            db.execute("UPDATE rounds SET status='closed', closed_at=COALESCE(closed_at, ?) WHERE id=?", (time.time(), current["id"]))

    def new_round(self, key: str) -> str:
        self._require_host(key)
        with self._transaction() as db:
            current = self._current_round(db)
            db.execute("UPDATE rounds SET status='closed', closed_at=COALESCE(closed_at, ?) WHERE id=?", (time.time(), current["id"]))
            return self._create_round(db)

    def public_url(self, browser_url: str | None = None) -> str:
        with self._transaction(False) as db:
            configured = db.execute("SELECT value FROM settings WHERE key='public_url'").fetchone()[0]
        return configured or normalize_public_url(os.environ.get("PUBLIC_APP_URL") or browser_url or "http://localhost:8501")

    def set_public_url(self, key: str, value: str) -> None:
        self._require_host(key)
        value = normalize_public_url(value)
        with self._transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key='public_url'", (value,))

    def join_url(self, browser_url: str | None = None) -> str:
        return self.public_url(browser_url) + "/?join=1"

    def connect(self, round_id: str, token: str | None = None) -> str:
        with self._transaction() as db:
            current = self._current_round(db)
            if current["id"] != round_id:
                raise QuizError("Ведущий открыл новый раунд. Обновите страницу.")
            existing = db.execute("SELECT 1 FROM participants WHERE token=? AND round_id=? AND excluded=0", (token, round_id)).fetchone() if token else None
            if existing:
                db.execute("UPDATE participants SET last_seen=? WHERE token=?", (time.time(), token))
                return token
            token = secrets.token_urlsafe(24)
            now = time.time()
            db.execute("INSERT INTO participants(token,round_id,joined_at,last_seen) VALUES (?,?,?,?)", (token, round_id, now, now))
            return token

    def exclude_presenter(self, key: str, token: str) -> None:
        self._require_host(key)
        with self._transaction() as db:
            db.execute("UPDATE participants SET excluded=1 WHERE token=? AND name=''", (token,))

    def heartbeat(self, round_id: str, token: str) -> None:
        with self._transaction() as db:
            db.execute("UPDATE participants SET last_seen=? WHERE token=? AND round_id=? AND excluded=0", (time.time(), token, round_id))

    @staticmethod
    def _participant(db, round_id: str, token: str):
        person = db.execute("SELECT * FROM participants WHERE token=? AND round_id=? AND excluded=0", (token, round_id)).fetchone()
        if not person:
            raise QuizError("Подключение не найдено. Откройте ссылку квиза заново.")
        return person

    @classmethod
    def _require_running(cls, db, round_id: str) -> None:
        current = cls._current_round(db)
        if current["id"] != round_id or current["status"] != "running":
            raise QuizError("Этот раунд сейчас не принимает ответы.")

    def register_name(self, round_id: str, token: str, value: str) -> None:
        name = normalize_name(value)
        with self._transaction() as db:
            self._require_running(db, round_id)
            person = self._participant(db, round_id, token)
            if person["name"] and person["name"] != name:
                raise QuizError("Имя этой попытки уже сохранено.")
            db.execute("UPDATE participants SET name=?,last_seen=? WHERE token=?", (name, time.time(), token))

    def participant(self, round_id: str, token: str) -> dict:
        with self._transaction(False) as db:
            person = dict(self._participant(db, round_id, token))
            person["answers"] = {row["question"]: row["selected"] for row in db.execute("SELECT question,selected FROM answers WHERE token=? ORDER BY question", (token,))}
            return person

    def save_answer(self, round_id: str, token: str, question: int, selected: int) -> None:
        if type(question) is not int or not 0 <= question < len(QUIZ) or type(selected) is not int or not 0 <= selected < len(QUIZ[question]["options"]):
            raise QuizError("Неверный вопрос или вариант ответа.")
        with self._transaction() as db:
            self._require_running(db, round_id)
            person = self._participant(db, round_id, token)
            if not person["name"]:
                raise QuizError("Сначала укажите ФИО.")
            saved = {row["question"]: row["selected"] for row in db.execute("SELECT question,selected FROM answers WHERE token=?", (token,))}
            if question in saved:
                if saved[question] != selected:
                    raise QuizError("Этот ответ уже сохранён, изменить его нельзя.")
                return
            if question != len(saved):
                raise QuizError("Ответьте на вопросы по порядку.")
            now = time.time()
            db.execute("INSERT INTO answers VALUES (?,?,?,?)", (token, question, selected, now))
            saved[question] = selected
            db.execute("UPDATE participants SET last_seen=? WHERE token=?", (now, token))
            if len(saved) == len(QUIZ):
                score = sum(saved[i] == item["answer"] for i, item in enumerate(QUIZ))
                db.execute("UPDATE participants SET completed_at=?,score=? WHERE token=?", (now, score, token))

    def board(self, key: str) -> dict:
        self._require_host(key)
        with self._transaction(False) as db:
            current = self._current_round(db)
            people = [dict(row) for row in db.execute("""
                SELECT p.name,p.joined_at,p.last_seen,p.completed_at,p.score,COUNT(a.question) AS answered
                FROM participants p LEFT JOIN answers a ON a.token=p.token
                WHERE p.round_id=? AND p.excluded=0 GROUP BY p.token ORDER BY p.joined_at
            """, (current["id"],))]
            finished = [person for person in people if person["completed_at"] is not None]
            distribution = [sum(person["score"] == score for person in finished) for score in range(len(QUIZ) + 1)]
            question_totals = []
            for i, question in enumerate(QUIZ):
                row = db.execute("""
                    SELECT COUNT(*) AS total,COALESCE(SUM(a.selected=?),0) AS correct
                    FROM answers a JOIN participants p ON p.token=a.token
                    WHERE p.round_id=? AND p.excluded=0 AND p.completed_at IS NOT NULL AND a.question=?
                """, (question["answer"], current["id"], i)).fetchone()
                question_totals.append({"question": i + 1, "total": row["total"], "correct": row["correct"]})
            return {
                "round": current,
                "connected": len(people),
                "online": sum(time.time() - person["last_seen"] < 15 for person in people),
                "people": [person for person in people if person["name"]],
                "anonymous": sum(not person["name"] for person in people),
                "finished": sorted(finished, key=lambda person: person["completed_at"]),
                "distribution": distribution,
                "questions": question_totals,
            }
