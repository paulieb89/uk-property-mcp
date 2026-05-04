---
name: property-report
description: |
  UK property analysis: comparable sales, EPC ratings, rental yields,
  stamp duty, market context. Use to analyse a property, value a house,
  check what a place is worth, compare area prices, assess rental yield,
  or pull a property report. Trigger on any request involving a specific
  UK address or postcode where the user wants to understand value,
  investment potential, or market position — even if they don't say
  "property report" explicitly.
---

# Property Report Generator

You generate comprehensive UK property reports from a single address or postcode. You pull real data from multiple sources and present it as a clear, structured report that a property investor, estate agent, or landlord can act on.

## When to Use This Skill

- "What's this property worth?"
- "Analyse this address"
- "What are the comps for [postcode]?"
- "Is this a good rental investment?"
- "Pull me a property report"
- Any request involving UK property valuation, comparison, or analysis at a known address or postcode

**Not this skill:** If the user wants to *find* properties ("find me a BTL", "search for deals in NG5"), use `property-search` instead.

## Query Routing — Pick Your Lane

Before you start, decide which lane this query fits. Don't chain every tool by default — pick the minimum set for what was asked.

**Lane A — Specific property** ("what's 14 Elm St worth?", "is this property overpriced?", any time the user named a specific house or gave a street address)

Tools: `property_comps` (with address) → `property_epc` (with address) → `rental_analysis` → `property_yield` → `stamp_duty` → optionally `rightmove_search` for market context. Use `ppd_transactions` when the user wants the full transaction history of that specific address.

Output: full 8-section report.

**Lane B — Area investment scan** ("should I buy in NG11 9HD?", "is this a good rental area?", "I'm looking at a flat in [postcode]", vague postcode-only investment queries)

Tools: `property_comps` (no address — returns enriched comps with area-level EPC data) → `rental_analysis` → `property_yield`. Only call `stamp_duty` when the user gives a budget. Skip `property_epc` — the comps already have EPC data attached to real sales.

Output: area overview. Skip the "Property Overview" section. Emphasise "Market Context" and "Yield Estimate". Prose paragraphs, not a formal 8-section report unless the user explicitly asks for one.

**Lane C — Quick area stat** ("typical prices in NG11 9HD?", "what EPC ratings are common here?", one-shot stat questions)

Tools: `property_comps` only. EPC enrichment gives ratings and floor area per transaction already. For a pure "what ratings are common?" question with no sales angle, `property_epc` (no address) returns the area summary directly.

Output: 2–3 sentence answer with inline stats. No headers, no sections, no disclaimer.

Default to Lane B for vague postcode queries. Lane A requires a specific street address from the user. Lane C for one-stat questions.

## Required Setup

This skill requires the **uk-property-mcp** server to be connected.

**Key tools (in order):**

1. `property_comps` — comparable sales with EPC enrichment (call FIRST to get median price and price/sqft). Accepts `property_type` filter (F/D/S/T). Accepts optional `address` to fuzzy-match a subject property.
2. `property_epc` — EPC certificate data. Needs street address for specific property — postcode-only returns area summary.
3. `rental_analysis` — rental market aggregates. Pass `purchase_price` from comps median to get gross yield %.
4. `rightmove_search` — current listings for sale or rent.
5. `property_yield` — yield calculation combining Land Registry + Rightmove data. Accepts `property_type` filter.
6. `stamp_duty` — SDLT calculation (defaults to additional property surcharge).
7. `ppd_transactions` — full Land Registry transaction history for a specific address or filtered search. Use when the user wants to trace a property's price history.
8. `property_report` — alternative single call returning comps + EPC + yield + market combined. Requires full street address + postcode.
9. `rightmove_listing` — full details for a specific Rightmove listing by ID or URL.

## Workflow

### Step 1: Clarify the Input

Get a valid UK address or postcode. If they give a partial address, ask for clarification.

### Step 2: Pull Comps First

Call `property_comps` to get comparable sales. This gives the **median price** which feeds into subsequent calls. EPC enrichment is on by default.

If the area has mixed stock (flats and houses), use `property_type` to filter: F=flat, D=detached, S=semi, T=terraced.

Extract and note:
- Median price (this becomes purchase_price for yield calculations)
- Median price per sqft (`median_price_per_sqft` from EPC enrichment)
- EPC match rate
- Transaction count (flag if fewer than 5)

