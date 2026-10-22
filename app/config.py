from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "EMG English"
APP_ID = "EMGEnglish"

FROZEN = getattr(sys, "frozen", False)

BASE_DIR = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
WORDS_DIR = DATA_DIR / "words"
USER_DIR = Path(os.environ.get("APPDATA") or Path.home()) / APP_ID
DB_PATH = USER_DIR / "emg.db"
BACKUP_DIR = USER_DIR / "backups"
LEGACY_USER_DIR = Path(__file__).resolve().parent.parent / "userdata"

DATA_VERSION = 2

LEVELS = ["B1", "B2"]
LEVEL_BOUNDS = [(1500, "B1"), (10 ** 9, "B2")]

LEVEL_COLORS = {
    "B1": "#3A6EA5",
    "B2": "#7B5EA7",
    "C1": "#C98A1B",
}
LEVEL_RARITY = {"B1": "Ender", "B2": "Epik", "C1": "Efsanevi"}

POS_TR = {
    "n": "isim",
    "v": "fiil",
    "adj": "sıfat",
    "adv": "zarf",
    "prep": "edat",
    "pron": "zamir",
    "conj": "bağlaç",
    "det": "belirleyici",
    "int": "ünlem",
    "num": "sayı",
    "modal": "modal",
    "aux": "yardımcı fiil",
    "phr": "phrasal verb",
    "pat": "kalıp",
    "expr": "hazır cümle",
    "idiom": "deyim",
    "prov": "atasözü",
}

KINDS = {
    "word": "Kelimeler",
    "phr": "Phrasal verb",
    "pat": "Kalıplar",
    "expr": "Hazır cümleler",
    "idiom": "Deyimler",
    "prov": "Atasözleri",
}
PHRASE_POS = ("phr", "pat", "expr", "idiom", "prov")


def kind_of(pos: str | None) -> str:
    first = (pos or "").split(",")[0].strip()
    return first if first in PHRASE_POS else "word"

STATUS_NEW, STATUS_LEARNING, STATUS_LEARNED = 0, 1, 2
STATUS_TR = {STATUS_NEW: "Yeni", STATUS_LEARNING: "Öğreniliyor", STATUS_LEARNED: "Öğrenildi"}
STATUS_COLORS = {STATUS_NEW: "#8A929E", STATUS_LEARNING: "#B7791F", STATUS_LEARNED: "#2F7A4C"}

LEARNED_REPS = 4


def level_for_rank(rank: int | None) -> str:
    if rank is None:
        return "B2"
    for bound, level in LEVEL_BOUNDS:
        if rank <= bound:
            return level
    return "B2"


DEFAULT_SETTINGS: dict = {
    "widget.enabled": True,
    "widget.interval": 8,
    "widget.order": "smart",
    "widget.source": "smart",
    "widget.deck_id": None,
    "widget.levels": ["B1", "B2"],
    "widget.kinds": list(KINDS),
    "widget.quiz_mode": False,
    "widget.reveal_delay": 3,
    "widget.tense_mix": 0,
    "widget.auto_speak": False,
    "widget.fade": True,
    "widget.hotkeys": True,
    "widget.seq_pos": 0,
    "widget.fs_mode": "show_voice",
    "widget.fs_voice_interval": 20,
    "widget.bg_color": "#1C2028",
    "widget.bg_opacity": 60,
    "widget.text_opacity": 100,
    "widget.corner_radius": 8,
    "widget.padding": 14,
    "widget.min_width": 300,
    "widget.font_family": "Bahnschrift",
    "widget.align": "center",
    "widget.shadow": True,
    "widget.border": False,
    "widget.show_tr": True,
    "widget.show_ipa": True,
    "widget.show_pron": True,
    "widget.show_ex": True,
    "widget.show_badge": False,
    "widget.size_en": 26,
    "widget.size_tr": 17,
    "widget.size_ipa": 15,
    "widget.size_pron": 15,
    "widget.size_ex": 14,
    "widget.color_en": "#FFFFFF",
    "widget.color_tr": "#FFE14D",
    "widget.color_ipa": "#C9D1DC",
    "widget.color_pron": "#C9D1DC",
    "widget.color_ex": "#E3E7ED",
    "widget.position": "top-right",
    "widget.margin": 24,
    "widget.screen": 0,
    "widget.custom_x": 120,
    "widget.custom_y": 120,
    "widget.click_through": False,
    "app.username": "",
    "app.theme": "light",
    "app.daily_goal": 20,
    "app.start_with_windows": False,
    "app.start_minimized": False,
    "app.close_to_tray": True,
    "app.tts_voice": "",
    "app.tts_rate": 0.0,
    "training.session_size": 20,
    "training.source": "smart",
    "pron.keep_w": True,
    "pron.keep_th": False,
    "coach.model": "opus",
    "coach.session_id": "",
    "coach.history": [],
}
