"""Finding a website's icon (favicon).

Looks for the icon the page itself points to, then falls back to /favicon.ico.
Talks to the website directly and to nobody else.

Note for the planned web app: fetching addresses typed in by users from a
server needs protection against requests to internal addresses (SSRF).
This is fine on the user's own PC, but not on a server as it is.
"""

import http.client
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .downloader import USER_AGENT
from .icons import IconError, to_icon_png
from .urls import normalize_url

MAX_PAGE_BYTES = 512 * 1024
MAX_ICON_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 3  # icons tried from the page, before the /favicon.ico fallback


def _get(url: str, limit: int, timeout: float) -> tuple[str, bytes] | None:
    """Fetch up to `limit` bytes of an http(s) address. None on any problem."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
            final_url = response.geturl()
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return None
    if len(data) > limit:
        return None
    return final_url, data


class _IconLinkParser(HTMLParser):
    """Collects <link rel="icon" ...> style tags from a page."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[tuple[int, int], str]] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag != "link":
            return
        attributes = {name.lower(): (value or "") for name, value in attrs}
        rels = attributes.get("rel", "").lower().split()
        href = attributes.get("href", "").strip()
        if not href or not any(r in ("icon", "apple-touch-icon", "apple-touch-icon-precomposed") for r in rels):
            return
        # Pillow cannot read SVG, so those are skipped (the /favicon.ico fallback usually exists).
        if "svg" in attributes.get("type", "").lower() or urllib.parse.urlparse(href).path.lower().endswith(".svg"):
            return
        touch = any(r.startswith("apple-touch-icon") for r in rels)  # big and sharp: best choice
        biggest = 0
        for size in attributes.get("sizes", "").lower().split():
            width, _, height = size.partition("x")
            if width.isdigit() and height.isdigit():
                biggest = max(biggest, int(width))
        self.found.append(((0 if touch else 1, -biggest), href))


def fetch_favicon(page_url: str, timeout: float = 8) -> bytes | None:
    """Return the website's icon as a 64 x 64 PNG, or None if none was found."""
    try:
        page_url = normalize_url(page_url)
    except ValueError:
        return None

    base = page_url
    candidates: list[str] = []
    page = _get(page_url, MAX_PAGE_BYTES, timeout)
    if page is not None:
        base, body = page
        parser = _IconLinkParser()
        try:
            parser.feed(body.decode("utf-8", errors="replace"))
        except Exception:  # damaged HTML must never stop the search
            pass
        for _, href in sorted(parser.found, key=lambda item: item[0])[:MAX_CANDIDATES]:
            candidates.append(urllib.parse.urljoin(base, href))

    parts = urllib.parse.urlparse(base)
    fallback = f"{parts.scheme}://{parts.netloc}/favicon.ico"
    if fallback not in candidates:
        candidates.append(fallback)

    for url in candidates:
        got = _get(url, MAX_ICON_BYTES, timeout)
        if got is None:
            continue
        try:
            return to_icon_png(got[1])
        except IconError:
            continue
    return None