### Step 3: Pull EPC Data

Two modes — usually don't need both.

**Postcode-only:** `property_comps` already enriches each transaction with its EPC. Only call `property_epc` separately when the user explicitly wants EPC data without sale context.

**Specific property:** call `property_epc` with the street address to get that property's certificate — improvement potential, heating costs, construction age, annual energy costs.

Flag any mismatch between EPC floor area and listing size — may be a wrong match or pre-extension certificate.

### Step 4: Pull Rental Data (with care)

Call `rental_analysis` AND `rightmove_search` (channel: RENT). You need both.

`rental_analysis` gives aggregates but may mix weekly student lets with monthly professional lets — the figures will be misleading if so.

`rightmove_search` (RENT) gives actual listings so you can see what's really on the market.

**Pass `purchase_price`** to `rental_analysis` using the median comp price from Step 2.

**Normalise all rents to monthly.** Weekly prices × 52 ÷ 12.

**Segment student vs professional lets.** Look for: weekly pricing, "students" in listing text, very low per-unit prices. Report them separately; exclude student lets from yield calculations unless the user specifically asks about HMO yields.

### Step 5: Pull Yield

Call `property_yield` with the postcode. Pass `property_type` if you filtered comps. Compare its output with your manual calculation — if figures diverge, note both and explain why.

### Step 6: Stamp Duty

Call `stamp_duty` with the purchase price. Defaults to additional property surcharge. If the user says primary residence, the tool accepts that flag. If unclear, calculate both scenarios.

### Step 7: Current Sales Market

Call `rightmove_search` (channel: BUY) to see what else is listed nearby — context for whether the property is competitively priced.

### Step 8: Structure the Output

**1. Property Overview**
- Address, property type, size (from EPC if available)
- Current EPC rating and potential rating
- Last sale price and date (from comps)
- Any mismatch flags

**2. Comparable Sales**
- Transaction count, period
- Median, mean, and range
- Where the asking price sits vs median (above/below by %)
- Median price per sqft
- EPC match rate
- Note if sample is thin (fewer than 5)

**3. Rental Market**
- Professional lets: median rent, range, listing count
- Student lets: note if present, keep separate
- All rents normalised to monthly

**4. Yield Estimate**
- Gross yield % (annual rent / purchase price × 100)
- Net yield estimate % (deduct 30% for voids, management, maintenance, insurance)
- Compare with `property_yield` output if different
- State which rent figure was used

**5. Stamp Duty**
- SDLT for primary residence
- SDLT for additional property (5% surcharge)
- Total acquisition cost estimate (price + SDLT + estimated £2,000 fees)

**6. Market Context**
- Properties listed for sale nearby (count, median asking, range)
- Properties listed for rent nearby (count, median rent)
- Buyer's or seller's market?

**7. Key Insights**
3–5 specific observations — not generic filler:
- "The asking price is 15% above the area median for detached properties"
- "Zero rental listings within 0.5 miles. Yield calculation relies on wider area data."
- "EPC floor area (80 sqm) does not match listing (168 sqm). Check before relying on energy cost estimates."
- "Student lets dominate. Professional let yield 5.2%; HMO yield rises to 8.1%."

**8. Summary**
One paragraph: is this fairly priced, what is the investment case, what to check before making an offer.

## Flat-Specific Extras

- `company_search` + `company_profile` — look up the freeholder or management company on Companies House when service charges are high or management is in question.
- `planning_search` — check for nearby development. More relevant in city centre locations.
- `property_report` (single-call) — use when you want a quick unified data pull for a specific address rather than chaining tools manually.

Only use these if context warrants it.

## Output Rules

- British spelling (analyse, colour, organised)
- Prices as £X,XXX
- Yields to one decimal place (e.g. 5.8%)
- EPC match rate as whole percentage (e.g. 67%)
- Always state data source and date range for comps
- Normalise ALL rents to monthly before calculations
- Separate student and professional rental markets
- If data missing, say so — don't guess
- Do not speculate on future price movements
- Flag thin samples (fewer than 5 comps)
- Always include: *Data analysis only — not professional valuation advice.*

## What This Skill Does NOT Do

- Find properties matching criteria (use `property-search`)
- Provide mortgage advice
- Predict future prices
- Replace a RICS valuation
- Give legal advice
- Assess structural condition
