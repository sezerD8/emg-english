from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_MULTI: list[tuple[str, str]] = [
    ("aɪər", "ayır"), ("aɪə", "ayı"), ("aʊər", "auır"), ("aʊə", "auı"),
    ("tʃ", "ç"), ("dʒ", "c"), ("ʧ", "ç"), ("ʤ", "c"),
    ("ŋɡ", "ng"), ("ŋg", "ng"), ("ŋk", "nk"),
    ("juː", "yu"), ("ju", "yu"), ("jʊ", "yu"), ("jə", "yı"),
    ("aɪ", "ay"), ("aʊ", "au"), ("eɪ", "ey"), ("oʊ", "ou"), ("əʊ", "ou"),
    ("ɔɪ", "oy"), ("oɪ", "oy"),
    ("ɪər", "ir"), ("ɪə", "iı"), ("ɛər", "er"), ("eər", "er"), ("eə", "eı"), ("ɛə", "eı"),
    ("ʊər", "ur"), ("ʊə", "uı"),
    ("ɜːr", "ör"), ("ɜr", "ör"), ("ɝː", "ör"), ("ɝ", "ör"), ("ɜː", "ö"),
    ("ɚ", "ır"), ("ər", "ır"),
    ("ɑːr", "ar"), ("ɔːr", "or"),
]

_SINGLE: dict[str, str] = {
    "i": "i", "ɪ": "i", "e": "e", "ɛ": "e", "æ": "e", "ʌ": "a", "ɑ": "a", "ɒ": "o",
    "ɔ": "o", "ʊ": "u", "u": "u", "ə": "ı", "ɐ": "a", "ɜ": "ö", "a": "a", "o": "o",
    "ɨ": "ı", "ᵻ": "i", "ɵ": "ö", "y": "ü",
    "ʃ": "ş", "ʒ": "j", "ŋ": "ng", "j": "y", "r": "r", "ɹ": "r", "ɾ": "t",
    "ɫ": "l", "ʔ": "", "x": "h", "ɡ": "g", "g": "g",
    "b": "b", "d": "d", "f": "f", "h": "h", "k": "k", "l": "l", "m": "m", "n": "n",
    "p": "p", "s": "s", "t": "t", "v": "v", "z": "z", "c": "k", "q": "k",
}

_SKIP = set("/[]ˈˌ.'ˑ()‿-‖|ʰʷ")
_ALLOWED = set("abcçdefgğhıijklmnoöprsştuüvyzw ")
_SPLIT = re.compile(r"\s*[,;]\s*")


@lru_cache(maxsize=20000)
def ipa_to_turkish(ipa: str, keep_w: bool = True, keep_th: bool = False) -> str:
    if not ipa:
        return ""
    text = _SPLIT.split(ipa.strip())[0]
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"([nlmr])̩", r"ı\1", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = unicodedata.normalize("NFC", text)
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in _SKIP:
            i += 1
            continue
        matched = False
        for src, dst in _MULTI:
            if text.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        if ch == "ː":
            i += 1
            continue
        if ch == "θ":
            out.append("th" if keep_th else "t")
        elif ch == "ð":
            out.append("dh" if keep_th else "d")
        elif ch == "w":
            out.append("w" if keep_w else "v")
        elif ch == " ":
            out.append(" ")
        else:
            out.append(_SINGLE.get(ch, ""))
        i += 1
    result = "".join(out)
    result = "".join(ch for ch in result if ch in _ALLOWED)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def pronunciation_for(word: dict, settings_get=None) -> str:
    manual = (word.get("pron_tr") or "").strip()
    if manual:
        return manual
    keep_w, keep_th = True, False
    if settings_get is not None:
        keep_w = bool(settings_get("pron.keep_w"))
        keep_th = bool(settings_get("pron.keep_th"))
    return ipa_to_turkish(word.get("phonetic") or "", keep_w, keep_th)


def clean_ipa(ipa: str) -> str:
    ipa = (ipa or "").strip()
    if not ipa:
        return ""
    ipa = ipa.strip("/[] ")
    return f"/{ipa}/"
