from __future__ import annotations

import json
from pathlib import Path

from webharvest.core.firecrawl import (
    FirecrawlClient,
    render_crawl_markdown,
    render_scrape_markdown,
    write_output_bundle,
)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, url: str, json=None, headers=None, timeout=None):  # noqa: A002
        self.calls.append((method, url, json))
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)


def test_scrape_posts_expected_payload_and_renders_markdown() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                {
                    "success": True,
                    "data": {
                        "markdown": "# Example\n\nContent",
                        "metadata": {"title": "Example", "sourceURL": "https://example.com"},
                    },
                }
            )
        ]
    )
    client = FirecrawlClient(api_key="fc-test", session=session)

    result = client.scrape(
        "https://example.com",
        formats=("markdown", "html"),
        include_tags=("main",),
        exclude_tags=("nav",),
        wait_for=1000,
        mobile=True,
    )

    assert result["data"]["metadata"]["title"] == "Example"
    method, url, payload = session.calls[0]
    assert method == "POST"
    assert url == "https://api.firecrawl.dev/v2/scrape"
    assert payload["url"] == "https://example.com"
    assert payload["formats"] == ["markdown", "html"]
    assert payload["includeTags"] == ["main"]
    assert payload["excludeTags"] == ["nav"]
    assert payload["waitFor"] == 1000
    assert payload["mobile"] is True

    markdown = render_scrape_markdown("https://example.com", result)
    assert "Firecrawl Scrape" in markdown
    assert "Example" in markdown
    assert "Content" in markdown


def test_crawl_polls_until_completed_and_collects_pages() -> None:
    session = _FakeSession(
        [
            _FakeResponse({"success": True, "id": "crawl-123", "url": "https://example.com"}),
            _FakeResponse({"status": "scraping", "data": [], "next": None}),
            _FakeResponse(
                {
                    "status": "completed",
                    "total": 2,
                    "completed": 2,
                    "creditsUsed": 2,
                    "data": [
                        {"metadata": {"title": "Home", "sourceURL": "https://example.com"}},
                    ],
                    "next": "https://api.firecrawl.dev/v2/crawl/crawl-123?page=2",
                }
            ),
            _FakeResponse(
                {
                    "status": "completed",
                    "data": [
                        {"metadata": {"title": "Docs", "sourceURL": "https://example.com/docs"}},
                    ],
                    "next": None,
                }
            ),
        ]
    )
    client = FirecrawlClient(api_key="fc-test", session=session, timeout_ms=10_000)

    result = client.crawl("https://example.com", wait=True, poll_interval=0.0, max_wait_seconds=5.0)

    assert result["status"] == "completed"
    assert result["started"]["id"] == "crawl-123"
    assert len(result["data"]) == 2
    assert result["data"][0]["metadata"]["title"] == "Home"
    assert result["data"][1]["metadata"]["title"] == "Docs"

    markdown = render_crawl_markdown("https://example.com", result)
    assert "Firecrawl Crawl" in markdown
    assert "Home" in markdown
    assert "Docs" in markdown


def test_write_output_bundle_writes_latest_and_archive(tmp_path: Path) -> None:
    payload = {"success": True, "data": {"markdown": "# Example"}}
    markdown = "# Firecrawl Scrape\n\n- URL: https://example.com\n"

    paths = write_output_bundle(
        kind="scrapes",
        slug="example-com",
        markdown=markdown,
        payload=payload,
        output_root=tmp_path,
    )

    assert paths["latest_md"].read_text(encoding="utf-8") == markdown
    assert paths["latest_json"].exists()
    assert paths["archive_md"].exists()
    assert paths["archive_json"].exists()

