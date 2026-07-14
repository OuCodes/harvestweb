from __future__ import annotations

import argparse
from importlib.metadata import version
from pathlib import Path
from typing import Any

from webharvest.core.firecrawl import (
    DEFAULT_OUTPUT_ROOT,
    FirecrawlClient,
    make_output_slug,
    render_crawl_markdown,
    render_map_markdown,
    render_scrape_markdown,
    render_search_markdown,
    write_output_bundle,
)
from webharvest.core.review import (
    DEFAULT_PROVIDER_ORDER,
    SiteReviewClient,
    render_review_markdown,
    write_review_bundle,
)


def _csv(values: list[str] | None) -> list[str]:
    items: list[str] = []
    for value in values or []:
        for part in value.split(","):
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)
    return items


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-key", help="Firecrawl API key. Defaults to FIRECRAWL_API_KEY.")
    parser.add_argument("--api-url", help="Firecrawl API base URL. Defaults to FIRECRAWL_API_URL or the hosted API.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for saved markdown and JSON bundles.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Website review and Firecrawl CLI.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('webharvest')}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser(
        "review",
        help="Review a website with Firecrawl first, then Crawl4AI, then requests.",
    )
    _add_common_options(review)
    review.add_argument("url", help="Website URL to review.")
    review.add_argument("--focus", help="Optional review prompt or focus area to include in the report.")
    review.add_argument(
        "--provider-order",
        default=",".join(DEFAULT_PROVIDER_ORDER),
        help="Comma-separated provider order. Default: firecrawl,crawl4ai,requests",
    )
    review.add_argument("--write", action="store_true", help="Write archive and latest files under the output root.")

    scrape = subparsers.add_parser("scrape", help="Scrape a single URL into a readable bundle.")
    _add_common_options(scrape)
    scrape.add_argument("url")
    scrape.add_argument("--format", dest="formats", action="append", default=["markdown"], help="Output format(s), comma-separated.")
    scrape.add_argument("--only-main-content", action=argparse.BooleanOptionalAction, default=True)
    scrape.add_argument("--include-tag", dest="include_tags", action="append", default=[])
    scrape.add_argument("--exclude-tag", dest="exclude_tags", action="append", default=[])
    scrape.add_argument("--max-age", type=int, default=172800000)
    scrape.add_argument("--wait-for", type=int, default=0)
    scrape.add_argument("--mobile", action="store_true")
    scrape.add_argument("--proxy", default="auto")
    scrape.add_argument("--timeout-ms", type=int, default=60000)
    scrape.add_argument("--write", action="store_true", help="Save archive and latest bundles.")

    search = subparsers.add_parser("search", help="Search the web and optionally scrape the results.")
    _add_common_options(search)
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--source", dest="sources", action="append", default=["web"], help="Search sources, comma-separated.")
    search.add_argument("--category", dest="categories", action="append", default=[])
    search.add_argument("--tbs")
    search.add_argument("--location")
    search.add_argument("--country", default="US")
    search.add_argument("--scrape-format", dest="scrape_formats", action="append", default=["markdown"], help="Scrape output formats, comma-separated.")
    search.add_argument("--only-main-content", action=argparse.BooleanOptionalAction, default=True)
    search.add_argument("--timeout-ms", type=int, default=60000)
    search.add_argument("--write", action="store_true", help="Save archive and latest bundles.")

    map_parser = subparsers.add_parser("map", help="Discover URLs on a website.")
    _add_common_options(map_parser)
    map_parser.add_argument("url")
    map_parser.add_argument("--search")
    map_parser.add_argument("--sitemap", choices=("include", "skip", "only"), default="include")
    map_parser.add_argument("--include-subdomains", action=argparse.BooleanOptionalAction, default=True)
    map_parser.add_argument("--ignore-query-parameters", action=argparse.BooleanOptionalAction, default=True)
    map_parser.add_argument("--limit", type=int, default=5000)
    map_parser.add_argument("--timeout-ms", type=int, default=60000)
    map_parser.add_argument("--write", action="store_true", help="Save archive and latest bundles.")

    crawl = subparsers.add_parser("crawl", help="Crawl a site and save the collected pages.")
    _add_common_options(crawl)
    crawl.add_argument("url")
    crawl.add_argument("--prompt")
    crawl.add_argument("--exclude-path", dest="exclude_paths", action="append", default=[])
    crawl.add_argument("--include-path", dest="include_paths", action="append", default=[])
    crawl.add_argument("--max-discovery-depth", type=int)
    crawl.add_argument("--sitemap", choices=("include", "skip"), default="include")
    crawl.add_argument("--ignore-query-parameters", action=argparse.BooleanOptionalAction, default=False)
    crawl.add_argument("--limit", type=int, default=100)
    crawl.add_argument("--crawl-entire-domain", action="store_true")
    crawl.add_argument("--allow-external-links", action="store_true")
    crawl.add_argument("--allow-subdomains", action="store_true")
    crawl.add_argument("--delay", type=int)
    crawl.add_argument("--max-concurrency", type=int)
    crawl.add_argument("--scrape-format", dest="scrape_formats", action="append", default=["markdown"], help="Scrape output formats, comma-separated.")
    crawl.add_argument("--only-main-content", action=argparse.BooleanOptionalAction, default=True)
    crawl.add_argument("--no-wait", dest="wait", action="store_false", help="Return the crawl job id without waiting for completion.")
    crawl.set_defaults(wait=True)
    crawl.add_argument("--timeout-ms", type=int, default=60000)
    crawl.add_argument("--write", action="store_true", help="Save archive and latest bundles.")

    return parser


