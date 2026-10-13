"""Translation files must stay in step and must never break the UI."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vozlab import i18n  # noqa: E402

LOCALES = i18n.LOCALES_DIR


def _load(lang: str) -> dict:
    with open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


def test_english_and_spanish_ship_with_the_app():
    assert i18n.available()[:2] == ["en", "es"]


def test_every_language_has_exactly_the_same_keys():
    english = set(_load("en"))
    for lang in i18n.available():
        missing = english - set(_load(lang))
        extra = set(_load(lang)) - english
        assert not missing, f"{lang}.json is missing {sorted(missing)}"
        assert not extra, f"{lang}.json has unknown keys {sorted(extra)}"


def test_placeholders_match_across_languages():
    """A translation that drops {model} would print a half-finished sentence."""
    import re

    def placeholders(text: str) -> set:
        return set(re.findall(r"\{(\w+)\}", text))

    english = _load("en")
    for lang in i18n.available():
        table = _load(lang)
        for key, value in english.items():
            assert placeholders(value) == placeholders(table[key]), \
                f"{lang}:{key} placeholders differ from English"


def test_unknown_keys_return_the_key_itself():
    tr = i18n.Translator("en")
    assert tr("nope_not_here") == "nope_not_here"


def test_unknown_language_falls_back_to_english():
    tr = i18n.Translator("klingon")
    assert tr.language == "en"
    assert tr("state_listening") == "Listening…"


def test_missing_translation_falls_back_to_english(monkeypatch):
    monkeypatch.setitem(i18n.STRINGS, "xx", {})
    tr = i18n.Translator("xx")
    assert tr("state_listening") == i18n.STRINGS["en"]["state_listening"]


def test_broken_placeholder_does_not_crash(monkeypatch):
    monkeypatch.setitem(i18n.STRINGS["es"], "broken_key", "Hola {missing}")
    tr = i18n.Translator("es")
    assert tr("broken_key") == "Hola {missing}"      # returned literally, no raise


def test_no_translation_is_left_empty():
    for lang in i18n.available():
        empty = [k for k, v in _load(lang).items() if not str(v).strip()]
        assert not empty, f"{lang}.json has empty values: {empty}"
