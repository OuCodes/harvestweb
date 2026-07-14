from __future__ import annotations

import sys
import types
from pathlib import Path

from harvestweb.core.review import SiteReviewClient, SiteReviewError, render_review_markdown, write_review_bundle


class _FakeCrawlMarkdown:
    raw_markdown = "# Crawl4AI\n\nBody"
    markdown_with_citations = ""
    references_markdown = ""


class _FakeCrawlResult:
    success = True
    url = "https://example.com"
    redirected_url = "https://example.com/landing"
    markdown = _FakeCrawlMarkdown()
    metadata = {"title": "Crawl4AI Title"}
    html = "<html><head><title>Crawl4AI Title</title></head><body><a href='/docs'>Docs</a></body></html>"
    links = {"internal": [{"href": "/docs", "text": "Docs"}]}
    status_code = 200


class _FakeAsyncWebCrawler:
    async def __aenter__(self) -> "_FakeAsyncWebCrawler":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def arun(self, url: str) -> _FakeCrawlResult:
        assert url == "https://example.com"
        return _FakeCrawlResult()


class _FakeFirecrawlClient:
    def scrape(self, url: str, *, formats, timeout):  # noqa: ANN001
        assert url == "https://example.com"
        assert formats == ("markdown",)
        assert timeout == 60_000
        return {
            "data": {
                "markdown": "# Firecrawl\n\nBody",
                "metadata": {"title": "Firecrawl Title", "sourceURL": url},
                "links": {"internal": [{"href": "/docs", "text": "Docs"}]},
                "statusCode": 200,
            }
        }


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def get(self, url: str, headers=None, timeout=None):  # noqa: ANN001
        assert url == "https://example.com"
        return _FakeResponse(
            "<html><head><title>Requests Title</title></head><body><a href='/about'>About</a></body></html>"
        )


def test_review_prefers_firecrawl_when_available(monkeypatch) -> None:
    crawl4ai_module = types.ModuleType("crawl4ai")
    crawl4ai_module.AsyncWebCrawler = _FakeAsyncWebCrawler
    monkeypatch.setitem(sys.modules, "crawl4ai", crawl4ai_module)

    def fail_crawl(self, url: str) -> dict[str, str]:  # noqa: ARG001
        raise SiteReviewError("crawl4ai should not run when firecrawl succeeds")

    monkeypatch.setattr(SiteReviewClient, "_crawl_with_crawl4ai", fail_crawl)
    client = SiteReviewClient(firecrawl_client=_FakeFirecrawlClient())

    review, errors = client.review("https://example.com")

    assert review["provider"] == "firecrawl"
    assert review["title"] == "Firecrawl Title"
    assert review["markdown"] == "# Firecrawl\n\nBody"
    assert review["links"]["internal"][0]["href"] == "/docs"
    assert errors == []


def test_review_falls_back_to_crawl4ai_when_firecrawl_fails(monkeypatch) -> None:
    crawl4ai_module = types.ModuleType("crawl4ai")
    crawl4ai_module.AsyncWebCrawler = _FakeAsyncWebCrawler
    monkeypatch.setitem(sys.modules, "crawl4ai", crawl4ai_module)

    def fail_firecrawl(self, url: str) -> dict[str, str]:  # noqa: ARG001
        raise SiteReviewError("firecrawl unavailable")

    monkeypatch.setattr(SiteReviewClient, "_firecrawl_review", fail_firecrawl)

    client = SiteReviewClient()

    review, errors = client.review("https://example.com")

    assert review["provider"] == "crawl4ai"
    assert review["title"] == "Crawl4AI Title"
    assert review["markdown"] == "# Crawl4AI\n\nBody"
    assert errors == ["firecrawl: firecrawl unavailable"]


def test_review_falls_back_to_requests_when_prior_providers_fail(monkeypatch) -> None:
    def fail_firecrawl(self, url: str) -> dict[str, str]:  # noqa: ARG001
        raise SiteReviewError("firecrawl unavailable")

    def fail_crawl(self, url: str) -> dict[str, str]:  # noqa: ARG001
        raise SiteReviewError("crawl4ai unavailable")

    monkeypatch.setattr(SiteReviewClient, "_firecrawl_review", fail_firecrawl)
    monkeypatch.setattr(SiteReviewClient, "_crawl_with_crawl4ai", fail_crawl)

    client = SiteReviewClient(session=_FakeSession())

    review, errors = client.review("https://example.com")

    assert review["provider"] == "requests"
    assert review["title"] == "Requests Title"
    assert review["links"]["internal"][0]["href"] == "/about"
    assert errors == ["firecrawl: firecrawl unavailable", "crawl4ai: crawl4ai unavailable"]

    markdown = render_review_markdown(review, errors=errors, focus="Homepage")
    assert "Site Review" in markdown
    assert "Fallbacks Tried" in markdown
    assert "Homepage" in markdown


def test_write_review_bundle_writes_latest_and_archive(tmp_path: Path) -> None:
    payload = {
        "review": {"provider": "requests", "url": "https://example.com"},
        "errors": [],
        "provider_order": ["firecrawl", "crawl4ai", "requests"],
        "focus": "Homepage",
    }
    markdown = "# Site Review\n\n- URL: https://example.com\n"

    paths = write_review_bundle(
        slug="example-com",
        markdown=markdown,
        payload=payload,
        output_root=tmp_path,
    )

    assert paths["latest_md"].read_text(encoding="utf-8") == markdown
    assert paths["latest_json"].exists()
    assert paths["archive_md"].exists()
    assert paths["archive_json"].exists()
