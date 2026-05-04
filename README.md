<!-- mcp-name: io.github.paulieb89/uk-property-mcp -->

# uk-property-mcp

UK property data MCP server for AI agents. Wraps Land Registry, Rightmove, EPC, rental yields, stamp duty, and Companies House into 13 tools — one connection, no paywalls.

[![PyPI](https://img.shields.io/pypi/v/uk-property-mcp)](https://pypi.org/project/uk-property-mcp/)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=property-mcp&config=%7B%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fuk-property-mcp.fly.dev%2Fmcp%22%7D)
[![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install_Server-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=property-mcp&config=%7B%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fuk-property-mcp.fly.dev%2Fmcp%22%7D&quality=insiders)
[![Install in Cursor](https://img.shields.io/badge/Cursor-Install_Server-000000?style=flat-square&logoColor=white)](https://cursor.com/en/install-mcp?name=property-mcp&config=eyJ0eXBlIjoiaHR0cCIsInVybCI6Imh0dHBzOi8vdWstcHJvcGVydHktbWNwLmZseS5kZXYvbWNwIn0=)

---

## Data Sources

| Source | API | Auth |
|--------|-----|------|
| Land Registry (PPD) | `landregistry.data.gov.uk` SPARQL | None |
| EPC Register | `epc.opendatacommunities.org` | API key (free, optional) |
| Rightmove | rightmove.co.uk (scraping, polite) | None |
| postcodes.io | `api.postcodes.io` | None |
| Companies House | `api.company-information.service.gov.uk` | API key (free) |

---

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

---

## Connect

### Hosted (no install)

```json
{
  "mcpServers": {
    "property-mcp": {
      "type": "http",
      "url": "https://uk-property-mcp.fly.dev/mcp"
    }
  }
}
```

### Local (uvx)

```bash
export EPC_API_EMAIL=your_email
export EPC_API_KEY=your_key
export COMPANIES_HOUSE_API_KEY=your_key
```

```json
{
  "mcpServers": {
    "property-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["uk-property-mcp"]
    }
  }
}
```

### API Keys

| Key | Where to get it |
|-----|----------------|
| `EPC_API_EMAIL` / `EPC_API_KEY` | [epc.opendatacommunities.org](https://epc.opendatacommunities.org) — free registration |
| `COMPANIES_HOUSE_API_KEY` | [developer.company-information.service.gov.uk](https://developer.company-information.service.gov.uk) — free |

EPC credentials are optional — the server degrades gracefully without them. `COMPANIES_HOUSE_API_KEY` is required for the `company_search` and `company_profile` tools.

---

## Agent Skills

Routing skills for common workflows are in [`.agents/skills/`](.agents/skills/):

- `property-report` — full property report from address + postcode
- `property-search` — deal sourcing and comparable analysis

---

## Licence

MIT
