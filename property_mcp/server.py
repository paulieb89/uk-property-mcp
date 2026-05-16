"""UK property data MCP server — thin wrapper over property_core for AI hosts.

Run:  property-mcp
    or: pip install uk-property-mcp && property-mcp
"""

from __future__ import annotations

import os
import time
from functools import partial
from statistics import median as stat_median
from typing import Any, Optional

import anyio
import httpx
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.caching import (
    CallToolSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
from prometheus_client import Counter as PromCounter, Histogram

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

TRANSPORT = os.getenv("MCP_TRANSPORT", "http")
REGION = os.getenv("FLY_REGION", "local")

tool_calls_total = PromCounter(
    "property_mcp_tool_calls_total",
    "Count of MCP tool invocations.",
    labelnames=["tool", "transport", "region", "status"],
)
tool_duration_seconds = Histogram(
    "property_mcp_tool_duration_seconds",
    "Tool invocation latency in seconds.",
    labelnames=["tool", "transport", "region"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


class PrometheusMiddleware(Middleware):
    """Emit fleet-standard Prometheus metrics on every tool call."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = context.message.name
        t0 = time.perf_counter()
        try:
            result = await call_next(context)
            tool_calls_total.labels(tool_name, TRANSPORT, REGION, "ok").inc()
            return result
        except BaseException:
            tool_calls_total.labels(tool_name, TRANSPORT, REGION, "error").inc()
            raise
        finally:
            tool_duration_seconds.labels(tool_name, TRANSPORT, REGION).observe(
                time.perf_counter() - t0
            )


def _slim(obj: Any) -> Any:
    """Strip raw/images/floorplans/epc_match keys + drop None values recursively.

    The bulk-key stripping is the original behaviour. The None-dropping kills
    placeholder fields like the 10 EPC enrichment keys on PPDTransaction that
    are always null without explicit enrichment — ~190 wasted tokens per
    transaction in pre-fix responses.
    """
    if isinstance(obj, dict):
        return {
            k: _slim(v) for k, v in obj.items()
            if v is not None and k not in ("raw", "images", "floorplans", "epc_match")
        }
    if isinstance(obj, list):
        return [_slim(item) for item in obj]
    return obj


mcp = FastMCP(
    "property-server",
    middleware=[PrometheusMiddleware()],
    instructions=(
        "UK property data tools. Use property_report for a full data pull when "
        "you have a street address + postcode (comps + EPC + yield + market in "
        "one call). For postcode-only queries, use property_comps (comparable "
        "sales with EPC-enriched price/sqft) and property_yield separately. "
        "ppd_transactions for specific property history or filtered searches, "
        "rightmove_search to browse current listings for sale or rent, then "
        "rightmove_listing for full detail on a specific listing. "
        "property_epc for energy certificates (needs street address for exact "
        "match). rental_analysis for rental market figures, stamp_duty for SDLT, "
        "property_blocks for block-buy opportunities, planning_search for council "
        "planning portals, company_search to find a company by name, then "
        "company_profile for the full profile. "
        "For structured investment reports and property analysis skills, "
        "see https://bouch.dev/products "
    ),
)


# ---------------------------------------------------------------------------
# Tools — each returns a plain dict so FastMCP generates proper outputSchemas
# ---------------------------------------------------------------------------


@mcp.tool()
async def property_report(
    address: str,
    include_rentals: bool = True,
    include_sales_market: bool = True,
    ppd_months: int = 24,
    search_radius: float = 0.5,
    property_type: Optional[str] = None,
) -> dict:
    """Full data pull for a UK property in one call.

    Returns sale history, area comps, EPC rating, rental market listings,
    current sales market listings, rental yield calculation, and price range
    from area median.

    Requires a street address + postcode for subject property identification.
    Postcode-only (e.g. "NG1 2NS") returns area-level data without a subject
    property — use property_comps or property_yield for postcode-only queries.

    Args:
        address: Street address with postcode, e.g. "10 Downing Street, SW1A 2AA"
        include_rentals: Include Rightmove rental market analysis (default true)
        include_sales_market: Include Rightmove sales market (default true)
        ppd_months: Lookback period for comparable sales (default 24)
        search_radius: Radius in miles for Rightmove searches (default 0.5)
        property_type: Filter comparable sales by type: F=flat, D=detached, S=semi, T=terraced (default all)
    """
    from property_core import PropertyReportService

    report = await PropertyReportService().generate_report(
        address_query=address,
        include_rentals=include_rentals,
        include_sales_market=include_sales_market,
        ppd_months=ppd_months,
        search_radius=search_radius,
        property_type=property_type,
    )
    data = _slim(report.model_dump(mode="json", exclude_none=True))

    from property_core.interpret import generate_insights

    insights = generate_insights(report)
    sources = [s.name for s in (report.sources or []) if s.available]
    summary = f"Property report for {report.query_postcode}"
    if insights:
        summary += "\n" + "\n".join(insights[:5])
    if sources:
        summary += f"\nSources: {', '.join(sources)}"

    data["_summary"] = summary
    return data


@mcp.tool()
async def property_comps(
    postcode: str,
    months: int = 24,
    limit: int = 30,
    search_level: str = "sector",
    address: Optional[str] = None,
    property_type: Optional[str] = None,
    transaction_category: Optional[str] = "A",
    filter_outliers: bool = False,
    enrich_epc: bool = True,
    auto_escalate: bool = True,
) -> dict:
    """Comparable property sales from Land Registry Price Paid Data.

    Returns clean residential standard sales by default. Bulk transfers
    (transaction_category "B") and commercial units are excluded unless
    you opt back in. Auto-escalates to wider search area if fewer than 5
    results found.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA", "NG11 9HD")
        months: Lookback period in months (default 24)
        limit: Max transactions to return (default 30)
        search_level: Search area granularity - usually leave as default
        address: Optional street address to identify subject property and show percentile rank
        property_type: Residential filter. None (default) = residential set (F+D+S+T).
            "F"=flat, "D"=detached, "S"=semi, "T"=terraced, "O"=commercial-only.
            Pass "ALL" for the raw firehose including commercial.
        transaction_category: "A" (default) = standard residential sales only.
            Pass None to include category-B (bulk transfers, intra-group conveyances).
        filter_outliers: When True, applies a 1.5×IQR price filter (needs ≥4 prices).
            Default False — median is naturally robust; opt in for a cleaner mean.
        enrich_epc: Add floor area, price/sqft, and EPC rating to each comp (default true)
        auto_escalate: Widen search area if fewer than 5 results (default true). Set false to keep results local — useful when district-level escalation would include irrelevant areas.
    """
    from property_core import PPDService
    from property_core.epc_client import EPCClient
    from property_core.enrichment import compute_enriched_stats, enrich_comps_with_epc

    limit = min(limit, 100)
    result = await anyio.to_thread.run_sync(
        partial(
            PPDService().comps,
            postcode=postcode,
            months=months,
            limit=limit,
            search_level=search_level,
            address=address,
            property_type=property_type,
            transaction_category=transaction_category,
            filter_outliers=filter_outliers,
            auto_escalate=auto_escalate,
        )
    )

    if enrich_epc and result.transactions:
        epc = EPCClient()
        if epc.is_configured():
            result.transactions = await enrich_comps_with_epc(
                result.transactions, epc
            )
            result = compute_enriched_stats(result)

    data = _slim(result.model_dump(mode="json"))

    summary = f"Found {result.count} comps for {postcode}"
    if result.median:
        summary += f", median £{result.median:,}"
    if result.escalated_from:
        summary += f" (expanded from {result.escalated_from} to {result.escalated_to})"
    if enrich_epc and result.epc_match_rate is not None:
        summary += f" (EPC matched {result.epc_match_rate}%)"

    data["_summary"] = summary
    return data


@mcp.tool()
async def ppd_transactions(
    postcode: Optional[str] = None,
    street: Optional[str] = None,
    town: Optional[str] = None,
    paon: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    property_type: Optional[str] = None,
    limit: int = 25,
) -> dict:
    """Search Land Registry transactions by postcode, address, date range, or price.

    Use for specific property history ("what has 10 Downing Street sold for?")
    or filtered market queries ("all sales over 500k in SW1 last year").

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA") - required for postcode search
        street: Street name for address-based search
        town: Town name for address-based search
        paon: Primary address (house name/number) for address-based search
        from_date: Start date filter (ISO format, e.g. "2023-01-01")
        to_date: End date filter (ISO format)
        min_price: Minimum price filter in £
        max_price: Maximum price filter in £
        property_type: Filter by type: F=flat, D=detached, S=semi, T=terraced
        limit: Max results to return (default 25)
    """
    from property_core import PPDService

    svc = PPDService()
    limit = min(limit, 100)

    if street or paon:
        result = await anyio.to_thread.run_sync(
            partial(
                svc.address_search,
                paon=paon,
                street=street,
                town=town,
                postcode=postcode,
                limit=limit,
            )
        )
    else:
        result = await anyio.to_thread.run_sync(
            partial(
                svc.search_transactions,
                postcode=postcode,
                postcode_prefix=None,
                from_date=from_date,
                to_date=to_date,
                min_price=min_price,
                max_price=max_price,
                property_type=property_type,
                limit=limit,
            )
        )

    result["results"] = [t.model_dump(mode="json") for t in result["results"]]
    result.pop("raw", None)

    count = result["count"]
    location = postcode or street or "search"
    summary = f"Found {count} transactions for {location}"
    if result.get("warnings"):
        summary += f" (warnings: {', '.join(result['warnings'])})"

    result["_summary"] = summary
    return _slim(result)


@mcp.tool()
async def property_yield(
    postcode: str,
    months: int = 24,
    search_level: str = "sector",
    property_type: Optional[str] = None,
    radius: float = 0.5,
) -> dict:
    """Calculate rental yield for a UK postcode.

    Combines Land Registry sales data with Rightmove rental listings
    to produce a gross yield figure.

    Args:
        postcode: UK postcode (e.g. "NG11", "SW1A 1AA")
        months: Sales lookback period in months (default 24)
        search_level: "sector" (recommended), "district", or "postcode"
        property_type: Filter comparable sales by type: F=flat, D=detached, S=semi, T=terraced (default all)
        radius: Rental search radius in miles (default 0.5)
    """
    from property_core import calculate_yield

    result = await calculate_yield(
        postcode=postcode,
        months=months,
        search_level=search_level,
        property_type=property_type,
        radius=radius,
    )
    data = _slim(result.model_dump(mode="json"))

    from property_core.interpret import classify_data_quality, classify_yield

    if result.gross_yield_pct is not None:
        data["yield_assessment"] = classify_yield(result.gross_yield_pct)
    data["data_quality"] = classify_data_quality(result.sale_count, result.rental_count)

    summary = f"Yield analysis for {postcode}"
    if result.gross_yield_pct is not None:
        summary += f": {result.gross_yield_pct:.1f}% gross yield ({data['yield_assessment']})"
        summary += f", data quality: {data['data_quality']}"
    elif result.rental_count == 0:
        summary += f": no rental listings within {radius} miles"
        data["rental_note"] = (
            f"No rental listings found at {radius} mile radius. "
            f"Try property_yield with a wider radius, or use rental_analysis "
            f"which auto-escalates up to 1.5 miles."
        )
        summary += " — try wider radius or use rental_analysis (auto-escalates)"
    else:
        summary += f", data quality: {data['data_quality']}"

    data["_summary"] = summary
    return data


@mcp.tool()
async def rental_analysis(
    postcode: str,
    radius: float = 0.5,
    purchase_price: Optional[int] = None,
    auto_escalate: bool = True,
    building_type: Optional[str] = None,
) -> dict:
    """Rental market analysis for a UK postcode.

    Returns median/average rent, listing count, and rent range.
    Optionally calculates gross yield from a given purchase price.
    Auto-escalates search radius if local listings are sparse (thin market).

    Args:
        postcode: UK postcode (e.g. "NG1 1AA")
        radius: Search radius in miles (default 0.5)
        purchase_price: Optional purchase price to calculate gross yield
        auto_escalate: Widen radius if fewer than 3 listings found (default true)
        building_type: Filter by building type: F=flat, D=detached, S=semi, T=terraced (default all)
    """
    from property_core.rental_service import analyze_rentals

    result = await analyze_rentals(
        postcode,
        radius=radius,
        purchase_price=purchase_price,
        auto_escalate=auto_escalate,
        building_type=building_type,
    )
    data = _slim(result.model_dump(mode="json"))

    if result.gross_yield_pct is not None:
        from property_core.interpret import classify_yield
        data["yield_assessment"] = classify_yield(result.gross_yield_pct)

    summary = f"Rental analysis for {postcode}: {result.rental_listings_count} listings"
    if result.median_rent_monthly:
        summary += f", median £{result.median_rent_monthly:,.0f}/month"
    if result.gross_yield_pct is not None:
        summary += f", {result.gross_yield_pct:.1f}% gross yield ({data['yield_assessment']})"
    if result.escalated_from is not None:
        summary += f" (radius widened from {result.escalated_from}mi to {result.escalated_to}mi)"

    data["_summary"] = summary
    return data


@mcp.tool()
async def property_epc(
    postcode: str,
    address: Optional[str] = None,
) -> dict:
    """EPC certificate data for a UK property or postcode area.

    With address: returns the matched certificate for that property —
    energy rating, score, floor area, construction age, heating costs.

    Without address: returns all certificates at the postcode with
    area-level aggregation (rating distribution, floor area range,
    property type breakdown). Use this for area analysis rather than
    a single-property lookup.

    Args:
        postcode: UK postcode (e.g. "SW1A 1AA")
        address: Street address for exact match (omit for area view)
    """
    from collections import Counter

    from property_core.epc_client import EPCClient

    epc = EPCClient()
    if not epc.is_configured():
        return {"error": "EPC service not configured (set EPC_API_EMAIL and EPC_API_KEY)"}

    # Single-property mode — address provided
    if address:
        result = await epc.search_by_postcode(postcode, address=address)
        if not result:
            return {"error": f"No EPC found for {address} {postcode}".strip()}

        data = _slim(result.model_dump(mode="json", exclude_none=True))
        parts = [f"EPC for {address}"]
        if result.rating:
            parts.append(f"Rating: {result.rating} (score {result.score})")
        if result.floor_area:
            parts.append(f"Floor area: {result.floor_area} sqm")
        if result.property_type:
            parts.append(f"Type: {result.property_type}")
        if result.construction_age:
            parts.append(f"Built: {result.construction_age}")
        data["_summary"] = ", ".join(parts)
        return data

    # Area mode — no address
    certs = await epc.search_all_by_postcode(postcode)
    if not certs:
        return {"error": f"No EPC certificates found for {postcode}"}

    ratings = Counter(c.rating for c in certs if c.rating)
    types = Counter(c.property_type for c in certs if c.property_type)
    areas = [c.floor_area for c in certs if c.floor_area]

    rating_str = ", ".join(f"{r}:{n}" for r, n in sorted(ratings.items())) if ratings else "no ratings"
    summary = f"EPC area data for {postcode}: {len(certs)} certificates — {rating_str}"
    if areas:
        summary += f", floor area {int(min(areas))}-{int(max(areas))} sqm (avg {round(sum(areas) / len(areas))})"

    return {
        "_summary": summary,
        "postcode": postcode,
        "count": len(certs),
        "rating_distribution": dict(sorted(ratings.items())),
        "property_type_breakdown": dict(sorted(types.items())),
        "floor_area_min": min(areas) if areas else None,
        "floor_area_max": max(areas) if areas else None,
        "floor_area_avg": round(sum(areas) / len(areas), 1) if areas else None,
        "certificates": [_slim(c.model_dump(mode="json", exclude_none=True)) for c in certs],
    }


@mcp.tool()
async def rightmove_search(
    postcode: str,
    property_type: str = "sale",
    building_type: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_bedrooms: Optional[int] = None,
    max_bedrooms: Optional[int] = None,
    radius: Optional[float] = None,
    max_pages: int = 1,
    sort_by: Optional[str] = None,
) -> dict:
    """Search Rightmove property listings for sale or rent near a postcode.

    Returns prices, addresses, bedrooms, agent details, and listing URLs.

    Args:
        postcode: UK postcode (e.g. "NG1 1AA", "SW1A 2AA")
        property_type: "sale" or "rent" (default "sale")
        building_type: Filter by building type: F=flat, D=detached, S=semi, T=terraced (default all)
        min_price: Minimum price/rent filter in £
        max_price: Maximum price/rent filter in £
        min_bedrooms: Minimum bedrooms filter
        max_bedrooms: Maximum bedrooms filter
        radius: Search radius in miles (default varies by area)
        max_pages: Max pages to fetch (default 1, ~25 listings per page)
        sort_by: Sort order: "newest", "oldest", "price_low", "price_high", "most_reduced" (default: Rightmove default)
    """
    from property_core.rightmove_location import RightmoveLocationAPI
    from property_core.rightmove_scraper import fetch_listings

    url = await anyio.to_thread.run_sync(
        partial(
            RightmoveLocationAPI().build_search_url,
            postcode,
            property_type=property_type,
            building_type=building_type,
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            max_bedrooms=max_bedrooms,
            radius=radius,
            sort_by=sort_by,
        )
    )

    max_pages = min(max_pages, 5)
    listings = await anyio.to_thread.run_sync(
        partial(fetch_listings, url, max_pages=max_pages)
    )

    listing_dicts = [_slim(listing.model_dump(mode="json")) for listing in listings]
    prices = [listing.price for listing in listings if listing.price and listing.price > 0]
    summary = f"Found {len(listings)} {property_type} listings near {postcode}"
    if prices:
        median = int(stat_median(prices))
        summary += f", median £{median:,}, range £{min(prices):,}-£{max(prices):,}"

    return {
        "_summary": summary,
        "search_url": url,
        "count": len(listings),
        "listings": listing_dicts,
    }


@mcp.tool()
async def rightmove_listing(
    property_id: str,
    include_images: bool = False,
    max_images: int = 8,
) -> dict:
    """Fetch full details for a Rightmove listing by ID or URL.

    Returns price, tenure, lease years remaining, service charge, ground rent,
    council tax band, floor area, key features, nearest stations, and floorplan URLs.
    Set include_images=True to also fetch and return image URLs (use rightmove_listing
    without include_images for basic detail, check image_urls field for photos).

    Args:
        property_id: Rightmove property URL (e.g. "https://www.rightmove.co.uk/properties/12345678") or numeric ID (e.g. "12345678")
        include_images: Include image URLs in the response (default False)
        max_images: Max image URLs to include when include_images=True (default 8)
    """
    from property_core.rightmove_scraper import fetch_listing

    result = await anyio.to_thread.run_sync(
        partial(fetch_listing, property_id)
    )
    data = _slim(result.model_dump(mode="json"))

    summary = f"{result.address or 'Property'}"
    if result.price:
        summary += f" — £{result.price:,}"
    if result.tenure_type:
        summary += f" ({result.tenure_type})"
    if result.bedrooms:
        summary += f", {result.bedrooms} bed"
    if result.display_size:
        summary += f", {result.display_size}"

    if include_images:
        image_urls: list[str] = result.model_dump(mode="json").get("images") or []
        data["image_urls"] = image_urls[:min(max_images, 12)]
        summary += f" ({len(data['image_urls'])} image URLs)"

    data["_summary"] = summary
    return data


@mcp.tool()
async def property_blocks(
    postcode: str,
    months: int = 24,
    min_transactions: int = 2,
    limit: int = 50,
    search_level: str = "sector",
    property_type: Optional[str] = "F",
) -> dict:
    """Find buildings with multiple flat sales — block buying opportunities.

    Groups Land Registry transactions by building to identify blocks being
    sold off, investor exits, and bulk-buy opportunities.

    Args:
        postcode: UK postcode (e.g. "B1 1AA")
        months: Lookback period in months (default 24)
        min_transactions: Minimum sales per building to qualify (default 2)
        limit: Maximum number of blocks to return (default 50)
        search_level: Search granularity — "postcode", "sector", or "district" (default "sector")
        property_type: PPD property type filter — "F" for flats, None for all types (default "F")
    """
    from property_core.block_service import analyze_blocks

    result = await anyio.to_thread.run_sync(
        partial(
            analyze_blocks,
            postcode=postcode,
            months=months,
            limit=limit,
            min_transactions=min_transactions,
            search_level=search_level,
            property_type=property_type,
        )
    )
    data = _slim(result.model_dump(mode="json"))

    summary = f"Found {result.blocks_found} flat blocks for {postcode}"
    if result.blocks:
        top = result.blocks[0]
        summary += f" (top: {top.building_name}, {top.transaction_count} sales)"

    data["_summary"] = summary
    return data


@mcp.tool()
async def stamp_duty(
    price: int,
    additional_property: bool = True,
    first_time_buyer: bool = False,
    non_resident: bool = False,
) -> dict:
    """Calculate UK Stamp Duty Land Tax (SDLT) for a residential property.

    Args:
        price: Purchase price in £
        additional_property: True if buying additional property (+5% surcharge)
        first_time_buyer: True for first-time buyer relief (up to £300k nil rate)
        non_resident: True if buyer not UK resident (+2% surcharge)
    """
    from property_core.stamp_duty import calculate_stamp_duty

    result = calculate_stamp_duty(
        price=price,
        additional_property=additional_property,
        first_time_buyer=first_time_buyer,
        non_resident=non_resident,
    )
    data = _slim(result.model_dump(mode="json"))
    data["_summary"] = f"SDLT for £{price:,}: £{result.total_sdlt:,.0f} ({result.effective_rate}% effective rate)"
    return data


@mcp.tool()
async def planning_search(
    postcode: str,
) -> dict:
    """Find the planning portal URL for a UK postcode.

    Returns the council name, planning system type, and a direct URL to open in a browser.
    Does NOT return planning application data — scraping is blocked by council portals.
    Use the returned search_urls.direct_search link to browse applications manually.

    Args:
        postcode: UK postcode (e.g. "S1 1AA", "SW1A 2AA")
    """
    from property_core.planning_service import PlanningService

    result = await anyio.to_thread.run_sync(
        partial(PlanningService().search, postcode)
    )

    if result.get("council_found"):
        council = result.get("council", {})
        name = council.get("name", "Unknown")
        system = council.get("system", "unknown")
        summary = f"{name} ({system} system)"
        urls = result.get("search_urls", {})
        if urls.get("direct_search"):
            summary += f", direct search: {urls['direct_search']}"
    else:
        summary = f"No planning portal found for {postcode}"

    result["_summary"] = summary
    return _slim(result)


@mcp.tool()
async def company_search(
    query: str,
) -> dict:
    """Search Companies House by company name. Returns a list of matches.

    For a direct lookup by company number, use company_profile(company_number="00445790").

    Args:
        query: Company name to search (e.g. "Tesco", "Rightmove plc")
    """
    from property_core.companies_house_client import CompaniesHouseClient

    client = CompaniesHouseClient()
    if not client.is_configured():
        return {"error": "Companies House not configured (set COMPANIES_HOUSE_API_KEY)"}

    result = await anyio.to_thread.run_sync(partial(client.search, query))
    data = _slim(result.model_dump(mode="json"))
    data["_summary"] = f"Found {result.total_results} companies for '{query}'"
    return data


@mcp.tool()
async def company_profile(company_number: str) -> dict:
    """Get the full Companies House record for a company by number.

    Returns registered address, status, incorporation date, officers, and
    filing history. Use company_search to find a company number by name.

    Args:
        company_number: Companies House number (e.g. '00445790').
    """
    from property_core.companies_house_client import CompaniesHouseClient

    client = CompaniesHouseClient()
    if not client.is_configured():
        return {"error": "Companies House not configured (set COMPANIES_HOUSE_API_KEY)"}
    result = await anyio.to_thread.run_sync(partial(client.get_company, company_number))
    if result is None:
        return {"error": f"Company {company_number!r} not found"}
    data = _slim(result.model_dump(mode="json"))
    data["_summary"] = result.company_name or company_number
    return data


# ---------------------------------------------------------------------------
# Health + metrics routes (required by Fly.io health checks and Prometheus)
# ---------------------------------------------------------------------------

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/metrics", methods=["GET"])
async def metrics(request: Request) -> Response:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
async def server_card(request: Request) -> JSONResponse:
    from importlib.metadata import version as _pkg_version
    return JSONResponse({"serverInfo": {"name": "uk-property-mcp", "version": _pkg_version("uk-property-mcp")}})


@mcp.custom_route("/.well-known/glama.json", methods=["GET"])
async def glama_manifest(request: Request) -> JSONResponse:
    return JSONResponse({
        "$schema": "https://glama.ai/mcp/schemas/connector.json",
        "maintainers": [{"email": "paul@bouch.dev"}],
    })


# ---------------------------------------------------------------------------
# Accept header normalizer — ensures application/json is always present.
# Anthropic's infrastructure sends Accept: text/event-stream or */* for some
# MCP requests, which 406s against json_response=True. This middleware rewrites
# those before FastMCP sees them.
# ---------------------------------------------------------------------------

class _HttpGuard:
    """Return a held-open SSE stream for GET /mcp; 405 for DELETE /mcp.

    claude.ai probes GET /mcp to establish an SSE stream before sending MCP
    protocol messages via POST. With stateless_http=True FastMCP only registers
    POST routes, so GET returns 405 — claude.ai treats this as a connection
    failure even though POST works fine.

    Fix: intercept GET /mcp and return 200 text/event-stream held open until
    the client disconnects. FastMCP never sees the GET; stateless semantics
    are preserved. DELETE is rejected (405) — stateless servers have no sessions.
    """

    def __init__(self, app, mcp_path: bytes = b"/mcp"):
        self.app = app
        self._mcp_path = mcp_path.rstrip(b"/")

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "").rstrip("/").encode()
            method = scope.get("method", "").upper().encode()
            if path == self._mcp_path:
                if method == b"GET":
                    await send({"type": "http.response.start", "status": 200, "headers": [
                        (b"content-type", b"text/event-stream"),
                        (b"cache-control", b"no-cache"),
                        (b"connection", b"keep-alive"),
                    ]})
                    await send({"type": "http.response.body", "body": b"", "more_body": True})
                    while True:
                        event = await receive()
                        if event["type"] == "http.disconnect":
                            break
                    return
                if method == b"DELETE":
                    from starlette.responses import Response as StarletteResponse
                    await StarletteResponse("Method Not Allowed", status_code=405, headers={"Allow": "POST"})(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class _AcceptNormalizer:
    """Stamp Accept to the MCP-spec value on /mcp only, so json_response=True never 406s.

    Anthropic sends mixed Accept headers per request type (application/json for
    initialize, text/event-stream for tools/list). Only stamp the MCP endpoint —
    leave /metrics, /health, /.well-known/* with their original Accept headers so
    Prometheus scrapers and other clients aren't affected.
    """
    def __init__(self, app, mcp_path: bytes = b"/mcp"):
        self.app = app
        self._mcp_path = mcp_path.rstrip(b"/")

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").rstrip("/").encode() == self._mcp_path:
            headers = [
                (b"accept", b"application/json, text/event-stream")
                if name.lower() == b"accept"
                else (name, value)
                for name, value in scope.get("headers", [])
            ]
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    from fastmcp.server.http import create_streamable_http_app
    app = create_streamable_http_app(
        mcp,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
    uvicorn.run(
        _HttpGuard(_AcceptNormalizer(app)),
        host="0.0.0.0",
        port=port,
        forwarded_allow_ips="*",
        proxy_headers=True,
        lifespan="on",
        log_level="info",
    )


# 5 min cache — 1h caused OOM on 512MB machine under burst load (unbounded in-memory cache)
mcp.add_middleware(ResponseCachingMiddleware(
    read_resource_settings=ReadResourceSettings(ttl=300),
    call_tool_settings=CallToolSettings(ttl=300),
))


if __name__ == "__main__":
    main()
