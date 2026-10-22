from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from .config import LEVELS, USER_DIR

WORK_DIR = USER_DIR / "ai_coach"

MODELS = {"opus": "Opus (en iyi)", "sonnet": "Sonnet (hızlı)", "haiku": "Haiku (en hızlı)"}

SYSTEM_PROMPT = """\
You are "Koç", the AI language coach inside EMG English, a Windows desktop app that helps a native \
Turkish speaker learn English (vocabulary widget, spaced-repetition training, tense lessons). You are \
fully fluent in both Turkish and English and know the typical difficulties Turkish speakers have with \
English: articles (a/an/the), tense and aspect choices (present perfect vs. past simple, continuous \
forms), word order, prepositions, phrasal verbs, countable/uncountable nouns, false friends, and \
sounds such as th, w/v, and short/long vowels.

How to answer:
- Reply in the language the learner writes in. When they write in Turkish, explain in Turkish and keep \
English examples in English. When they write in English, answer in English (they are practising), \
using simple, natural sentences matched to their level.
- If the learner's English contains mistakes, first answer what they said, then add a short \
"Düzeltme" note: the corrected sentence in **bold** and a one-line Turkish explanation of why. Correct \
only real errors; do not nitpick style.
- Translations: give the most natural translation first, then useful alternatives with nuance \
(formal/informal, British/American) when it matters.
- Grammar: give the rule in plain Turkish, a short formula, and 2-3 everyday example sentences with \
Turkish translations. Point out the most common mistake Turkish speakers make with it.
- Words: meaning(s) in Turkish, part of speech, an example sentence, common collocations, and \
pronunciation as IPA plus a Turkish-letter reading (e.g. "thought /θɔːt/, okunuşu: thoot").
- Practice and role-play: when asked for a quiz, dialogue or role-play, ask one question or play one \
turn at a time and wait for the learner's reply, then give feedback.
- Keep answers short and scannable for a chat window: no long preambles, no headings bigger than bold \
text, no emoji. Markdown (bold, italics, lists, small tables) is rendered.
- Be warm and encouraging like a good teacher, but honest. Stay focused on language learning; if the \
learner wants to chat about another topic, do it in English as speaking practice.
"""


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for candidate in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if candidate.exists():
            return str(candidate)
    return None


def learner_profile(db) -> str:
    tot = db.totals()
    lines = []
    name = (db.get("app.username") or "").strip()
    if name:
        lines.append(f"Name: {name}")
    lines.append(f"Words learned: {tot['learned']} of {tot['total']}; currently learning: {tot['learning']}.")
    levels = {r["level"]: r for r in db.level_breakdown()}
    done = [lv for lv in LEVELS
            if levels.get(lv, {}).get("total") and levels[lv]["learned"] / levels[lv]["total"] >= 0.6]
    lines.append(f"Estimated level: {'above ' + done[-1] if done else 'intermediate (knows A1-A2 basics)'}.")
    hard = db.get_words(db.session_word_ids("hard", 12))
    if hard:
        lines.append("Words they often get wrong: " + ", ".join(f"{w['english']} ({w['turkish']})" for w in hard))
    recent = db.recent_learned(8)
    if recent:
        lines.append("Recently learned: " + ", ".join(w["english"] for w in recent))
    return "\n".join(lines)


