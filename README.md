# uk-property-mcp

UK property data MCP server for AI hosts (Claude, ChatGPT). Wraps Land Registry, Rightmove, EPC, rental yields, stamp duty, and Companies House into 13 tools.

## Install

```bash
pip install uk-property-mcp
```

Or with uvx (no install required):

```bash
uvx uk-property-mcp
```

## Connect

### Claude Code / Claude Desktop (stdio)

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "property": {
      "command": "uvx",
      "args": ["uk-property-mcp"]
    }
  }
}
```

### Claude.ai (remote)

`https://uk-property-mcp.fly.dev/mcp`

## Tools

| Tool | Description |
|------|-------------|
| `property_report` | Full data pull — comps + EPC + yield + market (needs street address + postcode) |
| `property_comps` | Land Registry comparable sales with EPC-enriched price/sqft |
| `ppd_transactions` | Transaction search by postcode, address, date range, or price |
| `property_yield` | Gross rental yield (PPD sales + Rightmove rentals) |
| `rental_analysis` | Rental market stats, optional yield from purchase price |
| `property_epc` | EPC certificate lookup |
| `rightmove_search` | Rightmove listings for sale or rent |
| `rightmove_listing` | Full details for a specific Rightmove listing |
| `property_blocks` | Block-buy opportunities (buildings with multiple flat sales) |
| `stamp_duty` | SDLT calculator with all surcharges |
| `planning_search` | Local council planning portal URL |
| `company_search` | Companies House search by name |
| `company_profile` | Full Companies House record by company number |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EPC_API_EMAIL` | EPC tools | EPC Register API email |
| `EPC_API_KEY` | EPC tools | EPC Register API key |
| `COMPANIES_HOUSE_API_KEY` | company_* tools | Companies House API key (free at developer.company-information.service.gov.uk) |
| `RIGHTMOVE_DELAY_SECONDS` | No | Rate limit delay (default 0.6s) |
| `PORT` | No | HTTP port when self-hosting (default 8080) |

Copy `.env.example` to `.env` and fill in credentials.

Agent skills for common workflows (property reports, deal sourcing, block-buy analysis) are in [`.agents/skills/`](.agents/skills/).
