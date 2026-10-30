import pytest

from app.citations import is_kasparro_url, normalise_url, unique_urls


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://WWW.Example.com/guide/?utm_source=chatgpt.com#top", "https://example.com/guide"),
        ("https://example.com/guide?id=7&utm_medium=x", "https://example.com/guide?id=7"),
        ("http://example.com/", "http://example.com"),
    ],
)
def test_normalise_url(url: str, expected: str) -> None:
    assert normalise_url(url) == expected


def test_citation_dedup_rule() -> None:
    urls = [
        "https://www.example.com/guide?utm_source=chatgpt.com",
        "https://example.com/guide/",
        "https://other.org/page",
    ]

    assert unique_urls(urls) == ["https://example.com/guide", "https://other.org/page"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://kasparro.com/", True),
        ("https://www.kasparro.com/audit", True),
        ("https://blog.kasparro.com/post", True),
        ("https://notkasparro.com/", False),
        ("https://example.com/kasparro-review", False),
    ],
)
def test_kasparro_citation_is_detected(url: str, expected: bool) -> None:
    assert is_kasparro_url(url) is expected
