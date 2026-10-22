from __future__ import annotations

from PySide6.QtCore import QLocale, QObject, QTimer, Signal

try:
    from PySide6.QtTextToSpeech import QTextToSpeech
except ImportError:
    QTextToSpeech = None

ENGINE_ORDER = ["winrt", "sapi"]


class Speaker(QObject):
    voicesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engines: dict[str, object] = {}
        self._voices: dict[str, tuple] = {}
        self._pending: set[str] = set()
        self._current: str | None = None
        self._preferred = ""
        self._en_label: str | None = None
        self._tr_voice: tuple | None = None
        self._queue: list[tuple] = []
        self._seq_engine: str | None = None
        self._rate = 0.0
        if QTextToSpeech is None:
            return
        try:
            names = [e for e in QTextToSpeech.availableEngines() if e != "mock"]
        except Exception:
            names = []
        names.sort(key=lambda e: ENGINE_ORDER.index(e) if e in ENGINE_ORDER else 99)
        for name in names:
            try:
                eng = QTextToSpeech(name, self)
            except Exception:
                continue
            self._engines[name] = eng
            self._pending.add(name)
            eng.stateChanged.connect(lambda state, n=name: self._on_state(n, state))
            self._on_state(name, eng.state())

    def _on_state(self, name: str, state):
        if name not in self._pending:
            if state == QTextToSpeech.State.Ready and name == self._seq_engine and self._queue:
                QTimer.singleShot(300, lambda n=name: self._advance_if_idle(n))
            return
        if state not in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error):
            return
        self._pending.discard(name)
        if state == QTextToSpeech.State.Ready:
            self._collect(name)
        if not self._pending:
            self._finish()

    def _collect(self, name: str):
        eng = self._engines[name]
        original = eng.locale()
        for loc in eng.availableLocales():
            lang = loc.language()
            if lang not in (QLocale.Language.English, QLocale.Language.Turkish):
                continue
            eng.setLocale(loc)
            for v in eng.availableVoices():
                label = f"{v.name()} ({loc.name()}, {name})"
                if lang == QLocale.Language.English:
                    self._voices[label] = (name, loc, v)
                elif self._tr_voice is None:
                    self._tr_voice = (name, loc, v)
        eng.setLocale(original)

    def _finish(self):
        if self._preferred in self._voices:
            self.set_voice(self._preferred)
        elif self._voices:
            us = [n for n in self._voices if "en_US" in n] or list(self._voices)
            self._apply_voice(us[0])
        self.voicesChanged.emit()

    @property
    def available(self) -> bool:
        return bool(self._engines)

    def voices(self) -> list[str]:
        return list(self._voices)

    @property
    def has_turkish(self) -> bool:
        return self._tr_voice is not None

    def _apply_voice(self, name: str):
        engine_name, loc, voice = self._voices[name]
        eng = self._engines[engine_name]
        eng.setLocale(loc)
        eng.setVoice(voice)
        eng.setRate(self._rate)
        self._current = engine_name
        self._en_label = name

    def set_voice(self, name: str):
        self._preferred = name
        if name in self._voices:
            self._apply_voice(name)

    def set_rate(self, rate: float):
        self._rate = max(-1.0, min(1.0, float(rate)))
        for eng in self._engines.values():
            eng.setRate(self._rate)

    def _stop_all(self):
        self._queue.clear()
        self._seq_engine = None
        for eng in self._engines.values():
            try:
                eng.stop()
            except Exception:
                pass

    def speak(self, text: str):
        if not text or self._current is None:
            return
        try:
            self._stop_all()
            if self._en_label:
                self._apply_voice(self._en_label)
            self._engines[self._current].say(text)
        except Exception:
            pass

    def speak_pair(self, english: str, turkish: str):
        if self._current is None or not english:
            return
        self._stop_all()
        en_engine, en_loc, en_voice = self._voices[self._en_label]
        self._queue = [(en_engine, en_loc, en_voice, english)]
        if turkish and self._tr_voice is not None:
            self._queue.append((*self._tr_voice, turkish))
            self._queue.append((en_engine, en_loc, en_voice, english))
        self._play_next()

    def _advance_if_idle(self, name: str):
        eng = self._engines.get(name)
        if eng is not None and name == self._seq_engine and self._queue \
                and eng.state() == QTextToSpeech.State.Ready:
            self._seq_engine = None
            self._play_next()

    def _play_next(self):
        if not self._queue:
            return
        engine_name, loc, voice, text = self._queue.pop(0)
        eng = self._engines.get(engine_name)
        if eng is None:
            return
        try:
            eng.setLocale(loc)
            eng.setVoice(voice)
            eng.setRate(self._rate)
            self._seq_engine = engine_name
            eng.say(text)
        except Exception:
            self._seq_engine = None
