# EMG English

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A Windows desktop app that keeps you exposed to English all day. An always-on-top widget cycles through
words and phrases in a corner of your screen while you game, work or browse, and a spaced-repetition trainer
turns that exposure into long-term memory.

EMG English is made for **Turkish speakers learning English**: every entry comes with its Turkish meaning,
IPA and a Turkish-letter pronunciation guide, and the interface is in Turkish.

## Features

- **Overlay widget**: transparent, always on top, hidden from the taskbar. Shows the English word, its
  Turkish meaning, IPA, Turkish pronunciation and an example sentence. Stays visible over borderless and
  windowed fullscreen games.
- **~4,150 entries**: ~3,260 words ordered by frequency (B1/B2) plus ~890 phrasal verbs, sentence patterns,
  ready-made phrases, idioms and proverbs, each with a translated example.
- **Training**: five modes (flashcards with spaced repetition, English→Turkish, Turkish→English, typing,
  listening) with a daily goal and smart word selection.
- **Library**: browse, search, filter and edit every entry, add notes and favorites, build decks, fill in
  missing data from free online dictionaries, import/export CSV.
- **Tenses**: all 12 tenses plus *used to*, conditionals, passive voice and modals, with Turkish explanations,
  formulas, examples, common mistakes and quizzes.
- **Card Draft**: build your own deck by drafting cards like in a card game (rarity = level).
- **AI Coach** (optional): chat with a bilingual language coach for translations, grammar, vocabulary,
  pronunciation and conversation practice. See [AI Coach](#ai-coach).
- **Light and dark themes**, a custom dark title bar and native Windows window behavior (Aero Snap, resizing,
  system menu).

## Download

Grab `EMG-English.exe` from the [**Releases**](https://github.com/sezerD8/emg-english/releases/latest) page
and run it. No installer or Python required (Windows 10/11).

> The executable is not code-signed, so Windows SmartScreen may warn on first launch:
> **More info → Run anyway**.

Run `EMG-English.exe --minimized` to start with only the widget and the tray icon.

## Widget

Five lines: **English word → Turkish meaning → IPA → Turkish pronunciation → example sentence**. Choose
which entry types rotate under Widget → *Content*.

- Drag to move, right-click for the menu, double-click to hear the word. The word does not change while the
  mouse is over it.
- **Game mode** makes the widget click-through so it never blocks your game.
- Interval, source, order, levels, colors, opacity, font, size of each line, alignment, nine preset positions
  or a custom position, and monitor are all configurable with a live preview.

### Fullscreen games

The widget follows the foreground window:

- **Borderless / windowed fullscreen** (and F11 video): the widget is kept on top, refreshed four times a
  second so games that push themselves forward don't cover it.
- **Exclusive fullscreen**: Windows does not allow any window to draw over it. Overlays like Discord or
  Steam inject code into the game to get around this, which risks bans in anti-cheat games, so EMG English
  doesn't. Instead, the word and its meaning are **read aloud**. For the visual widget, switch the game to
  borderless or windowed fullscreen.

The behavior is configurable under Widget → *Fullscreen and games*.

### Global hotkeys (work in games too)

| Hotkey | Action |
|---|---|
| `Ctrl+Alt+→` / `Ctrl+Alt+←` | Next / previous word |
| `Ctrl+Alt+H` | Show / hide widget |
| `Ctrl+Alt+P` | Pause / resume |
| `Ctrl+Alt+L` | Mark as learned |
| `Ctrl+Alt+F` | Toggle favorite |
| `Ctrl+Alt+S` | Speak |
| `Ctrl+Alt+R` | Reveal meaning (active recall mode) |
| `Ctrl+Alt+C` | Toggle game mode |

## How learning works

- The 2,000 most common words (A1–A2) are left out; they are archived in `app/data/words_archive/`. The
  remaining words become B1 (first 1,500) and B2 by frequency. Words you add yourself are C1.
- Phrasal verbs, patterns, phrases, idioms and proverbs are spread evenly between words.
- **Smart widget**: shows words you are learning more often, introduces new ones (least-seen first) and
  occasionally repeats learned ones. New words you see often on the widget come first in training.
- **Spaced repetition (SM-2 style)**: each correct answer pushes the next review further out
  (1 day → 3 days → …). After **4 successful on-time reviews** a word counts as learned. A wrong answer resets
  it and asks again 10 minutes later.

## AI Coach

The coach runs [Claude Code](https://claude.com/claude-code) installed on your computer as a background
language-coach agent. **No API key is needed**: it uses the account you are signed in with in Claude Code,
and EMG English never sees or stores your credentials.

The agent has no tools (it cannot read files or run commands) and only chats. Its answers are personalized
with your progress data, such as the words you struggle with. Conversations are kept and resume after a
restart; the model (Opus / Sonnet / Haiku) is selectable.

Requirement: Claude Code installed and signed in (run `claude` once in a terminal). Every other feature works
without it.

## Your data

Everything is stored in `%APPDATA%\EMGEnglish\emg.db` (SQLite): words, per-word progress, settings, daily
stats, answer history, decks and tense scores. Backups go to `backups\` in the same folder and errors are
logged to `error.log`. Deleting or updating the `.exe` does not touch your progress.

## Running from source

Requires [Python 3.10+](https://www.python.org/downloads/).

```powershell
git clone https://github.com/sezerD8/emg-english.git
cd emg-english
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Building the .exe

```powershell
pip install pyinstaller
pyinstaller emg-english.spec      # → dist\EMG-English.exe
```

Pushing a tag such as `v1.2.0` (`git tag v1.2.0 && git push origin v1.2.0`) makes GitHub Actions build the
`.exe` and attach it to a release (`.github/workflows/release.yml`). If the icon design changes, regenerate
`assets/emg.ico` with `python tools/make_icon.py` (requires Pillow).

## Word list format

Built-in entries live in `app/data/words/*.txt`, one per line:

```
english|pos|turkish|ipa|example|example_turkish
```

The last two fields are optional and line order is frequency order. A `#! level=B1` line sets the level for
the whole file. Phrase files are `phrases_*.txt` with these type codes: `phr` phrasal verb, `pat` pattern,
`expr` ready-made phrase, `idiom` idiom, `prov` proverb.

When the list changes, bump `config.DATA_VERSION`; on startup the database is synced with the list (built-in
entries removed from the list are deleted after an automatic backup). Turkish pronunciations are generated
from IPA and can be edited per word.

CSV import format (header optional): `english;turkish;phonetic;pos;example;example_tr`

## Project structure

```
main.py                 entry point (single instance, tray, hotkeys)
app/database.py         SQLite schema, data access, spaced repetition
app/overlay.py          desktop widget
app/widget_render.py    widget drawing (shared by widget and preview)
app/pronunciation.py    IPA → Turkish pronunciation
app/hotkeys.py          global hotkeys (RegisterHotKey)
app/winutil.py          Win32: topmost, fullscreen detection, custom frame
app/tts.py              text-to-speech (WinRT / SAPI)
app/online.py           dictionaryapi.dev + MyMemory lookups
app/ai_coach.py         AI Coach agent process and prompt
app/ui/*.py             pages and title bar
app/data/tenses.py      tense lessons and quizzes
app/data/words/*.txt    built-in word and phrase lists
app/data/words_archive/ archived A1–A2 words (not loaded)
emg-english.spec        PyInstaller build (single-file .exe)
assets/emg.ico          app icon (generated by tools/make_icon.py)
.github/workflows/      builds the .exe and publishes releases on tags
```

## Contributing

Bug reports, suggestions and pull requests are welcome. Fixes to translations, IPA or example sentences are
especially valuable: edit `app/data/words/*.txt` and bump `config.DATA_VERSION`. For larger changes, please
open an issue first.

## License

[MIT](LICENSE)
