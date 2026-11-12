"""Web addresses typed by the user."""

from urllib.parse import urlparse


def normalize_url(text: str) -> str:
    """Return a clean http(s) address, adding https:// when it is missing.

    Raises ValueError with a readable message when it cannot be a web address.
    Only http and https are accepted, so a saved entry can never point at a
    local file or run a script when it is opened.
    """
    text = text.strip()
    if not text:
        raise ValueError("A website needs a web address.")
    if any(character.isspace() for character in text):
        raise ValueError("A web address cannot contain spaces.")
    if "://" not in text:
        text = "https://" + text

    parts = urlparse(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Enter a web address that starts with http:// or https://")
    try:
        parts.port  # raises ValueError for something like https://example.com:abc
    except ValueError:
        raise ValueError("That web address has an invalid port number.") from None
    return text