def _client_for_args(args: argparse.Namespace) -> FirecrawlClient:
    return FirecrawlClient(api_key=args.api_key, api_url=args.api_url, timeout_ms=getattr(args, "timeout_ms", 60000))


def _render_and_maybe_write(
    *,
    kind: str,
    slug: str,
    markdown: str,
    payload: dict[str, Any],
    output_root: Path,
    should_write: bool,
) -> None:
    print(markdown, end="")
    if not should_write:
        return

    paths = write_output_bundle(kind=kind, slug=slug, markdown=markdown, payload=payload, output_root=output_root)
    print(f"\nSaved: {paths['archive_md']}")
    print(f"Saved: {paths['archive_json']}")


def _run_review(args: argparse.Namespace) -> int:
    provider_order = tuple(part.strip() for part in args.provider_order.split(",") if part.strip())
    client = SiteReviewClient(
        api_key=args.api_key,
        api_url=args.api_url,
        provider_order=provider_order,
        output_root=args.output_root,
    )
    review, errors = client.review(args.url)
    markdown = render_review_markdown(review, errors=errors, focus=args.focus)
    print(markdown, end="")
    if not args.write:
        return 0

    paths = write_review_bundle(
        slug=make_output_slug(args.url),
        markdown=markdown,
        payload={
            "review": review,
            "errors": errors,
            "provider_order": list(provider_order),
            "focus": args.focus,
        },
        output_root=args.output_root,
    )
    print(f"\nSaved: {paths['archive_md']}")
    print(f"Saved: {paths['archive_json']}")
    return 0


def _run_scrape(args: argparse.Namespace) -> int:
    client = _client_for_args(args)
    result = client.scrape(
        args.url,
        formats=_csv(args.formats),
        only_main_content=args.only_main_content,
        include_tags=args.include_tags,
        exclude_tags=args.exclude_tags,
        max_age=args.max_age,
        wait_for=args.wait_for,
        mobile=args.mobile,
        proxy=args.proxy,
        timeout=args.timeout_ms,
    )
    markdown = render_scrape_markdown(args.url, result)
    _render_and_maybe_write(
        kind="scrapes",
        slug=make_output_slug(args.url),
        markdown=markdown,
        payload=result,
        output_root=args.output_root,
        should_write=args.write,
    )
    return 0


def _run_search(args: argparse.Namespace) -> int:
    client = _client_for_args(args)
    result = client.search(
        args.query,
        limit=args.limit,
        sources=_csv(args.sources),
        categories=_csv(args.categories),
        tbs=args.tbs,
        location=args.location,
        country=args.country,
        timeout=args.timeout_ms,
        scrape_formats=_csv(args.scrape_formats),
        only_main_content=args.only_main_content,
    )
    markdown = render_search_markdown(args.query, result)
    _render_and_maybe_write(
        kind="searches",
        slug=make_output_slug(args.query),
        markdown=markdown,
        payload=result,
        output_root=args.output_root,
        should_write=args.write,
    )
    return 0


def _run_map(args: argparse.Namespace) -> int:
    client = _client_for_args(args)
    result = client.map(
        args.url,
        search=args.search,
        sitemap=args.sitemap,
        include_subdomains=args.include_subdomains,
        ignore_query_parameters=args.ignore_query_parameters,
        limit=args.limit,
        timeout=args.timeout_ms,
    )
    markdown = render_map_markdown(args.url, result)
    _render_and_maybe_write(
        kind="maps",
        slug=make_output_slug(args.url),
        markdown=markdown,
        payload=result,
        output_root=args.output_root,
        should_write=args.write,
    )
    return 0


def _run_crawl(args: argparse.Namespace) -> int:
    client = _client_for_args(args)
    result = client.crawl(
        args.url,
        prompt=args.prompt,
        exclude_paths=args.exclude_paths,
        include_paths=args.include_paths,
        max_discovery_depth=args.max_discovery_depth,
        sitemap=args.sitemap,
        ignore_query_parameters=args.ignore_query_parameters,
        limit=args.limit,
        crawl_entire_domain=args.crawl_entire_domain,
        allow_external_links=args.allow_external_links,
        allow_subdomains=args.allow_subdomains,
        delay=args.delay,
        max_concurrency=args.max_concurrency,
        scrape_options={
            "formats": _csv(args.scrape_formats),
            "onlyMainContent": args.only_main_content,
        },
        wait=args.wait,
    )
    markdown = render_crawl_markdown(args.url, result)
    _render_and_maybe_write(
        kind="crawls",
        slug=make_output_slug(args.url),
        markdown=markdown,
        payload=result,
        output_root=args.output_root,
        should_write=args.write,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "review":
        return _run_review(args)
    if args.command == "scrape":
        return _run_scrape(args)
    if args.command == "search":
        return _run_search(args)
    if args.command == "map":
        return _run_map(args)
    if args.command == "crawl":
        return _run_crawl(args)

    raise SystemExit(f"Unknown command: {args.command}")
