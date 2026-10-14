"""Scribe — local voice dictation client."""

# APP_NAME / APP_ID are *stable identifiers*: the config folder, the Windows
# startup value, the DPAPI entropy and the log file all derive from APP_NAME, so
# renaming the product must never move a user's settings or make their token
# undecryptable. DISPLAY_NAME is the only thing the user sees.
APP_NAME = "VozLab"
DISPLAY_NAME = "Scribe"
APP_ID = "vozlab"
VERSION = "1.5.0"
__all__ = ["APP_NAME", "DISPLAY_NAME", "APP_ID", "VERSION"]
