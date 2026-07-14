# harvestweb

`harvestweb` is a small CLI and Python package for website review work.

It gives you one installable tool that can:

- review a site with provider fallbacks
- call Firecrawl directly for `scrape`, `search`, `map`, and `crawl`
- save markdown + JSON bundles under a repo-local `data/harvestweb/` directory

This package is meant to be reusable across client ops repos without dragging along brand-specific code or repo-specific state.

## Install

```bash
pip install harvestweb
```

Optional Crawl4AI fallback support:

```bash
pip install "harvestweb[crawl4ai]"
```

For local development:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[dev]"
```

## Quick start

Hosted Firecrawl requires `FIRECRAWL_API_KEY`:

```bash
export FIRECRAWL_API_KEY=fc-your-key
harvestweb review https://example.com --write
harvestweb scrape https://example.com --write
harvestweb map https://example.com --write
harvestweb crawl https://example.com --write
```

## Commands

### Review a site with fallbacks

Default provider order:

1. `firecrawl`
2. `crawl4ai`
3. `requests`

```bash
harvestweb review https://example.com --write
harvestweb review https://example.com --focus "homepage messaging" --write
harvestweb review https://example.com --provider-order firecrawl,requests --write
```

### Firecrawl commands

```bash
harvestweb scrape https://example.com --write
harvestweb search "best electrolyte drink" --limit 5 --write
harvestweb map https://example.com --write
harvestweb crawl https://example.com --limit 50 --write
```

## Output

By default, bundles are written under:

```text
data/harvestweb/
```

Subfolders are grouped by kind:

- `reviews/`
- `scrapes/`
- `searches/`
- `maps/`
- `crawls/`

Override the root with:

- `--output-root ...` on the CLI
- or `HARVESTWEB_OUTPUT_ROOT=/custom/path`

## Why this package exists

This tool is designed for people who work across multiple client repositories and want one clean, pip-installable website review utility instead of copying scripts between ops repos.

## Development

Run tests:

```bash
./.venv/bin/python -m pytest
```

Build distributions:

```bash
./.venv/bin/python -m build
```

## Release docs

- changelog: [`CHANGELOG.md`](./CHANGELOG.md)
- release checklist: [`RELEASE_CHECKLIST.md`](./RELEASE_CHECKLIST.md)
