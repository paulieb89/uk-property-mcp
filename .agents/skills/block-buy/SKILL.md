---
name: block-buy
description: |
  UK block-buy opportunity analysis. Identifies buildings with multiple
  flat sales — developer selldowns, investor exits, bulk-buy targets.
  Use when the user asks about block buying, multi-unit purchases, buying
  multiple flats in a building, investor activity in a building, whether
  a developer is offloading units, or finding buildings where several
  flats have recently traded. Trigger on: "block buy", "block purchase",
  "multiple flats in the same building", "investor exit", "developer
  selldown", "how many units have sold in [building/postcode]".
---

# Block-Buy Opportunity Analyser

You identify buildings where multiple flats have traded in a given period — a signal of developer selldowns, investor exits, or bulk-buy opportunities. This is specialist investor research: the patterns matter as much as the raw numbers.

## When to Use This Skill

- "Is there a block buy opportunity near [postcode]?"
- "Has a developer been selling off flats in [area]?"
- "Find buildings where multiple units have changed hands"
- "I want to buy multiple flats in the same building — what's active?"
- "Is there investor exit activity in [postcode]?"

**Not this skill:** If the user wants to analyse a single property or area for rental yield, use `property-report` or `property-search`.

## Step 1: Clarify the Search

Before calling any tools, confirm:

1. **Postcode** — the area to scan. If the user gives a building name or address, extract the postcode.
2. **Timeframe** — how far back to look (default 24 months). A shorter window (6–12 months) catches active selldowns; a longer window (36–48 months) reveals slower investor exits.
3. **Search scope** — should you look at just this postcode, the sector, or the wider district? Sector is the default and usually right. Postcode-level is best for a specific building; district-level for broad area scouting.
4. **Minimum transactions** — how many sales in a building to qualify (default 2). Lower this to 1 only if the user wants to see all buildings with any recent activity; keep at 2+ for genuine block signals.

## Step 2: Run `property_blocks`

Call `property_blocks` with:
- `postcode` — the area
- `months` — lookback period
- `min_transactions` — 2 (default) or as clarified
- `search_level` — `"sector"` (default), `"postcode"`, or `"district"`
- `limit` — 50 (default) is fine for most searches; reduce if the output is too broad
- `property_type` — `"F"` (flats, the default) for block-buy research; pass `None` if the user wants all property types

The tool groups Land Registry transactions by building name and returns blocks sorted by transaction count.

**Reading the output:**
- `blocks_found` — total qualifying buildings
- Each block has: `building_name`, `transaction_count`, `transactions` (list of sales with address, price, date)
- High `transaction_count` in a short window = active selldown
- Prices declining over time within a block = possible distressed seller
- Prices increasing = developer confidence in the area

## Step 3: Identify the Pattern

Look at the top blocks and classify each:

| Pattern | Signal |
|---|---|
| Many sales in < 6 months | Active developer selldown or investor exit |
| Sales spread evenly over 24 months | Normal turnover — not a block signal |
| Prices falling across transactions | Motivated/distressed seller |
| Prices rising across transactions | Strong demand; developer holding price |
| Single seller across multiple units | Corporate seller — worth a Companies House lookup |
| New-build address style (e.g. "Apt", "Plot") | Developer selling off-plan completions |

## Step 4: Look Up the Freeholder (for promising blocks)

For the 1–3 most interesting blocks, call `company_search` using the building name or address to find the freeholder or management company:

```
company_search(query="[Building Name] [area]")
```

Then call `company_profile` with the company number to get:
- Company status (active/dissolved/in administration)
- Directors and date of incorporation
- SIC code (tells you if it's a property company)
- Filing history (accounts due? late filings signal financial stress)

A dissolved freeholder or one with late accounts is a red flag for service charge disputes and future enfranchisement complications.

## Step 5: Cross-Check with Comps

For the top block candidate, call `property_comps` with the postcode and `property_type="F"` to understand:
- What comparable flats in the area have sold for
- Whether the block's transaction prices are at, above, or below the area median
- Whether the block represents a discount opportunity

This gives the investor context for negotiating a bulk price.

## Step 6: Structure the Output

---

**Block-Buy Analysis: [Postcode], [months] months**

**Scan Summary**
- Buildings scanned: [search_level] level
- Qualifying blocks (≥ [min_transactions] sales): [blocks_found]
- Period: [months] months

**Top Block Opportunities**

For each of the top 3–5 blocks:

> **[Building Name]**
> - Sales: [count] in [period]
> - Price range: £[min] – £[max]
> - Price trend: [rising / falling / flat]
> - Pattern: [e.g. "active selldown — 4 units in 6 months, prices stable"]
> - Freeholder: [company name, status] or "not identified"
> - vs. Area median: [above/below by X%]

**Area Comps Context**
- Sector median (flats): £[X]
- Median price/sqft: £[X] (if EPC-enriched data available)
- Sample: [N] transactions over [period]

**Investment Interpretation**
[2–3 sentences synthesising the opportunity: is there a genuine block play, what's the likely seller motivation, what the investor should do next]

**Risks to Flag**
- Thin market (few comps)? Note yield data may be unreliable
- Freeholder issues (dissolved, late accounts)?
- New-build — no long-run price history?
- All sales from one seller — worth investigating their motive before approaching

---

## Output Rules

- Use British spelling (analyse, colour, organised)
- Present all prices as £X,XXX
- Always state the search scope (postcode / sector / district) so the user knows what was covered
- Clearly separate pattern interpretation from raw data — what the numbers mean matters more than listing them
- If `blocks_found` is 0: say so, explain what that means (no multi-unit trading in this area/period), suggest widening the search (district level, longer window)
- If all blocks have only 2 transactions: note this is the minimum threshold, not a strong signal
- Always include: *Land Registry data has a publication lag of 2–6 months. Recent sales may not appear.*

## What This Skill Does NOT Do

- Assess leasehold terms, ground rent, or service charge levels
- Identify off-market portfolios or private block sales
- Access auction data
- Negotiate or contact sellers
- Provide legal advice on enfranchisement or collective purchase
- Replace a solicitor's due diligence on title and lease

Once the user identifies a target block, `property-report` can analyse individual units within it.
