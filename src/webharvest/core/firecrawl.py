from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import requests

FIRECRAWL_API_BASE = "https://api.firecrawl.dev"
FIRECRAWL_API_VERSION = "v2"
DEFAULT_OUTPUT_ROOT = Path(os.getenv("WEBHARVEST_OUTPUT_ROOT", "data/webharvest"))


class FirecrawlError(RuntimeError):
    pass


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "firecrawl"


def make_output_slug(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        source = parsed.netloc + parsed.path
        if parsed.query:
            source += f"-{parsed.query}"
        return slugify(source)
    return slugify(value)


def _csv_to_list(values: Iterable[str] | None) -> list[str]:
    items: list[str] = []
    for value in values or ():
        for part in str(value).split(","):
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)
    return items


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _request_timeout(timeout_ms: int) -> float:
    return max(timeout_ms / 1000.0, 0.1)


def _default_location() -> dict[str, Any]:
    return {"country": "US", "languages": ["en-US"]}


@dataclass(slots=True)
class FirecrawlClient:
    api_key: str | None = None
    api_url: str | None = None
    timeout_ms: int = 60_000
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("FIRECRAWL_API_KEY")
        self.api_url = (self.api_url or os.getenv("FIRECRAWL_API_URL") or FIRECRAWL_API_BASE).rstrip("/")
        if self.api_url == FIRECRAWL_API_BASE and not self.api_key:
            raise FirecrawlError(
                "FIRECRAWL_API_KEY is required when using the hosted Firecrawl API"
            )

    @property
    def _base_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_url == FIRECRAWL_API_BASE:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.api_url}/{FIRECRAWL_API_VERSION}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(
            method=method,
            url=self._url(path),
            json=_json_safe(payload) if payload is not None else None,
            headers=self._base_headers,
            timeout=_request_timeout(self.timeout_ms),
        )
        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise FirecrawlError(
                f"Firecrawl returned non-JSON data from {method} {path}: {response.text[:200]}"
            ) from exc

        if response.status_code >= 400:
            message = data.get("error") if isinstance(data, Mapping) else response.text
            raise FirecrawlError(f"Firecrawl {method} {path} failed ({response.status_code}): {message}")
        if isinstance(data, Mapping) and data.get("success") is False:
            message = data.get("error") or data.get("warning") or "unknown error"
            raise FirecrawlError(f"Firecrawl {method} {path} returned success=false: {message}")
        if not isinstance(data, dict):
            return {"data": data}
        return data

    def scrape(
        self,
        url: str,
        *,
        formats: Iterable[str | Mapping[str, Any]] = ("markdown",),
        only_main_content: bool = True,
        include_tags: Iterable[str] | None = None,
        exclude_tags: Iterable[str] | None = None,
        max_age: int | None = None,
        headers: Mapping[str, str] | None = None,
        wait_for: int = 0,
        mobile: bool = False,
        skip_tls_verification: bool = True,
        timeout: int | None = None,
        parsers: Iterable[str] | None = ("pdf",),
        actions: Iterable[Mapping[str, Any]] | None = None,
        location: Mapping[str, Any] | None = None,
        remove_base64_images: bool = True,
        block_ads: bool = True,
        proxy: str = "auto",
        store_in_cache: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "formats": list(formats),
            "onlyMainContent": only_main_content,
            "waitFor": wait_for,
            "mobile": mobile,
            "skipTlsVerification": skip_tls_verification,
            "removeBase64Images": remove_base64_images,
            "blockAds": block_ads,
            "proxy": proxy,
        }
        if include_tags:
            payload["includeTags"] = _csv_to_list(include_tags)
        if exclude_tags:
            payload["excludeTags"] = _csv_to_list(exclude_tags)
        if max_age is not None:
            payload["maxAge"] = max_age
        if headers:
            payload["headers"] = dict(headers)
        if timeout is not None:
            payload["timeout"] = timeout
        if parsers is not None:
            payload["parsers"] = _csv_to_list(parsers)
        if actions:
            payload["actions"] = [dict(action) for action in actions]
        if location:
            payload["location"] = dict(location)
        if store_in_cache is not None:
            payload["storeInCache"] = store_in_cache
        return self._request("POST", "scrape", payload=payload)

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        sources: Iterable[str] = ("web",),
        categories: Iterable[str] | None = None,
        tbs: str | None = None,
        location: str | None = None,
        country: str = "US",
        timeout: int = 60_000,
        ignore_invalid_urls: bool = True,
        scrape_formats: Iterable[str | Mapping[str, Any]] | None = None,
        only_main_content: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "sources": _csv_to_list(sources),
            "country": country,
            "timeout": timeout,
            "ignoreInvalidURLs": ignore_invalid_urls,
        }
        if categories:
            payload["categories"] = _csv_to_list(categories)
        if tbs:
            payload["tbs"] = tbs
        if location:
            payload["location"] = location
        if scrape_formats:
            payload["scrapeOptions"] = {
                "formats": list(scrape_formats),
                "onlyMainContent": only_main_content,
            }
        return self._request("POST", "search", payload=payload)

    def map(
        self,
        url: str,
        *,
        search: str | None = None,
        sitemap: str = "include",
        include_subdomains: bool = True,
        ignore_query_parameters: bool = True,
        limit: int = 5_000,
        timeout: int | None = None,
        location: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "sitemap": sitemap,
            "includeSubdomains": include_subdomains,
            "ignoreQueryParameters": ignore_query_parameters,
            "limit": limit,
        }
        if search:
            payload["search"] = search
        if timeout is not None:
            payload["timeout"] = timeout
        if location:
            payload["location"] = dict(location)
        return self._request("POST", "map", payload=payload)

    def crawl(
        self,
        url: str,
        *,
        prompt: str | None = None,
        exclude_paths: Iterable[str] | None = None,
        include_paths: Iterable[str] | None = None,
        max_discovery_depth: int | None = None,
        sitemap: str = "include",
        ignore_query_parameters: bool = False,
        limit: int = 100,
        crawl_entire_domain: bool = False,
        allow_external_links: bool = False,
        allow_subdomains: bool = False,
        delay: int | None = None,
        max_concurrency: int | None = None,
        scrape_options: Mapping[str, Any] | None = None,
        zero_data_retention: bool = False,
        wait: bool = True,
        poll_interval: float = 2.0,
        max_wait_seconds: float = 300.0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "sitemap": sitemap,
            "ignoreQueryParameters": ignore_query_parameters,
            "limit": limit,
            "crawlEntireDomain": crawl_entire_domain,
            "allowExternalLinks": allow_external_links,
            "allowSubdomains": allow_subdomains,
            "zeroDataRetention": zero_data_retention,
        }
        if prompt:
            payload["prompt"] = prompt
        if exclude_paths:
            payload["excludePaths"] = _csv_to_list(exclude_paths)
        if include_paths:
            payload["includePaths"] = _csv_to_list(include_paths)
        if max_discovery_depth is not None:
            payload["maxDiscoveryDepth"] = max_discovery_depth
        if delay is not None:
            payload["delay"] = delay
        if max_concurrency is not None:
            payload["maxConcurrency"] = max_concurrency
        if scrape_options:
            payload["scrapeOptions"] = dict(scrape_options)

        started = self._request("POST", "crawl", payload=payload)
        if not wait:
            return started

        crawl_id = started.get("id")
        if not crawl_id:
            return started

        deadline = time.monotonic() + max_wait_seconds
        status_url = f"crawl/{crawl_id}"
        status_payload: dict[str, Any] = {}
        while True:
            status_payload = self._request("GET", status_url)
            status = status_payload.get("status")
            if status == "failed":
                raise FirecrawlError(
                    f"Firecrawl crawl {crawl_id} failed: {status_payload.get('error') or 'unknown error'}"
                )
            if status == "completed":
                break
            if time.monotonic() >= deadline:
                raise FirecrawlError(f"Firecrawl crawl {crawl_id} did not finish within {max_wait_seconds}s")
            time.sleep(poll_interval)

        raw_pages = status_payload.get("data")
        pages = list(raw_pages) if isinstance(raw_pages, list) else []
        next_url = status_payload.get("next")
        while next_url:
            page_payload = self._request("GET", str(next_url))
            page_data = page_payload.get("data")
            if isinstance(page_data, list):
                pages.extend(page_data)
            next_url = page_payload.get("next")

        final = dict(status_payload)
        final["started"] = started
        final["data"] = pages
        return final


