from __future__ import annotations

import json
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

USER_AGENT = "EMG-English/1.0"
POS_MAP = {"noun": "n", "verb": "v", "adjective": "adj", "adverb": "adv", "preposition": "prep",
           "pronoun": "pron", "conjunction": "conj", "interjection": "int", "determiner": "det",
           "exclamation": "int", "numeral": "num"}


def _get_json(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_dictionary(word: str) -> dict:
    url = "https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(word.strip().lower())
    data = _get_json(url)
    result = {"phonetic": "", "example": "", "pos": "", "definition": ""}
    if not isinstance(data, list) or not data:
        return result
    entry = data[0]
    phon = entry.get("phonetic") or ""
    if not phon:
        for p in entry.get("phonetics", []):
            if p.get("text"):
                phon = p["text"]
                if "-us" in (p.get("audio") or ""):
                    break
    result["phonetic"] = phon.strip("/[] ")
    poses = []
    for meaning in entry.get("meanings", []):
        pos = POS_MAP.get(meaning.get("partOfSpeech", ""), "")
        if pos and pos not in poses:
            poses.append(pos)
        for d in meaning.get("definitions", []):
            if not result["definition"] and d.get("definition"):
                result["definition"] = d["definition"]
            if not result["example"] and d.get("example"):
                result["example"] = d["example"]
    result["pos"] = ",".join(poses[:3])
    return result


def translate(text: str, src: str = "en", dst: str = "tr") -> str:
    url = ("https://api.mymemory.translated.net/get?" +
           urllib.parse.urlencode({"q": text, "langpair": f"{src}|{dst}"}))
    data = _get_json(url)
    translated = (data.get("responseData") or {}).get("translatedText") or ""
    if "MYMEMORY WARNING" in translated.upper():
        raise RuntimeError("Çeviri servisinin günlük limiti doldu.")
    options = [translated.strip()]
    for m in data.get("matches", [])[:6]:
        t = (m.get("translation") or "").strip()
        if t and t.lower() not in (o.lower() for o in options) and len(t) < 40 and float(m.get("match", 0)) >= 0.7:
            options.append(t)
    return ", ".join(o for o in options[:3] if o)


def fetch_word_info(word: str) -> dict:
    info = {"english": word.strip(), "phonetic": "", "pos": "", "example": "", "example_tr": "",
            "turkish": "", "errors": []}
    try:
        info.update(fetch_dictionary(word))
    except Exception as exc:  # noqa: BLE001
        info["errors"].append(f"Sözlük: {exc}")
    try:
        info["turkish"] = translate(word)
    except Exception as exc:  # noqa: BLE001
        info["errors"].append(f"Çeviri: {exc}")
    if info.get("example"):
        try:
            info["example_tr"] = translate(info["example"]).split(", ")[0]
        except Exception:  # noqa: BLE001
            pass
    return info


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Relay(QObject):
    def __init__(self, on_done, on_error):
        super().__init__()
        self.on_done = on_done
        self.on_error = on_error

    @Slot(object)
    def handle_done(self, result):
        _ACTIVE.discard(self)
        if self.on_done:
            self.on_done(result)

    @Slot(str)
    def handle_error(self, message):
        _ACTIVE.discard(self)
        if self.on_error:
            self.on_error(message)


class _Task(QRunnable):
    def __init__(self, fn, args, signals):
        super().__init__()
        self.fn, self.args, self.signals = fn, args, signals

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


_ACTIVE: set = set()


def run_async(fn, *args, on_done=None, on_error=None):
    relay = _Relay(on_done, on_error)
    signals = _Signals()
    signals.done.connect(relay.handle_done)
    signals.failed.connect(relay.handle_error)
    relay.signals = signals
    _ACTIVE.add(relay)
    QThreadPool.globalInstance().start(_Task(fn, args, signals))
