from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QScrollArea, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from .. import __version__, theme
from ..config import APP_NAME, BACKUP_DIR, DB_PATH
from ..theme import THEME_NAMES
from ..pronunciation import ipa_to_turkish
from ..seed import seed_builtin
from ..winutil import IS_WINDOWS, autostart_enabled, set_autostart
from .common import Page, button, confirm, info, label

PRON_SAMPLES = [("think", "θɪŋk"), ("world", "wɝːld"), ("weather", "ˈwɛðər"), ("thank you", "ˈθæŋk juː")]


class SettingsPage(Page):
    def __init__(self, ctx):
        super().__init__("Ayarlar", "Uygulama, ses, okunuş ve veri ayarları.")
        self.ctx = ctx
        self.db = ctx.db
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(0, 0, 8, 0)
        self.lay.setSpacing(12)
        scroll.setWidget(inner)
        self.root.addWidget(scroll, 1)

        f = self._group("Görünüm")
        theme_row = QHBoxLayout()
        self.theme_combo = QComboBox()
        for key, name in THEME_NAMES.items():
            self.theme_combo.addItem(name, key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.ctx.get("app.theme"))))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        theme_row.addWidget(self.theme_combo)
        self.restart_btn = button("Yeniden başlat ve uygula", "Primary", self._restart)
        self.restart_btn.hide()
        theme_row.addWidget(self.restart_btn)
        theme_row.addStretch(1)
        f.addRow("Tema:", theme_row)

        f = self._group("Günlük hedef")
        self.goal = QSpinBox()
        self.goal.setRange(5, 500)
        self.goal.setSuffix(" tekrar / gün")
        self.goal.setValue(int(self.ctx.get("app.daily_goal")))
        self.goal.valueChanged.connect(lambda v: self.ctx.set("app.daily_goal", int(v)))
        f.addRow("Her gün:", self.goal)

        f = self._group("Uygulama")
        self.autostart = QCheckBox("Windows açılınca otomatik başlat (widget hemen çalışsın)")
        self.autostart.setChecked(autostart_enabled())
        self.autostart.setEnabled(IS_WINDOWS)
        self.autostart.toggled.connect(self._toggle_autostart)
        f.addRow(self.autostart)
        for key, text in (("app.start_minimized", "Simge durumunda başlat (sadece widget + sistem tepsisi)"),
                          ("app.close_to_tray", "Pencereyi kapatınca sistem tepsisine küçült (widget çalışmaya devam eder)")):
            cb = QCheckBox(text)
            cb.setChecked(bool(self.ctx.get(key)))
            cb.toggled.connect(lambda v, k=key: self.ctx.set(k, bool(v)))
            f.addRow(cb)

        f = self._group("Seslendirme")
        self.voice = QComboBox()
        self._fill_voices()
        self.voice.currentIndexChanged.connect(self._voice_changed)
        self.ctx.speaker.voicesChanged.connect(self._fill_voices)
        f.addRow("Ses:", self.voice)
        rate_row = QHBoxLayout()
        self.rate = QSlider(Qt.Orientation.Horizontal)
        self.rate.setRange(-10, 10)
        self.rate.setValue(int(float(self.ctx.get("app.tts_rate")) * 10))
        self.rate.valueChanged.connect(self._rate_changed)
        rate_row.addWidget(label("Yavaş", "Dim"))
        rate_row.addWidget(self.rate, 1)
        rate_row.addWidget(label("Hızlı", "Dim"))
        rate_row.addWidget(button("Sesi dene", None, lambda: self.ctx.speak("Hello! This is how I sound. "
                                                                          "Practice makes perfect.")))
        f.addRow("Hız:", rate_row)
        f.addRow(label("Daha fazla İngilizce ses için: Windows Ayarlar → Zaman ve dil → Konuşma → Ses ekle.",
                       "Dim", wrap=True))

        f = self._group("Türkçe okunuş yazımı")
        self.keep_w = QCheckBox("'w' sesini koru (world → wörld). Kapalıysa 'v' yazılır (vörld).")
        self.keep_w.setChecked(bool(self.ctx.get("pron.keep_w")))
        self.keep_w.toggled.connect(lambda v: self._pron_changed("pron.keep_w", v))
        self.keep_th = QCheckBox("'th' seslerini ayrı göster (think → think). Kapalıysa t/d yazılır (tink).")
        self.keep_th.setChecked(bool(self.ctx.get("pron.keep_th")))
        self.keep_th.toggled.connect(lambda v: self._pron_changed("pron.keep_th", v))
        f.addRow(self.keep_w)
        f.addRow(self.keep_th)
        self.pron_sample = label("", "Muted")
        f.addRow("Örnek:", self.pron_sample)
        self._update_pron_sample()

        f = self._group("Veri ve yedekleme")
        f.addRow("Veritabanı:", label(str(DB_PATH), "Muted", wrap=True))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("Şimdi yedekle", "Primary", self._backup))
        row.addWidget(button("Yedekten geri yükle", None, self._restore))
        row.addWidget(button("Klasörü aç", None,
                             lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DB_PATH.parent)))))
        row.addStretch(1)
        f.addRow(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(button("Kelime listesini yeniden yükle", None, self._reseed,
                              "Gömülü 5000 kelimelik listeyi kontrol eder, eksikleri ekler. İlerlemen korunur."))
        row2.addWidget(button("Tüm ilerlemeyi sıfırla", "Danger", self._reset_progress))
        row2.addStretch(1)
        f.addRow(row2)

        about = QGroupBox("ℹ Hakkında")
        al = QVBoxLayout(about)
        al.addWidget(label(
            f"<b>{APP_NAME}</b> v{__version__}<br>"
            "Gün boyu İngilizceye maruz kal: widget kelimeleri sürekli döndürür, eğitim modları aralıklı tekrarla "
            "kalıcı öğrenmeyi sağlar.<br><br>"
            "Ücretsiz servisler: <i>dictionaryapi.dev</i> (fonetik/örnek), <i>MyMemory</i> (çeviri).", wrap=True))
        self.lay.addWidget(about)
        self.lay.addStretch(1)

    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        self.lay.addWidget(box)
        return form

    def _toggle_autostart(self, on: bool):
        ok = set_autostart(on)
        self.ctx.set("app.start_with_windows", bool(on) if ok else not on)
        if not ok:
            info(self, "Hata", "Başlangıç ayarı değiştirilemedi.")

    def _theme_changed(self):
        self.ctx.set("app.theme", self.theme_combo.currentData())
        self.restart_btn.setVisible(self.theme_combo.currentData() != theme.CURRENT)

    def _restart(self):
        if self.ctx.restart_app:
            self.ctx.restart_app()
        else:
            info(self, "Tema", "Yeni tema, uygulamayı bir sonraki açışında uygulanır.")

    def _fill_voices(self):
        self.voice.blockSignals(True)
        self.voice.clear()
        voices = self.ctx.speaker.voices()
        self.voice.setEnabled(bool(voices))
        if not voices:
            self.voice.addItem("İngilizce ses bulunamadı (Windows → Konuşma ayarlarından ekleyebilirsin)", "")
        for v in voices:
            self.voice.addItem(v, v)
        i = self.voice.findData(self.ctx.get("app.tts_voice"))
        if i >= 0:
            self.voice.setCurrentIndex(i)
        self.voice.blockSignals(False)

    def _voice_changed(self):
        v = self.voice.currentData()
        if v:
            self.ctx.set("app.tts_voice", v)
            self.ctx.apply_tts_settings()
            self.ctx.speak("Hello")

    def _rate_changed(self, v: int):
        self.ctx.set("app.tts_rate", v / 10)
        self.ctx.apply_tts_settings()

    def _pron_changed(self, key, value):
        self.ctx.set(key, bool(value))
        self._update_pron_sample()
        self.ctx.wordsChanged.emit()

    def _update_pron_sample(self):
        kw, kt = bool(self.ctx.get("pron.keep_w")), bool(self.ctx.get("pron.keep_th"))
        self.pron_sample.setText(",   ".join(f"<b>{en}</b> → {ipa_to_turkish(ipa, kw, kt)}"
                                                for en, ipa in PRON_SAMPLES))

    def _backup(self):
        path = self.db.backup()
        info(self, "Yedeklendi", f"Yedek oluşturuldu:\n{path}")

    def _restore(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Yedek seç", str(BACKUP_DIR), "Veritabanı (*.db)")
        if not path:
            return
        if not confirm(self, "Geri yükle", "Mevcut veriler bu yedekle değiştirilsin mi?\n"
                                           "(Önce mevcut durumun otomatik yedeği alınır.)"):
            return
        try:
            self.db.restore(Path(path))
        except Exception as exc:  # noqa: BLE001
            info(self, "Hata", f"Geri yüklenemedi: {exc}")
            return
        self.ctx.wordsChanged.emit()
        self.ctx.progressChanged.emit()
        self.ctx.decksChanged.emit()
        info(self, "Tamam", "Yedek geri yüklendi. Bazı ayarların tam uygulanması için uygulamayı yeniden başlat.")

    def _reseed(self):
        n = seed_builtin(self.db, force=True)
        self.ctx.wordsChanged.emit()
        info(self, "Tamam", f"Gömülü liste kontrol edildi ({n} kelime). Toplam: {self.db.word_count()} kelime.")

    def _reset_progress(self):
        if not confirm(self, "İlerlemeyi sıfırla", "TÜM ilerleme (öğrenilenler, istatistikler, seri, tense "
                                                    "skorları) silinecek. Kelimeler ve desteler kalır.\n"
                                                    "Önce otomatik yedek alınır. Emin misin?"):
            return
        self.db.backup()
        self.db.reset_progress()
        self.ctx.progressChanged.emit()
        info(self, "Sıfırlandı", "İlerleme sıfırlandı. Yedek: " + str(BACKUP_DIR))
