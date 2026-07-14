from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from markitdown import MarkItDown

from webharvest.core.firecrawl import (
    DEFAULT_OUTPUT_ROOT,
    FirecrawlClient,
    FirecrawlError,
    write_output_bundle,
)

DEFAULT_PROVIDER_ORDER = ("firecrawl", "crawl4ai", "requests")


class SiteReviewError(RuntimeError):
    pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _title_from_html(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    return title or fallback


def _clean_html_to_markdown(html: str) -> str:
    markdowner = MarkItDown()
    return markdowner.convert_stream(
        io.BytesIO(html.encode("utf-8")),
        file_extension=".html",
    ).text_content.strip()


@dataclass(slots=True)
class SiteReviewClient:
    api_key: str | None = None
    api_url: str | None = None
    timeout_ms: int = 60_000
    provider_order: Sequence[str] = DEFAULT_PROVIDER_ORDER
    output_root: Path = DEFAULT_OUTPUT_ROOT
    firecrawl_client: FirecrawlClient | None = None
    session: requests.Session = field(default_factory=requests.Session)

    def _crawl_with_crawl4ai(self, url: str) -> dict[str, Any]:
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise SiteReviewError("crawl4ai is not installed") from exc

        async def _run() -> dict[str, Any]:
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url)
            if not getattr(result, "success", True):
                message = getattr(result, "error_message", "unknown error")
                raise SiteReviewError(f"crawl4ai crawl failed: {message}")

            markdown = getattr(result, "markdown", "")
            if hasattr(markdown, "raw_markdown"):
                markdown_text = markdown.raw_markdown or markdown.markdown_with_citations or markdown.references_markdown
            else:
                markdown_text = str(markdown or "")
            metadata = getattr(result, "metadata", {}) or {}
            html = getattr(result, "html", "") or ""
            title = str(metadata.get("title") or metadata.get("ogTitle") or _title_from_html(html, url))
            links = getattr(result, "links", {}) or {}
            return {
                "provider": "crawl4ai",
                "url": getattr(result, "redirected_url", None) or getattr(result, "url", url),
                "source_url": url,
                "title": title,
                "markdown": markdown_text.strip(),
                "html": html,
                "metadata": _json_safe(metadata),
                "links": _json_safe(links),
                "status_code": getattr(result, "status_code", None),
            }

        return asyncio.run(_run())

    def _firecrawl_review(self, url: str) -> dict[str, Any]:
        client = self.firecrawl_client or FirecrawlClient(api_key=self.api_key, api_url=self.api_url, timeout_ms=self.timeout_ms)
        response = client.scrape(url, formats=("markdown",), timeout=self.timeout_ms)
        data = response.get("data", response)
        if not isinstance(data, Mapping):
            raise SiteReviewError("Firecrawl returned an unexpected payload")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
        markdown = data.get("markdown")
        if hasattr(markdown, "raw_markdown"):
            markdown_text = markdown.raw_markdown or markdown.markdown_with_citations or markdown.references_markdown
        else:
            markdown_text = str(markdown or "")
        html = str(data.get("html") or "")
        title = str(metadata.get("title") or metadata.get("ogTitle") or _title_from_html(html, url))
        return {
            "provider": "firecrawl",
            "url": str(data.get("metadata", {}).get("sourceURL") or data.get("metadata", {}).get("url") or url),
            "source_url": url,
            "title": title,
            "markdown": markdown_text.strip(),
            "html": html,
            "metadata": _json_safe(metadata),
            "links": _json_safe(data.get("links") or {}),
            "status_code": data.get("statusCode") or response.get("statusCode"),
        }

    def _requests_review(self, url: str) -> dict[str, Any]:
        response = self.session.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
            timeout=max(self.timeout_ms / 1000.0, 0.1),
        )
        response.raise_for_status()
        html = response.text
        markdown = _clean_html_to_markdown(html)
        soup = BeautifulSoup(html, "html.parser")
        links: dict[str, list[dict[str, str]]] = {"internal": [], "external": []}
        parsed_base = urlparse(url)
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href"))
            text = anchor.get_text(" ", strip=True)
            target = urlparse(href)
            bucket = "internal" if not target.netloc or target.netloc == parsed_base.netloc else "external"
            links[bucket].append({"href": href, "text": text})
        return {
            "provider": "requests",
            "url": url,
            "source_url": url,
            "title": _title_from_html(html, url),
            "markdown": markdown,
            "html": html,
            "metadata": {"sourceURL": url},
            "links": links,
            "status_code": response.status_code,
        }

    def review(self, url: str) -> tuple[dict[str, Any], list[str]]:
        errors: list[str] = []
        providers = tuple(self.provider_order) if self.provider_order else DEFAULT_PROVIDER_ORDER
        for provider in providers:
            try:
                if provider == "crawl4ai":
                    return self._crawl_with_crawl4ai(url), errors
                if provider == "firecrawl":
                    return self._firecrawl_review(url), errors
                if provider == "requests":
                    return self._requests_review(url), errors
                raise SiteReviewError(f"Unknown provider: {provider}")
            except (SiteReviewError, FirecrawlError, requests.RequestException, ImportError, AttributeError, TypeError, ValueError) as exc:
                errors.append(f"{provider}: {exc}")
        raise SiteReviewError("All site review providers failed: " + " | ".join(errors))


def _render_links(links: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(links, Mapping):
        return []
    lines: list[str] = []
    for bucket in ("internal", "external"):
        items = links.get(bucket)
        if not isinstance(items, list) or not items:
            continue
        lines.extend(["", f"## {bucket.title()} Links ({len(items)})"])
        for item in items[:20]:
            if not isinstance(item, Mapping):
                continue
            href = item.get("href") or item.get("url") or ""
            text = item.get("text") or item.get("title") or href
            lines.append(f"- {text} ({href})")
    return lines


def render_review_markdown(review: Mapping[str, Any], *, errors: Sequence[str] | None = None, focus: str | None = None) -> str:
    lines = [
        "# Site Review",
        "",
        f"- URL: {review.get('source_url') or review.get('url')}",
        f"- Provider: {review.get('provider')}",
    ]
    if review.get("title"):
        lines.append(f"- Title: {review.get('title')}")
    if focus:
        lines.append(f"- Focus: {focus}")
    if review.get("status_code") is not None:
        lines.append(f"- Status: {review.get('status_code')}")
    if errors:
        lines.extend(["", "## Fallbacks Tried"])
        for error in errors:
            lines.append(f"- {error}")
    links = review.get("links")
    lines.extend(_render_links(links))
    markdown = str(review.get("markdown") or "").strip()
    if markdown:
        lines.extend(["", "## Extracted Markdown", "", markdown])
    else:
        lines.extend(["", "## Raw Data", "", "```json", json.dumps(_json_safe(review), indent=2, ensure_ascii=False), "```"])
    return "\n".join(lines).rstrip() + "\n"


def write_review_bundle(
    *,
    slug: str,
    markdown: str,
    payload: Mapping[str, Any],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Path]:
    return write_output_bundle(kind="reviews", slug=slug, markdown=markdown, payload=payload, output_root=output_root)
