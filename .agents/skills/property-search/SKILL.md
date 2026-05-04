---
name: property-search
description: |
  UK property deal sourcing and investment screening. Use when the user
  wants to FIND properties matching criteria — budget, area, yield target,
  property type. Triggers on searching and browsing intent: "find me",
  "source deals", "what's available in", "looking for BTLs", "search for
  properties under £X", "show me flats in [area]". Do NOT use for
  analysing a specific known address — that is property-report.
---

# Property Deal Sourcer

You surface UK investment property candidates from Rightmove, screen them against yield and price criteria, and present a shortlist an investor can act on. This skill is about FINDING, not ANALYSING — once the user has a specific address they want to dig into, hand off to `property-report`.

## When to Use This Skill

- "Find me a buy-to-let in Nottingham under £150k"
- "Source deals in NG5 yielding 6% or more"
- "What's available in DE22 under £200k?"
- "Show me flats for sale in [area]"
- "I'm looking for investment properties around [postcode]"

**Not this skill:** If the user gives a specific address and wants to know its value, comps, or EPC — use `property-report`.

## Step 1: Clarify the Search Criteria

Before running any tools, confirm:

1. **Area** — postcode, district (e.g. NG5), or city/town. If city name, ask for a postcode anchor.
2. **Budget ceiling** — maximum purchase price. Ask if not given.
3. **Property type** — flat, house, any? Matters for yield accuracy.
4. **Yield target** — minimum gross yield %, or "any"?
5. **BTL or primary residence** — affects stamp duty.

If the user is browsing without hard criteria, proceed with what you have.

## Step 2: Search Rightmove for Candidates

Call `rightmove_search` with:
- `postcode` — the area postcode
- `channel` — "BUY"
- `max_price` — budget ceiling if given
- `property_type` — "F" for flats, "H" for houses, or omit for all
- `radius` — start at 0.5 miles; widen to 1.0 or 1.5 if fewer than 10 results

Returns up to 25 listings (one page only — Rightmove does not expose further pages).

Prioritise candidates by:
- Price headroom below budget (room to negotiate)
- "Reduced" flags — motivated seller signal
- Long time on market — another motivated seller signal

Pick the top 3–5 candidates. If fewer than 5 returned, screen all of them.

Use `rightmove_listing` to fetch full details on any specific listing the user wants to drill into.

## Step 3: Screen Candidates Against Yield

For each candidate postcode, call `property_yield`:
- Pass `property_type` matching your search (F/D/S/T) — prevents cross-type contamination
- Note `gross_yield_pct`, `yield_assessment`, `data_quality`, and `thin_market`

**Interpretation:**
- `yield_assessment: "strong"` — typically 6%+
- `yield_assessment: "average"` — 4–6%
- `yield_assessment: "weak"` — below 4%

**Data quality traps to flag:**
- `thin_market: true` — yield is indicative, not reliable. Consider widening search level.
- Student let contamination — university areas inflate yield via weekly lets. Call `rental_analysis` and inspect actual listings if suspected.
- Mixed property types — always pass `property_type` when the user has specified one.

## Step 4: Calculate Stamp Duty

Call `stamp_duty` for the budget ceiling (BTL surcharge applies by default). If primary residence, the tool accepts that flag. Present both scenarios if unclear.

## Step 5: Present the Shortlist

---

**Property Search: [Area], Budget £[X][, Yield Target [Y]%]**

**Area Yield Snapshot** (from `property_yield`)
- Median sale price: £X
- Median monthly rent: £X/month
- Gross yield: X.X% ([strong/average/weak])
- Data quality: [good/low/insufficient]
- [Flag thin market or student contamination if present]

**Shortlist**

| # | Address | Asking Price | vs. Budget | Flags |
|---|---|---|---|---|
| 1 | ... | £X | -X% headroom | Reduced |
| 2 | ... | £X | at ceiling | New instruction |

**Stamp Duty** (BTL, budget ceiling £X): £X (X.X% effective rate)

**Estimated Total Acquisition Cost**: £X + £X SDLT + £2,000 fees = £X

**Investment Summary**
[2–3 sentences: is this area worth pursuing, what yield data says, material risks]

**Caveats**
[Thin market? Student area? Page 1 only — not exhaustive? New builds absent from yield data?]

---

## Output Rules

- British spelling (analyse, colour, organised)
- All prices as £X,XXX
- Yields to one decimal place
- Always note if results are page 1 only (not exhaustive)
- Keep yield snapshot (area-level) clearly separate from listing shortlist (specific properties)
- Never conflate area yield with a specific property's yield — the property's actual yield depends on its purchase price and achievable rent
- Always include: *Data analysis for research purposes only — not financial advice. Yields are area estimates.*

## What This Skill Does NOT Do

- Access more than 25 Rightmove listings per search
- Retrieve rental figures for specific addresses (area estimates only)
- Arrange viewings or contact agents
- Assess structural condition, leasehold terms, or service charges
- Provide mortgage advice
- Predict future price movements
- Replace a RICS valuation or solicitor's due diligence

Once the user picks a specific property, switch to `property-report` for full analysis.
