"""Per-app formatting profiles.

Dictating a chat message and dictating an email want different registers, and
the app you are typing into is a good signal. A profile maps a foreground
process name to one of the server's writing styles.

The mapping is *only* a tone/formatting hint: the server's cleanup guard still
rejects anything that invents or drops words, so a wrong profile can never
corrupt a dictation.
"""

from . import foreground

#: Styles the server understands (see server/cleanup.py).
STYLES = ("default", "formal", "casual", "concise", "bullets")

#: Sensible starting point for the apps people dictate into every day.
DEFAULT_PROFILES = {
    # mail and documents: complete sentences
    "outlook.exe": "formal",
    "thunderbird.exe": "formal",
    "winword.exe": "formal",
    "olk.exe": "formal",                 # new Outlook for Windows
    # chat: keep it light
    "slack.exe": "casual",
    "discord.exe": "casual",
    "telegram.exe": "casual",
    "whatsapp.exe": "casual",
    "ms-teams.exe": "casual",
    "teams.exe": "casual",
    "signal.exe": "casual",
    # notes and code: leave the words alone
    "notepad.exe": "default",
    "code.exe": "default",
    "obsidian.exe": "default",
}

_STYLE_ALIASES = {
    "": "default",
    "normal": "default",
    "plain": "default",
    "email": "formal",
    "professional": "formal",
    "chat": "casual",
    "informal": "casual",
    "short": "concise",
    "list": "bullets",
    "bullet": "bullets",
    "bullets": "bullets",
}


def clean_app(app: str) -> str:
    """'C:\\Program Files\\Slack\\slack.exe' -> 'slack.exe'."""
    text = str(app or "").strip().lower()
    for sep in ("\\", "/"):
        text = text.rsplit(sep, 1)[-1]
    return text


def normalize_style(style: str) -> str:
    """Accept friendly words ('email') as well as the real style names."""
    text = str(style or "").strip().lower()
    if text in STYLES:
        return text
    return _STYLE_ALIASES.get(text, "default")


def resolve_style(app: str, profiles: dict | None = None, fallback: str = "default") -> str:
    """Style to use for a foreground app name.

    Exact process-name match first, then the same name without '.exe' on either
    side, so users can type either form (the UI does not care which).
    """
    mapping = {clean_app(k): normalize_style(v)
               for k, v in (profiles or {}).items() if k}
    name = clean_app(app)
    if not name:
        return normalize_style(fallback)
    if name in mapping:
        return mapping[name]

    bare = name[:-4] if name.endswith(".exe") else name
    for key, style in mapping.items():
        key_bare = key[:-4] if key.endswith(".exe") else key
        if key_bare == bare:
            return style
    return normalize_style(fallback)


def style_for_now(cfg: dict) -> str:
    """The style for whatever app has focus (used when a recording stops)."""
    if not cfg.get("per_app_profiles", True):
        return normalize_style(cfg.get("style", "default"))
    app = foreground.foreground_app()
    return resolve_style(app, cfg.get("profiles") or DEFAULT_PROFILES,
                         fallback=cfg.get("style", "default"))


def describe_rules(profiles: dict | None = None) -> list[tuple[str, str]]:
    """Sorted (app, style) pairs, for the settings UI."""
    mapping = profiles if profiles is not None else DEFAULT_PROFILES
    return sorted((clean_app(k), normalize_style(v)) for k, v in mapping.items() if k)
