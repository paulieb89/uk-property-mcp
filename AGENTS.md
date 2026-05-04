# uk-property-mcp — Agent Usage Guide

UK property data MCP server. 13 tools covering Land Registry, EPC, Rightmove, rental yields, stamp duty, and Companies House.

## Connection

**Hosted:** `https://uk-property-mcp.fly.dev/mcp`
**Local:** `uvx uk-property-mcp`

## Available Tools

- `property_report` — full data pull (comps + EPC + yield + market) for a street address + postcode; use this first when you have both
- `property_comps` — Land Registry comparable sales with EPC-enriched price/sqft; postcode only
- `ppd_transactions` — transaction search by postcode, address, date range, or price
- `property_yield` — gross rental yield from PPD sales + Rightmove rentals
- `rental_analysis` — rental market stats; pass purchase price for yield calculation
- `property_epc` — EPC certificate lookup; needs street address for exact match
- `rightmove_search` — Rightmove listings for sale or rent
- `rightmove_listing` — full detail for a specific Rightmove listing by URL or ID
- `property_blocks` — block-buy opportunities (buildings with multiple flat sales)
- `stamp_duty` — SDLT calculator with all surcharges (additional dwelling, non-resident)
- `planning_search` — local council planning portal URL for a postcode
- `company_search` — Companies House search by company name
- `company_profile` — full Companies House record by company number

## Usage Tips

- Use `property_report` when you have both a street address and postcode — it combines comps, EPC, and yield in one call
- For postcode-only queries, call `property_comps` and `property_yield` separately
- `property_epc` needs a street address (not just postcode) for an exact certificate match
- `company_search` → `company_profile` for any landlord/developer research
- `COMPANIES_HOUSE_API_KEY` is required for the company_* tools; EPC key is optional

## Agent Skills

Routing skills for property reports and deal sourcing are in [`.agents/skills/`](.agents/skills/).
