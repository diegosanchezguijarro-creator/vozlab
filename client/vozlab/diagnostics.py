"""Diagnostics report — our support path without telemetry.

Builds a single text file the user can attach to a GitHub issue. Everything
private is removed: the token, dictated text, paths that identify the machine.

    report = build_report(cfg, log_path, server_health=None, client_version=…)
"""

import datetime
import os
import platform
import re
import sys

from . import VERSION
from . import platform_info

MAX_LOG_LINES = 200

# log lines that can contain dictated text
_TRANSCRIPT_PATTERNS = (
    re.compile(r"(dictation \([\d.]+s\):).*"),
    re.compile(r"(transcribed in [\d.]+s).*"),      # debug lines carry raw=/final=
    re.compile(r"(\[txt\]|\btxt\]\s*:?).*"),
)


def redact_line(line: str) -> str:
    """Strip anything that could contain the user's words."""
    for pattern in _TRANSCRIPT_PATTERNS:
        if pattern.search(line):
            return pattern.sub(lambda m: f"{m.group(1)} <redacted>", line).rstrip()
    return line


def redact_config(cfg: dict) -> dict:
    """The config without secrets or machine-identifying values."""
    hidden = {"token"}
    return {k: ("<redacted>" if k in hidden else v) for k, v in sorted(cfg.items())}


def tail_log(path: str, max_lines: int = MAX_LOG_LINES) -> list[str]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    return [redact_line(line.rstrip()) for line in lines[-max_lines:]]


def build_report(cfg: dict, log_path: str = "", server_health: dict | None = None,
                 extra: dict | None = None, server_status: dict | None = None) -> str:
    """A plain-text report with versions, environment, settings and logs."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"VozLab diagnostics — {now}",
        "=" * 60,
        "",
        f"Client version : {VERSION}",
        f"Python         : {sys.version.split()[0]}",
        f"Platform       : {platform.platform()}",
        f"Machine        : {platform.machine()}",
        f"Capabilities   : {platform_info.describe()}",
    ]
    if extra:
        for key, value in extra.items():
            lines.append(f"{key:<15}: {value}")

    server_health = server_status or server_health
    lines += ["", "-- server (from the app's last check) --"]
    if server_health:
        for key in ("version", "api", "whisper_model", "language", "cleanup",
                    "cleanup_model", "device", "uptime_s", "requests"):
            if key in server_health:
                lines.append(f"{key:<15}: {server_health[key]}")
        gpu = server_health.get("gpu") or {}
        if gpu:
            lines.append(f"{'gpu':<15}: {gpu.get('name')} "
                         f"({gpu.get('memory_used_mb')}/{gpu.get('memory_total_mb')} MB)")
        auth = server_health.get("auth") or {}
        if auth:
            lines.append(f"{'auth':<15}: {auth.get('role')}"
                         + (f" ({auth['device']})" if auth.get("device") else ""))
    else:
        lines.append("not reachable at the time of this report")

    lines += ["", "-- settings (secrets removed) --"]
    for key, value in redact_config(cfg).items():
        lines.append(f"{key:<20}: {value}")

    lines += ["", f"-- last {MAX_LOG_LINES} log lines (dictated text removed) --"]
    log_lines = tail_log(log_path)
    lines += log_lines or ["(no log file)"]

    lines += ["",
              "-- notes --",
              "This file contains no token and no dictated text.",
              "Add anything else that helps (what you said, what happened)."]
    return "\n".join(lines) + "\n"


def write_report(directory: str, cfg: dict, log_path: str = "",
                 server_health: dict | None = None, extra: dict | None = None,
                 server_status: dict | None = None) -> str:
    """Write the report into `directory`; returns the path."""
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory, f"vozlab-diagnostics-{stamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_report(cfg, log_path, server_health, extra, server_status))
    return path


ISSUE_URL = ("https://github.com/diegosg-dev/vozlab/issues/new"
             "?template=bug_report.yml")
DOCS_URL = "https://github.com/diegosg-dev/vozlab/tree/main/docs"
TROUBLESHOOTING_URL = ("https://github.com/diegosg-dev/vozlab/"
                       "blob/main/docs/TROUBLESHOOTING.md")