class CoachAgent(QObject):
    delta = Signal(str)
    finished = Signal(str)
    failed = Signal(str)
    busyChanged = Signal(bool)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.proc: QProcess | None = None
        self._buf = b""
        self._answer = ""
        self._busy = False
        self._resuming = False
        self._session = ""
        self._last_prompt = ""

    @property
    def busy(self) -> bool:
        return self._busy

    def _set_busy(self, on: bool):
        if self._busy != on:
            self._busy = on
            self.busyChanged.emit(on)

    def available(self) -> bool:
        return find_claude() is not None

    def _start(self) -> bool:
        exe = find_claude()
        if not exe:
            return False
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        session = self.ctx.get("coach.session_id") or ""
        self._resuming = bool(session)
        self._session = session or str(uuid.uuid4())
        args = [
            "-p", "--input-format", "stream-json", "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            "--safe-mode", "--tools", "",
            "--model", self.ctx.get("coach.model") or "opus", "--effort", "low",
            "--system-prompt", SYSTEM_PROMPT + "\nAbout the learner (from the app's progress data):\n"
                                              + learner_profile(self.ctx.db),
        ]
        args += ["--resume", self._session] if self._resuming else ["--session-id", self._session]
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(WORK_DIR))
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._on_exit)
        self.proc.errorOccurred.connect(self._on_error)
        self._buf = b""
        self.proc.start(exe, args)
        return True

    def _running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def warm_up(self):
        if not self._busy and not self._running():
            self._start()

    def shutdown(self):
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        for sig in (proc.readyReadStandardOutput, proc.finished, proc.errorOccurred):
            sig.disconnect()
        if proc.state() != QProcess.ProcessState.NotRunning:
            proc.kill()
            proc.waitForFinished(2000)
        proc.deleteLater()

    def send(self, text: str):
        if self._busy:
            return
        if not self._running() and not self._start():
            self.failed.emit("Claude Code bulunamadı. Kurulum: https://claude.com/claude-code")
            return
        self._answer = ""
        self._last_prompt = text
        self._set_busy(True)
        line = {"type": "user", "message": {"role": "user", "content": text}}
        self.proc.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))

    def stop(self):
        if not self._busy:
            return
        partial = self._answer
        self.shutdown()
        self._set_busy(False)
        self.finished.emit(partial + ("\n\n" if partial else "") + "*(durduruldu)*")
        self.warm_up()

    def new_chat(self):
        self.shutdown()
        self.ctx.set("coach.session_id", "")
        self._set_busy(False)
        self.warm_up()

    def set_model(self, model: str):
        self.ctx.set("coach.model", model)
        if not self._busy:
            self.shutdown()
            self.warm_up()

    def _read(self):
        self._buf += bytes(self.proc.readAllStandardOutput())
        *lines, self._buf = self._buf.split(b"\n")
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            self._handle(msg)

    def _handle(self, msg: dict):
        kind = msg.get("type")
        if kind == "stream_event":
            ev = msg.get("event") or {}
            d = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                self._answer += d.get("text", "")
                self.delta.emit(d.get("text", ""))
            elif ev.get("type") == "content_block_start" and self._answer and \
                    (ev.get("content_block") or {}).get("type") == "text":
                self._answer += "\n\n"
                self.delta.emit("\n\n")
        elif kind == "result":
            if msg.get("is_error") and self._resuming and not msg.get("num_turns"):
                return
            self._set_busy(False)
            if msg.get("is_error"):
                self.failed.emit(self._explain(str(msg.get("result") or msg.get("subtype") or "")))
            else:
                if not self.ctx.get("coach.session_id"):
                    self.ctx.set("coach.session_id", self._session)
                self.finished.emit(self._answer or str(msg.get("result") or ""))

    def _on_exit(self, code: int, _status):
        err = bytes(self.proc.readAllStandardError()).decode("utf-8", errors="replace") if self.proc else ""
        proc, self.proc = self.proc, None
        if proc is not None:
            proc.deleteLater()
        lost = self._resuming and not self._answer and "no conversation found" in err.lower()
        if lost:
            self.ctx.set("coach.session_id", "")
        if not self._busy:
            if lost:
                self.warm_up()
            return
        if lost:
            self._set_busy(False)
            self.send(self._last_prompt)
            return
        self._set_busy(False)
        self.failed.emit(self._explain(err.strip()) or f"Claude Code beklenmedik şekilde kapandı (kod {code}).")

    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.proc = None
            if self._busy:
                self._set_busy(False)
                self.failed.emit("Claude Code başlatılamadı. Kurulu ve güncel olduğundan emin ol.")

    @staticmethod
    def _explain(text: str) -> str:
        low = text.lower()
        if "login" in low or "auth" in low or "api key" in low:
            return ("Claude Code'da oturum açılmamış. Bir terminalde `claude` yazıp giriş yap, "
                    "sonra tekrar dene.\n\n" + text)
        if "rate" in low and "limit" in low or "usage limit" in low:
            return "Claude kullanım limitine ulaşıldı. Biraz sonra tekrar dene.\n\n" + text
        return text
