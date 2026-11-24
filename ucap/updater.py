"""Update check against GitHub Releases. Only tells the user; it never downloads or runs anything."""
from __future__ import annotations

import json
import re
import urllib.request

# "owner/repo" whose Releases hold Ucap.exe. Empty = update check off.
UPDATE_REPO = "albertsetiawan1994/ucap"
TIMEOUT_S = 10


def parse_version(tag: str) -> tuple[int, ...]:
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2, 0); anything unreadable -> ()."""
    m = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", tag or "")
    return tuple(int(x or 0) for x in m.groups()) if m else ()


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "Ucap-update-check"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - fixed https URL
        return json.load(r)


def check(current: str, repo: str = UPDATE_REPO, fetch=_fetch) -> dict | None:
    """{'version', 'url'} when the latest non-draft release is newer than `current`, else None.
    Network and parse errors return None: a failed check must never bother the user."""
    if not repo:
        return None
    try:
        data = fetch(f"https://api.github.com/repos/{repo}/releases/latest")
        latest = parse_version(data.get("tag_name", ""))
        url = data.get("html_url", "")
    except Exception:  # noqa: BLE001
        return None
    if latest and latest > parse_version(current) and url.startswith(f"https://github.com/{repo}/"):
        return {"version": ".".join(map(str, latest)), "url": url}
    return None
