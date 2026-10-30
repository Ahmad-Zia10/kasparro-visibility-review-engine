from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"fbclid", "gclid", "ref", "srsltid"}


def normalise_url(url: str) -> str:
    """Reduce a URL to the form used for counting: same page, same string."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.startswith("utm_") and key not in TRACKING_PARAMS
    ]
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), urlencode(query), ""))


def unique_urls(urls: list[str]) -> list[str]:
    """Normalised URLs of one response, each counted once, in first-seen order."""
    return list(dict.fromkeys(normalise_url(url) for url in urls))


def is_kasparro_url(url: str) -> bool:
    host = urlsplit(normalise_url(url)).hostname or ""
    return host == "kasparro.com" or host.endswith(".kasparro.com")
