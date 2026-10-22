from __future__ import annotations

import datetime as dt
import json
import random
import shutil
import sqlite3
from pathlib import Path

from .config import (
    DB_PATH, DEFAULT_SETTINGS, KINDS, LEARNED_REPS, PHRASE_POS, STATUS_LEARNED, STATUS_LEARNING, STATUS_NEW,
    USER_DIR,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS words(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    english     TEXT NOT NULL COLLATE NOCASE UNIQUE,
    turkish     TEXT NOT NULL DEFAULT '',
    phonetic    TEXT NOT NULL DEFAULT '',
    pron_tr     TEXT,                        -- NULL => IPA'dan otomatik üretilir
    pos         TEXT NOT NULL DEFAULT '',
    level       TEXT NOT NULL DEFAULT 'B2',
    rank        INTEGER,
    example     TEXT NOT NULL DEFAULT '',
    example_tr  TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'builtin', -- builtin | user | api
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_words_rank  ON words(rank);
CREATE INDEX IF NOT EXISTS idx_words_level ON words(level);

CREATE TABLE IF NOT EXISTS progress(
    word_id       INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    status        INTEGER NOT NULL DEFAULT 0,   -- 0 yeni, 1 öğreniliyor, 2 öğrenildi
    favorite      INTEGER NOT NULL DEFAULT 0,
    widget_seen   INTEGER NOT NULL DEFAULT 0,
    reviews       INTEGER NOT NULL DEFAULT 0,
    correct       INTEGER NOT NULL DEFAULT 0,
    wrong         INTEGER NOT NULL DEFAULT 0,
    reps          INTEGER NOT NULL DEFAULT 0,
    ease          REAL    NOT NULL DEFAULT 2.5,
    interval_days REAL    NOT NULL DEFAULT 0,
    due_at        TEXT,
    last_seen     TEXT,
    last_review   TEXT,
    learned_at    TEXT,
    note          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_progress_status ON progress(status);
CREATE INDEX IF NOT EXISTS idx_progress_due    ON progress(due_at);

CREATE TABLE IF NOT EXISTS settings(
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_stats(
    day           TEXT PRIMARY KEY,
    widget_views  INTEGER NOT NULL DEFAULT 0,
    reviews       INTEGER NOT NULL DEFAULT 0,
    correct       INTEGER NOT NULL DEFAULT 0,
    wrong         INTEGER NOT NULL DEFAULT 0,
    new_words     INTEGER NOT NULL DEFAULT 0,
    learned       INTEGER NOT NULL DEFAULT 0,
    tense_answers INTEGER NOT NULL DEFAULT 0,
    study_seconds INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_log(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    word_id INTEGER REFERENCES words(id) ON DELETE CASCADE,
    mode    TEXT NOT NULL,
    quality INTEGER NOT NULL,
    answer  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_review_log_word ON review_log(word_id);

CREATE TABLE IF NOT EXISTS decks(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'custom',   -- draft | custom
    color       TEXT NOT NULL DEFAULT '#7C5CFF',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS deck_cards(
    deck_id  INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    word_id  INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY(deck_id, word_id)
);

CREATE TABLE IF NOT EXISTS tense_progress(
    tense_key  TEXT PRIMARY KEY,
    read_count INTEGER NOT NULL DEFAULT 0,
    correct    INTEGER NOT NULL DEFAULT 0,
    wrong      INTEGER NOT NULL DEFAULT 0,
    best_score INTEGER NOT NULL DEFAULT 0,
    last_at    TEXT
);
"""

WORD_SELECT = """
SELECT w.id, w.english, w.turkish, w.phonetic, w.pron_tr, w.pos, w.level, w.rank,
       w.example, w.example_tr, w.source, w.created_at,
       p.status, p.favorite, p.widget_seen, p.reviews, p.correct, p.wrong, p.reps,
       p.ease, p.interval_days, p.due_at, p.last_seen, p.last_review, p.learned_at, p.note
FROM words w JOIN progress p ON p.word_id = w.id
"""

TS_FMT = "%Y-%m-%d %H:%M:%S"


def now_str() -> str:
    return dt.datetime.now().strftime(TS_FMT)


def today_str() -> str:
    return dt.date.today().isoformat()


def parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, TS_FMT)
    except ValueError:
        return None


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._settings: dict = {}
        self._connect()

    def _connect(self):
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._load_settings()

    def close(self):
        try:
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error:
            pass

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def _load_settings(self):
        self._settings = {}
        for row in self.conn.execute("SELECT key, value FROM settings"):
            try:
                self._settings[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                pass

    def get(self, key: str, default=None):
        if key in self._settings:
            return self._settings[key]
        if key in DEFAULT_SETTINGS:
            value = DEFAULT_SETTINGS[key]
            return list(value) if isinstance(value, list) else value
        return default

    def set(self, key: str, value):
        self._settings[key] = value
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def reset_settings(self, prefix: str):
        keys = [k for k in list(self._settings) if k.startswith(prefix)]
        for k in keys:
            self._settings.pop(k, None)
        self.conn.execute("DELETE FROM settings WHERE key LIKE ?", (prefix + "%",))
        self.conn.commit()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row is not None else None

    def word_count(self, source: str | None = None) -> int:
        if source:
            return self.conn.execute("SELECT COUNT(*) FROM words WHERE source=?", (source,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]

    def get_word(self, word_id: int) -> dict | None:
        return self._row(self.conn.execute(WORD_SELECT + " WHERE w.id = ?", (word_id,)).fetchone())

    def get_word_by_english(self, english: str) -> dict | None:
        return self._row(
            self.conn.execute(WORD_SELECT + " WHERE w.english = ? COLLATE NOCASE", (english.strip(),)).fetchone()
        )

    def get_words(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        out: dict[int, dict] = {}
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start:chunk_start + 500]
            marks = ",".join("?" * len(chunk))
            for r in self.conn.execute(WORD_SELECT + f" WHERE w.id IN ({marks})", chunk):
                out[r["id"]] = dict(r)
        return [out[i] for i in ids if i in out]

    def search_words(self, text: str = "", level: str | None = None, status: int | None = None,
                     pos: str | None = None, favorites: bool = False, source: str | None = None,
                     deck_id: int | None = None, limit: int | None = None) -> list[dict]:
        sql = WORD_SELECT
        where, params = [], []
        if deck_id is not None:
            sql += " JOIN deck_cards dc ON dc.word_id = w.id AND dc.deck_id = ?"
            params.append(deck_id)
        if text:
            like = f"%{text.strip()}%"
            where.append("(w.english LIKE ? OR w.turkish LIKE ?)")
            params += [like, like]
        if level:
            where.append("w.level = ?")
            params.append(level)
        if status is not None:
            where.append("p.status = ?")
            params.append(status)
        if pos:
            where.append("(',' || w.pos || ',') LIKE ?")
            params.append(f"%,{pos},%")
        if favorites:
            where.append("p.favorite = 1")
        if source:
            where.append("w.source = ?")
            params.append(source)
        if where:
            sql += " WHERE " + " AND ".join(where)
        if text:
            sql += " ORDER BY (w.english = ? COLLATE NOCASE) DESC, (w.english LIKE ?) DESC, COALESCE(w.rank, 999999), w.english"
            params += [text.strip(), f"{text.strip()}%"]
        else:
            sql += " ORDER BY COALESCE(w.rank, 999999), w.english"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self.conn.execute(sql, params)]

    def add_word(self, english: str, turkish: str, phonetic: str = "", pron_tr: str | None = None,
                 pos: str = "", level: str = "", example: str = "", example_tr: str = "",
                 source: str = "user") -> int:
        english = english.strip()
        if not english:
            raise ValueError("İngilizce kelime boş olamaz.")
        existing = self.get_word_by_english(english)
        if existing:
            raise ValueError(f"'{english}' zaten kütüphanede var.")
        cur = self.conn.execute(
            "INSERT INTO words(english, turkish, phonetic, pron_tr, pos, level, rank, example, example_tr, source)"
            " VALUES(?,?,?,?,?,?,NULL,?,?,?)",
            (english, turkish.strip(), phonetic.strip(), (pron_tr or None), pos, level or "C1",
             example.strip(), example_tr.strip(), source),
        )
        word_id = cur.lastrowid
        self.conn.execute("INSERT OR IGNORE INTO progress(word_id) VALUES(?)", (word_id,))
        self.conn.commit()
        return word_id

    def update_word(self, word_id: int, **fields):
        allowed = {"english", "turkish", "phonetic", "pron_tr", "pos", "level", "example", "example_tr"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        cols = ", ".join(f"{k} = ?" for k in sets)
        self.conn.execute(f"UPDATE words SET {cols} WHERE id = ?", (*sets.values(), word_id))
        self.conn.execute("UPDATE words SET source = 'edited' WHERE id = ? AND source = 'builtin'", (word_id,))
        self.conn.commit()

    def delete_word(self, word_id: int):
        self.conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
        self.conn.commit()

    def random_words(self, n: int, exclude: set[int] | None = None, pos: str | None = None,
                     levels: list[str] | None = None) -> list[dict]:
        sql = WORD_SELECT + " WHERE w.turkish <> ''"
        params: list = []
        if pos:
            sql += " AND (',' || w.pos || ',') LIKE ?"
            params.append(f"%,{pos},%")
        if levels:
            sql += f" AND w.level IN ({','.join('?' * len(levels))})"
            params += levels
        sql += " ORDER BY RANDOM() LIMIT ?"
        params.append(n + len(exclude or ()))
        rows = [dict(r) for r in self.conn.execute(sql, params)]
        if exclude:
            rows = [r for r in rows if r["id"] not in exclude]
        return rows[:n]

    def set_status(self, word_id: int, status: int):
        now = dt.datetime.now()
        word = self.get_word(word_id)
        if word is None:
            return
        if status == STATUS_LEARNED:
            self.conn.execute(
                "UPDATE progress SET status=?, learned_at=?, reps=MAX(reps, ?), interval_days=MAX(interval_days, 21),"
                " due_at=? WHERE word_id=?",
                (STATUS_LEARNED, now.strftime(TS_FMT), LEARNED_REPS,
                 (now + dt.timedelta(days=21)).strftime(TS_FMT), word_id),
            )
            if word["status"] != STATUS_LEARNED:
                self._bump_daily(learned=1)
        elif status == STATUS_LEARNING:
            self.conn.execute(
                "UPDATE progress SET status=?, learned_at=NULL, due_at=? WHERE word_id=?",
                (STATUS_LEARNING, now.strftime(TS_FMT), word_id),
            )
        else:
            self.conn.execute(
                "UPDATE progress SET status=0, reps=0, ease=2.5, interval_days=0, due_at=NULL,"
                " learned_at=NULL WHERE word_id=?",
                (word_id,),
            )
        self.conn.commit()

    def toggle_favorite(self, word_id: int) -> bool:
        self.conn.execute("UPDATE progress SET favorite = 1 - favorite WHERE word_id = ?", (word_id,))
        self.conn.commit()
        return bool(self.conn.execute("SELECT favorite FROM progress WHERE word_id=?", (word_id,)).fetchone()[0])

    def set_note(self, word_id: int, note: str):
        self.conn.execute("UPDATE progress SET note=? WHERE word_id=?", (note, word_id))
        self.conn.commit()

    def record_widget_view(self, word_id: int):
        self.conn.execute(
            "UPDATE progress SET widget_seen = widget_seen + 1, last_seen = ? WHERE word_id = ?",
            (now_str(), word_id),
        )
        self._bump_daily(widget_views=1)
        self.conn.commit()

    def record_answer(self, word_id: int, quality: int, mode: str, answer: str = "", srs: bool = True) -> dict:
        row = self.conn.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,)).fetchone()
        if row is None:
            return {}
        p = dict(row)
        now = dt.datetime.now()
        due = parse_ts(p["due_at"])
        is_due = due is None or due <= now
        correct = quality >= 3
        was_new = p["reviews"] == 0
        old_status = p["status"]

        p["reviews"] += 1
        if correct:
            p["correct"] += 1
        else:
            p["wrong"] += 1

        if not correct:
            p["reps"] = 0
            p["ease"] = max(1.3, p["ease"] - 0.2)
            p["interval_days"] = 0
            p["due_at"] = (now + dt.timedelta(minutes=10)).strftime(TS_FMT)
            p["status"] = STATUS_LEARNING
            p["learned_at"] = None
        elif srs and is_due:
            p["reps"] += 1
            if p["reps"] == 1:
                interval = 1.0
            elif p["reps"] == 2:
                interval = 3.0
            else:
                interval = max(1.0, p["interval_days"]) * p["ease"]
            if quality == 5:
                interval *= 1.3
            elif quality == 3:
                interval *= 0.8
            p["interval_days"] = round(max(interval, 0.5), 2)
            q = quality
            p["ease"] = max(1.3, p["ease"] + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
            p["due_at"] = (now + dt.timedelta(days=p["interval_days"])).strftime(TS_FMT)
            if p["reps"] >= LEARNED_REPS:
                p["status"] = STATUS_LEARNED
                if old_status != STATUS_LEARNED:
                    p["learned_at"] = now.strftime(TS_FMT)
            elif p["status"] != STATUS_LEARNED:
                p["status"] = STATUS_LEARNING
        else:
            if p["status"] == STATUS_NEW:
                p["status"] = STATUS_LEARNING
                p["due_at"] = now.strftime(TS_FMT)

        p["last_review"] = now.strftime(TS_FMT)
        self.conn.execute(
            "UPDATE progress SET status=?, reviews=?, correct=?, wrong=?, reps=?, ease=?, interval_days=?,"
            " due_at=?, last_review=?, learned_at=? WHERE word_id=?",
            (p["status"], p["reviews"], p["correct"], p["wrong"], p["reps"], p["ease"], p["interval_days"],
             p["due_at"], p["last_review"], p["learned_at"], word_id),
        )
        self.conn.execute(
            "INSERT INTO review_log(word_id, mode, quality, answer) VALUES(?,?,?,?)",
            (word_id, mode, quality, answer[:200]),
        )
        self._bump_daily(
            reviews=1,
            correct=1 if correct else 0,
            wrong=0 if correct else 1,
            new_words=1 if was_new else 0,
            learned=1 if (p["status"] == STATUS_LEARNED and old_status != STATUS_LEARNED) else 0,
        )
        self.conn.commit()
        p["became_learned"] = p["status"] == STATUS_LEARNED and old_status != STATUS_LEARNED
        return p

    def _level_clause(self, levels: list[str] | None, params: list, kinds: list[str] | None = None) -> str:
        sql = ""
        if levels:
            params += list(levels)
            sql += f" AND (w.level IN ({','.join('?' * len(levels))}) OR w.rank IS NULL)"
        if kinds and not set(KINDS) <= set(kinds):
            conds = []
            phrase = [k for k in kinds if k in PHRASE_POS]
            if phrase:
                conds.append(f"w.pos IN ({','.join('?' * len(phrase))})")
                params += phrase
            if "word" in kinds:
                conds.append(f"w.pos NOT IN ({','.join('?' * len(PHRASE_POS))})")
                params += list(PHRASE_POS)
            sql += f" AND ({' OR '.join(conds) or '0'})"
        return sql

    def _ids(self, sql: str, params) -> list[int]:
        return [r[0] for r in self.conn.execute(sql, params)]

    def session_word_ids(self, source: str, size: int, levels: list[str] | None = None,
                         deck_id: int | None = None, kinds: list[str] | None = None) -> list[int]:
        now = now_str()
        params: list = []
        lv = self._level_clause(levels, params, kinds)
        base = "SELECT w.id FROM words w JOIN progress p ON p.word_id = w.id WHERE w.turkish <> ''"
        if source == "deck" and deck_id is not None:
            ids = self._ids(
                "SELECT dc.word_id FROM deck_cards dc JOIN progress p ON p.word_id = dc.word_id"
                " WHERE dc.deck_id = ? ORDER BY p.status, COALESCE(p.due_at, ''), RANDOM()",
                (deck_id,),
            )
            return ids[:size]
        if source == "smart":
            due = self._ids(base + lv + " AND p.status > 0 AND p.due_at IS NOT NULL AND p.due_at <= ?"
                            " ORDER BY p.due_at LIMIT ?", params + [now, size])
            if len(due) < size:
                new = self._ids(base + lv + " AND p.status = 0 ORDER BY p.widget_seen DESC, COALESCE(w.rank, 999999)"
                                " LIMIT ?", params + [size - len(due)])
                due += new
            random.shuffle(due)
            return due[:size]
        if source == "new":
            return self._ids(base + lv + " AND p.status = 0 ORDER BY COALESCE(w.rank, 999999) LIMIT ?",
                             params + [size])
        if source == "due":
            return self._ids(base + lv + " AND p.status > 0 AND p.due_at <= ? ORDER BY p.due_at LIMIT ?",
                             params + [now, size])
        if source == "learning":
            return self._ids(base + lv + " AND p.status = 1 ORDER BY RANDOM() LIMIT ?", params + [size])
        if source == "learned":
            return self._ids(base + lv + " AND p.status = 2 ORDER BY RANDOM() LIMIT ?", params + [size])
        if source == "favorites":
            return self._ids(base + lv + " AND p.favorite = 1 ORDER BY RANDOM() LIMIT ?", params + [size])
        if source == "hard":
            return self._ids(base + lv + " AND p.wrong > 0 ORDER BY (p.wrong - p.correct) DESC, p.wrong DESC LIMIT ?",
                             params + [size])
        if source == "widget":
            return self._ids(base + lv + " AND p.widget_seen > 0 AND p.status < 2"
                             " ORDER BY p.widget_seen DESC LIMIT ?", params + [size])
        return self._ids(base + lv + " ORDER BY RANDOM() LIMIT ?", params + [size])

    def widget_pool(self, source: str, order: str, levels: list[str] | None, deck_id: int | None,
                    kinds: list[str] | None = None) -> list[int]:
        params: list = []
        lv = self._level_clause(levels, params, kinds)
        base = "SELECT w.id FROM words w JOIN progress p ON p.word_id = w.id WHERE w.turkish <> ''"
        if source == "deck" and deck_id is not None:
            ids = self._ids("SELECT word_id FROM deck_cards WHERE deck_id = ? ORDER BY position", (deck_id,))
        elif source == "smart":
            learning = self._ids(base + lv + " AND p.status = 1 ORDER BY COALESCE(p.due_at,'') LIMIT 150", params)
            new = self._ids(
                "SELECT id FROM (" + base + lv + " AND p.status = 0 ORDER BY COALESCE(w.rank, 999999) LIMIT 120)"
                " ORDER BY RANDOM()", params)
            new_ids = self._ids(
                f"SELECT p.word_id FROM progress p WHERE p.word_id IN ({','.join('?' * len(new))})"
                " ORDER BY p.widget_seen, RANDOM() LIMIT 70", new) if new else []
            learned = self._ids(base + lv + " AND p.status = 2 ORDER BY RANDOM() LIMIT 30", params)
            ids = learning + learning[:60] + new_ids + learned
        elif source == "new":
            ids = self._ids(base + lv + " AND p.status = 0 ORDER BY COALESCE(w.rank, 999999) LIMIT 400", params)
        elif source == "learning":
            ids = self._ids(base + lv + " AND p.status = 1", params)
        elif source == "learned":
            ids = self._ids(base + lv + " AND p.status = 2", params)
        elif source == "favorites":
            ids = self._ids(base + lv + " AND p.favorite = 1", params)
        elif source == "hard":
            ids = self._ids(base + lv + " AND p.wrong > 0 ORDER BY (p.wrong - p.correct) DESC LIMIT 200", params)
        else:
            if order == "sequential":
                ids = self._ids(base + lv + " ORDER BY COALESCE(w.rank, 999999), w.id", params)
            else:
                ids = self._ids(base + lv + " ORDER BY RANDOM() LIMIT 600", params)
        if not ids:
            ids = self._ids("SELECT id FROM words WHERE turkish <> '' ORDER BY COALESCE(rank, 999999) LIMIT 100", ())
        if order in ("random", "smart"):
            random.shuffle(ids)
        return ids

    def _bump_daily(self, **fields):
        day = today_str()
        self.conn.execute("INSERT OR IGNORE INTO daily_stats(day) VALUES(?)", (day,))
        sets = ", ".join(f"{k} = {k} + ?" for k in fields)
        self.conn.execute(f"UPDATE daily_stats SET {sets} WHERE day = ?", (*fields.values(), day))

    def add_study_seconds(self, seconds: int):
        if seconds > 0:
            self._bump_daily(study_seconds=int(seconds))
            self.conn.commit()

    def today(self) -> dict:
        row = self.conn.execute("SELECT * FROM daily_stats WHERE day = ?", (today_str(),)).fetchone()
        if row:
            return dict(row)
        return {"day": today_str(), "widget_views": 0, "reviews": 0, "correct": 0, "wrong": 0,
                "new_words": 0, "learned": 0, "tense_answers": 0, "study_seconds": 0}

    def daily_range(self, days: int = 14) -> list[dict]:
        start = dt.date.today() - dt.timedelta(days=days - 1)
        rows = {r["day"]: dict(r) for r in self.conn.execute(
            "SELECT * FROM daily_stats WHERE day >= ?", (start.isoformat(),))}
        out = []
        for i in range(days):
            d = (start + dt.timedelta(days=i)).isoformat()
            out.append(rows.get(d, {"day": d, "widget_views": 0, "reviews": 0, "correct": 0, "wrong": 0,
                                    "new_words": 0, "learned": 0, "tense_answers": 0, "study_seconds": 0}))
        return out

    def streak(self) -> int:
        active = {r[0] for r in self.conn.execute(
            "SELECT day FROM daily_stats WHERE reviews > 0 OR tense_answers > 0")}
        day = dt.date.today()
        if day.isoformat() not in active:
            day -= dt.timedelta(days=1)
        count = 0
        while day.isoformat() in active:
            count += 1
            day -= dt.timedelta(days=1)
        return count

    def best_streak(self) -> int:
        days = sorted(dt.date.fromisoformat(r[0]) for r in self.conn.execute(
            "SELECT day FROM daily_stats WHERE reviews > 0 OR tense_answers > 0"))
        best = cur = 0
        prev = None
        for d in days:
            cur = cur + 1 if prev and (d - prev).days == 1 else 1
            best = max(best, cur)
            prev = d
        return best

    def totals(self) -> dict:
        r = self.conn.execute(
            "SELECT COUNT(*) total,"
            " SUM(status = 0) new, SUM(status = 1) learning, SUM(status = 2) learned,"
            " SUM(favorite) favorites, SUM(widget_seen) widget_total, SUM(reviews) reviews,"
            " SUM(correct) correct, SUM(wrong) wrong,"
            " SUM(status > 0 AND due_at IS NOT NULL AND due_at <= ?) due"
            " FROM progress", (now_str(),)).fetchone()
        return {k: (r[k] or 0) for k in r.keys()}

    def level_breakdown(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT w.level, COUNT(*) total, SUM(p.status = 2) learned, SUM(p.status = 1) learning"
            " FROM words w JOIN progress p ON p.word_id = w.id GROUP BY w.level ORDER BY w.level").fetchall()
        return [{k: (r[k] or 0) for k in r.keys()} for r in rows]

    def recent_learned(self, limit: int = 8) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            WORD_SELECT + " WHERE p.status = 2 AND p.learned_at IS NOT NULL ORDER BY p.learned_at DESC LIMIT ?",
            (limit,))]

    def word_of_the_day(self) -> dict | None:
        ids = self._ids("SELECT w.id FROM words w JOIN progress p ON p.word_id = w.id"
                        " WHERE p.status < 2 AND w.turkish <> '' AND w.rank IS NOT NULL"
                        " ORDER BY w.rank LIMIT 1500", ())
        if not ids:
            ids = self._ids("SELECT id FROM words LIMIT 100", ())
        if not ids:
            return None
        rnd = random.Random(today_str())
        return self.get_word(rnd.choice(ids))

    def create_deck(self, name: str, kind: str = "custom", description: str = "", color: str = "#7C5CFF") -> int:
        cur = self.conn.execute("INSERT INTO decks(name, kind, description, color) VALUES(?,?,?,?)",
                                (name.strip() or "Yeni Deste", kind, description, color))
        self.conn.commit()
        return cur.lastrowid

    def rename_deck(self, deck_id: int, name: str):
        self.conn.execute("UPDATE decks SET name=? WHERE id=?", (name.strip(), deck_id))
        self.conn.commit()

    def delete_deck(self, deck_id: int):
        self.conn.execute("DELETE FROM decks WHERE id=?", (deck_id,))
        self.conn.commit()

    def add_to_deck(self, deck_id: int, word_ids: list[int]):
        pos = self.conn.execute("SELECT COALESCE(MAX(position), 0) FROM deck_cards WHERE deck_id=?",
                                (deck_id,)).fetchone()[0]
        for i, wid in enumerate(word_ids, start=1):
            self.conn.execute("INSERT OR IGNORE INTO deck_cards(deck_id, word_id, position) VALUES(?,?,?)",
                              (deck_id, wid, pos + i))
        self.conn.commit()

    def remove_from_deck(self, deck_id: int, word_id: int):
        self.conn.execute("DELETE FROM deck_cards WHERE deck_id=? AND word_id=?", (deck_id, word_id))
        self.conn.commit()

    def list_decks(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT d.*, COUNT(dc.word_id) cards, COALESCE(SUM(p.status = 2), 0) learned"
            " FROM decks d LEFT JOIN deck_cards dc ON dc.deck_id = d.id"
            " LEFT JOIN progress p ON p.word_id = dc.word_id"
            " GROUP BY d.id ORDER BY d.created_at DESC, d.id DESC")]

    def deck_words(self, deck_id: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            WORD_SELECT + " JOIN deck_cards dc ON dc.word_id = w.id WHERE dc.deck_id = ? ORDER BY dc.position",
            (deck_id,))]

    def draft_candidates(self, n: int, levels: list[str] | None, exclude: set[int]) -> list[dict]:
        params: list = []
        lv = self._level_clause(levels, params)
        rows = [dict(r) for r in self.conn.execute(
            WORD_SELECT + " WHERE p.status < 2 AND w.turkish <> ''" + lv + " ORDER BY RANDOM() LIMIT ?",
            params + [n + len(exclude) + 5])]
        rows = [r for r in rows if r["id"] not in exclude]
        return rows[:n]

    def tense_progress(self) -> dict[str, dict]:
        return {r["tense_key"]: dict(r) for r in self.conn.execute("SELECT * FROM tense_progress")}

    def mark_tense_read(self, key: str):
        self.conn.execute("INSERT OR IGNORE INTO tense_progress(tense_key) VALUES(?)", (key,))
        self.conn.execute("UPDATE tense_progress SET read_count = read_count + 1, last_at = ? WHERE tense_key = ?",
                          (now_str(), key))
        self.conn.commit()

    def record_tense_answer(self, key: str, correct: bool):
        self.conn.execute("INSERT OR IGNORE INTO tense_progress(tense_key) VALUES(?)", (key,))
        col = "correct" if correct else "wrong"
        self.conn.execute(f"UPDATE tense_progress SET {col} = {col} + 1, last_at = ? WHERE tense_key = ?",
                          (now_str(), key))
        self._bump_daily(tense_answers=1)
        self.conn.commit()

    def record_tense_score(self, key: str, score: int):
        self.conn.execute("INSERT OR IGNORE INTO tense_progress(tense_key) VALUES(?)", (key,))
        self.conn.execute("UPDATE tense_progress SET best_score = MAX(best_score, ?) WHERE tense_key = ?",
                          (score, key))
        self.conn.commit()

    def reset_progress(self):
        self.conn.execute(
            "UPDATE progress SET status=0, widget_seen=0, reviews=0, correct=0, wrong=0, reps=0, ease=2.5,"
            " interval_days=0, due_at=NULL, last_seen=NULL, last_review=NULL, learned_at=NULL")
        self.conn.execute("DELETE FROM daily_stats")
        self.conn.execute("DELETE FROM review_log")
        self.conn.execute("DELETE FROM tense_progress")
        self.conn.commit()

    def backup(self, target: Path | None = None) -> Path:
        from .config import BACKUP_DIR
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if target is None:
            target = BACKUP_DIR / f"emg_{dt.datetime.now():%Y%m%d_%H%M%S}.db"
        dest = sqlite3.connect(str(target))
        with dest:
            self.conn.backup(dest)
        dest.close()
        return Path(target)

    def restore(self, source: Path):
        source = Path(source)
        test = sqlite3.connect(str(source))
        try:
            tables = {r[0] for r in test.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            test.close()
        if not {"words", "progress", "settings"} <= tables:
            raise ValueError("Bu dosya geçerli bir EMG veritabanı değil.")
        self.backup()
        self.close()
        for suffix in ("-wal", "-shm"):
            extra = Path(str(self.path) + suffix)
            if extra.exists():
                extra.unlink()
        shutil.copyfile(source, self.path)
        self._connect()


def _migrate_legacy_userdata():
    from .config import LEGACY_USER_DIR
    if DB_PATH.exists() or not (LEGACY_USER_DIR / "emg.db").exists():
        return
    shutil.copytree(LEGACY_USER_DIR, USER_DIR, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("ui", "ai_coach"))


def open_database() -> Database:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_userdata()
    return Database(DB_PATH)
