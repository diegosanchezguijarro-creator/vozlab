"""Update checks against GitHub releases.

Disabled by default: VozLab ships zero telemetry, so the only time it talks to
the internet is when you turn this on in Settings or press "Check now".
(`deploy.ps1` / `update.ps1` also contact GitHub, but only when you run them.)
"""

import re

import requests

from . import VERSION

DEFAULT_REPO = "diegosanchezguijarro-creator/vozlab"
API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
INSTALLER_ASSET = "VozLab-{version}-src.zip"
USER_AGENT = f"VozLab/{VERSION}"


class UpdateError(Exception):
    pass


def parse_version(text: str) -> tuple[int, int, int]:
    """'v1.2.3' / '1.2.3' / '1.2.3-rc1' -> (1, 2, 3). Unparsable -> (0, 0, 0)."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(text) or "")
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def is_newer(candidate: str, current: str) -> bool:
    """True when `candidate` is a strictly newer version than `current`."""
    return parse_version(candidate) > parse_version(current)


def version_mismatch(server_version: str, client_version: str = VERSION) -> bool:
    """True when client/server differ in major.minor (patch drift is fine)."""
    s, c = parse_version(server_version), parse_version(client_version)
    return (s[0], s[1]) != (c[0], c[1])


def latest_release(repo: str = DEFAULT_REPO, timeout: float = 8.0) -> dict:
    """Ask GitHub for the newest release. Returns tag/version/url/notes."""
    try:
        r = requests.get(API_LATEST.format(repo=repo),
                         headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
                         timeout=timeout)
    except requests.RequestException as e:
        raise UpdateError(str(e)) from e
    if r.status_code == 404:
        raise UpdateError("no releases published yet")
    if r.status_code != 200:
        raise UpdateError(f"GitHub answered {r.status_code}")
    data = r.json()
    tag = data.get("tag_name") or ""
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "url": data.get("html_url") or "",
        "notes": (data.get("body") or "").strip(),
    }


def check(repo: str = DEFAULT_REPO, current: str = VERSION) -> dict | None:
    """Return release info when a newer version exists, else None."""
    release = latest_release(repo)
    if is_newer(release["version"], current):
        return release
    return None