def _title_from_metadata(metadata: Mapping[str, Any] | None, fallback: str) -> str:
    if not metadata:
        return fallback
    for key in ("title", "ogTitle", "siteName", "sourceURL"):
        value = metadata.get(key) if isinstance(metadata, Mapping) else None
        if value:
            return str(value)
    return fallback


def render_scrape_markdown(url: str, response: Mapping[str, Any]) -> str:
    data = response.get("data", response)
    if not isinstance(data, Mapping):
        data = {"markdown": str(data)}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
    title = _title_from_metadata(metadata, url)
    parts: list[str] = [
        "# Firecrawl Scrape",
        "",
        f"- URL: {url}",
        f"- Title: {title}",
    ]
    source_url = metadata.get("sourceURL") if isinstance(metadata, Mapping) else None
    if source_url:
        parts.append(f"- Source URL: {source_url}")
    summary = data.get("summary")
    if summary:
        parts.extend(["", "## Summary", "", str(summary).strip()])
    markdown = data.get("markdown")
    if markdown:
        parts.extend(["", "## Extracted Markdown", "", str(markdown).strip()])
    else:
        parts.extend(["", "## Raw Data", "", "```json", json.dumps(_json_safe(data), indent=2, ensure_ascii=False), "```"])
    return "\n".join(parts).rstrip() + "\n"


