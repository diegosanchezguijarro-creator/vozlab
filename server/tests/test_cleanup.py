"""Tests for the cleanup prompt and its safety guard (no network, no Whisper).

    pip install pytest
    pytest tests -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup import (  # noqa: E402
    DEFAULT_CLEANUP_PROMPT,
    cleanup_ok,
    strip_decoration,
    words,
)


# ------------------------------------------------------- the reported bug ----
def test_answering_a_question_is_rejected():
    """Real regression: llama3.1:8b answered 'are you responding to me?'."""
    ok, reason = cleanup_ok("Are you responding to me?", "Yes, I am responding to you.")
    assert not ok
    assert "invented" in reason


def test_answering_spanish_question_is_rejected():
    ok, _ = cleanup_ok("¿Me estás respondiendo?", "Sí, te estoy respondiendo.")
    assert not ok


def test_off_script_explanations_are_rejected():
    ok, reason = cleanup_ok("hello world",
                            "Formatted text: Hello world.")
    assert not ok


def test_grossly_longer_output_is_rejected():
    ok, reason = cleanup_ok("send the report",
                            "Sure, here is a much longer paraphrase of what you asked for, "
                            "rephrased in my own words and expanded considerably.")
    assert not ok


# ------------------------------------------------------- legitimate edits ----
@pytest.mark.parametrize("raw,cleaned", [
    ("are you responding to me", "Are you responding to me?"),
    ("um can you send me the the report by friday", "Can you send me the report by Friday?"),
    ("so I was thinking uh we should launch on monday you know",
     "So I was thinking we should launch on Monday."),
    ("hello, this is a test of the local dictation system. it should transcribe this clearly.",
     "Hello, this is a test of the local dictation system. It should transcribe this clearly."),
    ("oye necesito que prepares el informe del proyecto para el martes. um y tambien recuerdame llamar al cliente.",
     "Oye, necesito que prepares el informe del proyecto para el martes. Y también, recuérdame llamar al cliente."),
    ("the meeting is moved to monday", "The meeting is moved to Monday."),
])
def test_legitimate_cleanups_pass(raw, cleaned):
    ok, reason = cleanup_ok(raw, cleaned)
    assert ok, f"rejected a good cleanup: {reason}"


def test_short_rewrites_tolerated():
    # one misheard word corrected: still the same sentence
    ok, _ = cleanup_ok("prepare the report for tuesday", "Prepare the report for Tuesday.")
    assert ok


def test_empty_output_rejected():
    ok, _ = cleanup_ok("some words here", "")
    assert not ok


# --------------------------------------------------------------- helpers -----
def test_words_normalisation():
    assert words("Hello, Wörld! 42 times") == ["hello", "world", "times"]


def test_accents_are_not_treated_as_invented_words():
    """Regression: restoring accents in Spanish must not trip the guard."""
    ok, reason = cleanup_ok("hola que tal como estas", "Hola, qué tal, ¿cómo estás?")
    assert ok, f"accent restoration wrongly rejected: {reason}"

    ok, reason = cleanup_ok("necesito que prepares el informe para el martes",
                            "Necesito que prepares el informe para el martes.")
    assert ok, reason


def test_numbers_to_digits_are_tolerated():
    ok, _ = cleanup_ok("the meeting is at three pm", "The meeting is at 3 pm.")
    assert ok


def test_strip_decoration():
    assert strip_decoration('"Hello there."') == "Hello there."
    assert strip_decoration("```Hello```") == "Hello"
    assert strip_decoration("Plain text") == "Plain text"


def test_prompt_forbids_conversation():
    prompt = DEFAULT_CLEANUP_PROMPT.lower()
    assert "not a chat" in prompt
    assert "never answer" in prompt
    # the prompt must include a question example, since that is the failure mode
    assert "are you responding to me" in prompt
    assert "never translate" in prompt
