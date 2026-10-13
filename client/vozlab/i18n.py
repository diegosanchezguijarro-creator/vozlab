"""Small i18n layer. Translations live in `vozlab/locales/<lang>.json`.

Adding a language = copy `en.json`, translate the values, open a pull request
(see CONTRIBUTING). Keys missing from a translation fall back to English.
"""

import json
import locale
import os

LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
FALLBACK = "en"


def _load() -> dict:
    strings: dict[str, dict[str, str]] = {}
    try:
        names = sorted(os.listdir(LOCALES_DIR))
    except OSError:
        return {FALLBACK: {}}
    for name in names:
        if not name.endswith(".json"):
            continue
        lang = name[:-5]
        try:
            with open(os.path.join(LOCALES_DIR, name), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                strings[lang] = {k: str(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError):
            continue
    if FALLBACK not in strings:
        strings[FALLBACK] = {}
    return strings


STRINGS = _load()


def available() -> list[str]:
    """Language codes that ship with the app (English first)."""
    codes = sorted(STRINGS)
    return [FALLBACK] + [c for c in codes if c != FALLBACK]


def detect_language() -> str:
    """Return 'es' or 'en' from the OS locale."""
    try:
        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""
    except Exception:
        loc = ""
    return "es" if str(loc).lower().startswith("es") else "en"


def resolve(ui_language: str) -> str:
    if ui_language in (None, "", "auto"):
        lang = detect_language()
    else:
        lang = str(ui_language).lower()
    return lang if lang in STRINGS else FALLBACK


class Translator:
    def __init__(self, ui_language: str = "auto"):
        self.language = resolve(ui_language)

    def set_language(self, ui_language: str) -> None:
        self.language = resolve(ui_language)

    def __call__(self, key: str, **kwargs) -> str:
        text = STRINGS.get(self.language, {}).get(key) \
            or STRINGS[FALLBACK].get(key) or key
        try:
            return text.format(**kwargs) if kwargs else text
        except (KeyError, IndexError, ValueError):
            # a translation with a broken placeholder must never crash the app
            return text
