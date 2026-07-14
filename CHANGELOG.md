# Changelog

All notable changes to `harvestweb` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- initial `harvestweb` package scaffold
- unified CLI for `review`, `scrape`, `search`, `map`, and `crawl`
- Firecrawl client extraction from the source ops repo
- multi-provider site review extraction with Firecrawl, Crawl4AI, and requests fallback paths
- pytest coverage for Firecrawl and review flows
- GitHub Actions CI and release workflows with TestPyPI and PyPI publish lanes