def render_search_markdown(query: str, response: Mapping[str, Any]) -> str:
    data = response.get("data", response)
    if not isinstance(data, Mapping):
        data = {"web": data}
    lines = [
        "# Firecrawl Search",
        "",
        f"- Query: {query}",
    ]
    for source_name, results in data.items():
        if not isinstance(results, list):
            continue
        lines.extend(["", f"## {str(source_name).title()} ({len(results)})"])
        for item in results[:25]:
            if not isinstance(item, Mapping):
                continue
            title = item.get("title") or item.get("url") or "Untitled result"
            url = item.get("url") or item.get("source_url") or ""
            description = item.get("description") or item.get("summary") or ""
            lines.append(f"- {title} ({url})")
            if description:
                lines.append(f"  - {str(description).strip()}")
    return "\n".join(lines).rstrip() + "\n"


def render_map_markdown(url: str, response: Mapping[str, Any]) -> str:
    links = response.get("links") or response.get("data") or []
    lines = [
        "# Firecrawl Map",
        "",
        f"- URL: {url}",
        f"- Links found: {len(links) if isinstance(links, list) else 0}",
        "",
        "## URLs",
    ]
    for item in (links or [])[:250]:
        if not isinstance(item, Mapping):
            continue
        title = item.get("title") or item.get("url") or "Untitled"
        link_url = item.get("url") or ""
        description = item.get("description") or ""
        lines.append(f"- {title} ({link_url})")
        if description:
            lines.append(f"  - {str(description).strip()}")
    return "\n".join(lines).rstrip() + "\n"


def render_crawl_markdown(url: str, response: Mapping[str, Any]) -> str:
    raw_pages = response.get("data") or []
    pages = raw_pages if isinstance(raw_pages, list) else []
    lines = [
        "# Firecrawl Crawl",
        "",
        f"- Start URL: {url}",
        f"- Status: {response.get('status', 'unknown')}",
        f"- Total attempted: {response.get('total', 0)}",
        f"- Completed: {response.get('completed', 0)}",
        f"- Credits used: {response.get('creditsUsed', 0)}",
        "",
        "## Pages",
    ]
    for item in (pages or [])[:100]:
        if not isinstance(item, Mapping):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        title = _title_from_metadata(metadata, item.get("url") or "Untitled page")
        page_url = metadata.get("sourceURL") if isinstance(metadata, Mapping) else item.get("url")
        description = metadata.get("description") if isinstance(metadata, Mapping) else ""
        lines.append(f"- {title} ({page_url})")
        if description:
            lines.append(f"  - {str(description).strip()}")
    if len(pages or []) > 100:
        lines.append(f"- ... {len(pages) - 100} more pages not shown")
    return "\n".join(lines).rstrip() + "\n"


def write_output_bundle(
    *,
    kind: str,
    slug: str,
    markdown: str,
    payload: Mapping[str, Any],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Path]:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = output_root / kind
    folder.mkdir(parents=True, exist_ok=True)

    archive_base = folder / f"{slug}-{timestamp}"
    md_path = archive_base.with_suffix(".md")
    json_path = archive_base.with_suffix(".json")
    latest_md = folder / "latest.md"
    latest_json = folder / "latest.json"

    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    latest_json.write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "archive_md": md_path,
        "archive_json": json_path,
        "latest_md": latest_md,
        "latest_json": latest_json,
    }
