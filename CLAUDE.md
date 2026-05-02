# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Run the server locally (stdio transport)
uv run property-mcp

# Run with HTTP transport
MCP_TRANSPORT=http uv run property-mcp

# Build distribution
uv build

# Type check
uv run mypy property_mcp/

# Deploy to Fly.io
flyctl deploy --remote-only --ha=false
```

There are no tests in this repo. The package is thin enough that manual testing against the live MCP server is the expected workflow.

## Architecture

This is a **thin FastMCP wrapper** over [`property-shared`](https://pypi.org/project/property-shared/) (`property_core`). All business logic lives in `property_core` — this package just exposes it as MCP tools.

**Single file of substance:** `property_mcp/server.py` — contains all 13 tool definitions, the `main()` entry point, and two middleware layers.

**Key patterns in server.py:**
- All tools use **lazy imports** (`from property_core import ...` inside each async function) to keep startup fast and avoid loading unused dependencies.
- Synchronous `property_core` calls are wrapped with `anyio.to_thread.run_sync(partial(...))` to avoid blocking the async event loop.
- `_result(summary, data)` builds every tool response — strips `raw`, `images`, `floorplans`, `epc_match` from both the LLM-visible text and `structured_content` to reduce context window usage. API consumers needing raw data should call upstream services directly.
- `_slim()` is the recursive field stripper used by `_result`.

**Middleware stack (order matters — added after mcp is defined):**
1. `PrometheusMiddleware` — wraps every tool call with `tool_calls_total` counter and `tool_duration_seconds` histogram, labelled by tool/transport/region.
2. `ResponseCachingMiddleware` — 5-minute TTL in-memory cache. Intentionally short: a longer TTL caused OOM on the 512MB Fly machine under burst load (unbounded cache growth).

**Transport selection** (`main()`): `MCP_TRANSPORT` env var picks `stdio` (default), `sse`, or `http`. The `stdio` path is for local MCP clients (Claude Desktop, Claude Code). The `http` path is for the Fly.io remote deployment at `https://property-shared.fly.dev/mcp`.

**Release pipeline** (`.github/workflows/release.yml`): GitHub release → `uv build` → PyPI publish (trusted publishing, no token needed) → `flyctl deploy`. Both steps are in one workflow; Fly deploy runs only if `FLY_APP_NAME` is set.

## Environment Variables

Copy `.env.example` to `.env`. Only `EPC_API_EMAIL`/`EPC_API_KEY` and `COMPANIES_HOUSE_API_KEY` are needed — all other tools use public APIs with no auth.

| Variable | Purpose |
|---|---|
| `EPC_API_EMAIL` / `EPC_API_KEY` | EPC Register API (epc.opendatacommunities.org) |
| `COMPANIES_HOUSE_API_KEY` | Companies House API (free registration) |
| `RIGHTMOVE_DELAY_SECONDS` | Rate limit between Rightmove requests (default 0.6s) |
| `MCP_TRANSPORT` | `stdio` / `sse` / `http` |
| `FASTMCP_STATELESS_HTTP` | Set `true` for Fly.io stateless HTTP mode |

## Versioning

Version is set in `pyproject.toml`. Bump it there before cutting a GitHub release — the release workflow publishes whatever version is in `pyproject.toml`.
