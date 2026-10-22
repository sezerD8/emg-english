from __future__ import annotations

import re

from .config import DATA_VERSION, LEVELS, WORDS_DIR, kind_of, level_for_rank
from .database import Database

_DIRECTIVE = re.compile(r"#!\s*level\s*=\s*(\w+)", re.IGNORECASE)


def parse_word_files() -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for path in sorted(WORDS_DIR.glob("*.txt")):
        file_level = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            m = _DIRECTIVE.match(line)
            if m:
                file_level = m.group(1).upper()
                continue
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            english = parts[0]
            key = english.lower()
            if not english or key in seen:
                continue
            seen.add(key)
            entries.append({
                "english": english,
                "pos": parts[1],
                "turkish": parts[2],
                "phonetic": parts[3] if len(parts) > 3 else "",
                "example": parts[4] if len(parts) > 4 else "",
                "example_tr": parts[5] if len(parts) > 5 else "",
                "level": file_level,
            })

    groups: dict[str, list[dict]] = {}
    for w in entries:
        groups.setdefault(kind_of(w["pos"]), []).append(w)
    order: list[tuple[float, dict]] = []
    for items in groups.values():
        n = len(items)
        order += [((i + 0.5) / n, w) for i, w in enumerate(items)]
    order.sort(key=lambda t: t[0])

    words = []
    word_rank = 0
    for rank, (_, w) in enumerate(order, start=1):
        w["rank"] = rank
        if kind_of(w["pos"]) == "word":
            word_rank += 1
            w["level"] = w["level"] or level_for_rank(word_rank)
        else:
            w["level"] = w["level"] or "B2"
        words.append(w)
    return words


def seed_builtin(db: Database, force: bool = False) -> int:
    if not force and db.get("meta.data_version", 0) == DATA_VERSION and db.word_count("builtin") > 0:
        return 0
    words = parse_word_files()
    if not words:
        return 0

    keep = {w["english"].lower() for w in words}
    stale = [r[0] for r in db.conn.execute("SELECT id, english FROM words WHERE source IN ('builtin', 'edited')")
             if r[1].lower() not in keep]
    if stale:
        db.backup()
        db.conn.executemany("DELETE FROM words WHERE id = ?", [(i,) for i in stale])

    db.conn.executemany(
        "INSERT INTO words(english, turkish, phonetic, pos, level, rank, example, example_tr, source)"
        " VALUES(:english, :turkish, :phonetic, :pos, :level, :rank, :example, :example_tr, 'builtin')"
        " ON CONFLICT(english) DO UPDATE SET"
        "   rank = excluded.rank, level = excluded.level,"
        "   turkish = CASE WHEN words.source = 'builtin' THEN excluded.turkish ELSE words.turkish END,"
        "   phonetic = CASE WHEN words.source = 'builtin' THEN excluded.phonetic ELSE words.phonetic END,"
        "   pos = CASE WHEN words.source = 'builtin' THEN excluded.pos ELSE words.pos END,"
        "   example = CASE WHEN words.source = 'builtin' THEN excluded.example ELSE words.example END,"
        "   example_tr = CASE WHEN words.source = 'builtin' THEN excluded.example_tr ELSE words.example_tr END",
        words,
    )
    db.conn.execute("INSERT OR IGNORE INTO progress(word_id) SELECT id FROM words")
    db.conn.commit()

    levels = [lv for lv in (db.get("widget.levels") or []) if lv in LEVELS]
    if levels != db.get("widget.levels"):
        db.set("widget.levels", levels or list(LEVELS))
    db.set("meta.data_version", DATA_VERSION)
    return len(words)
