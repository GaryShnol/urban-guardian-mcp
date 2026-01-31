"""
Urban Guardian (Israel) — MCP Server

Model Context Protocol server for real-time urban planning, construction
permits, and real estate insights by address in Israel.

Technical flow: geocode_address → get_cadastral_data → get_urban_plans → generate_guardian_report
Phase 1: Geographic Foundation (geocode_address) — GovMap
Phase 2: Cadastral & Planning (get_cadastral_data, get_urban_plans) — GovMap WFS/APIs
Phase 3: Urban Intelligence (generate_guardian_report) — AI synthesis
Phase 4: Environmental & Infrastructure — planned
"""

from __future__ import annotations

from fastmcp import FastMCP

from govmap_client import (
    AddressNotFoundError,
    get_cadastral_at_coordinates,
    get_detailed_plan_info,
    multi_radius_search,
    query_plans_at_coordinates,
    query_noise_data_at_coordinates,
    query_tama_at_coordinates,
    query_transport_infrastructure_at_coordinates,
    search_address,
    spatial_mining_at_coordinates,
    validate_coordinates_in_israel,
)
from guardian_score import (
    analyze_risks_detailed,
    build_comprehensive_report,
    build_consult_text,
    build_report_text,
    compute_guardian_score,
    explain_plan_risk,
)

MCP_NAME = "Urban Guardian"
mcp = FastMCP(MCP_NAME)


def _geocode_address_impl(address: str) -> dict:
    """Implementation of geocode_address (used by tool and tests)."""
    try:
        result = search_address(address)
        out = {
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "display_name": result.get("display_name"),
        }
        if "source" in result:
            out["source"] = result["source"]
        return out
    except AddressNotFoundError as e:
        return {
            "error": e.message,
            "suggestions": e.suggestions,
        }


@mcp.tool()
def geocode_address(address: str) -> dict:
    """
    Phase 1 — Geographic Foundation: Convert a human-readable address in Israel to WGS84 (Lat, Lon).

    Engine: GovMap Geocoding API. Fuzzy search for Hebrew/English; ITM → WGS84 conversion.
    If the address is not found, returns an error with "did you mean?" suggestions when available.

    Args:
        address: Street address and city (e.g. "HaYarkon 10, Tel Aviv" or "דיזנגוף 100,תל אביב").

    Returns:
        A dict with latitude, longitude, display_name (optional) on success;
        or error, suggestions when address not found.
    """
    return _geocode_address_impl(address)


def _get_cadastral_data_impl(latitude: float, longitude: float) -> dict:
    """Implementation of get_cadastral_data (used by tool and tests)."""
    result = get_cadastral_at_coordinates(latitude, longitude)
    out = {
        "gush": result.get("gush"),
        "helka": result.get("helka"),
        "note": result.get("note", "Cadastral query completed."),
    }
    if result.get("source"):
        out["source"] = result["source"]
    if result.get("layer"):
        out["layer"] = result["layer"]
    if result.get("features_count") is not None:
        out["features_count"] = result["features_count"]
    # FULL TRANSPARENCY - include complete API response
    out["raw_api_response"] = result
    return out


@mcp.tool()
def get_cadastral_data(latitude: float, longitude: float) -> dict:
    """
    Phase 2 — Cadastral: Get Block (Gush) and Parcel (Helka) at the given WGS84 coordinates.

    Data source: GovMap Cadastral Layers. Required for Tabu (Title Deed) and legal identity.

    Args:
        latitude: WGS84 latitude (e.g. 32.065).
        longitude: WGS84 longitude (e.g. 34.773).

    Returns:
        A dict with gush (block), helka (parcel), and optional address metadata.
    """
    return _get_cadastral_data_impl(latitude, longitude)


def _get_urban_plans_impl(latitude: float, longitude: float) -> dict:
    """Implementation of get_urban_plans (used by tool and tests)."""
    result = query_plans_at_coordinates(latitude, longitude)
    out = {
        "plans": result.get("plans", []),
        "permits": result.get("permits", []),
        "note": result.get("note", "Query completed."),
    }
    if result.get("method_used") is not None:
        out["method_used"] = result["method_used"]
    if result.get("features_count") is not None:
        out["features_count"] = result["features_count"]
    if result.get("radius_m_used") is not None:
        out["radius_m_used"] = result["radius_m_used"]
    # FULL TRANSPARENCY - include complete API response
    out["raw_api_response"] = result
    return out


@mcp.tool()
def get_urban_plans(latitude: float, longitude: float) -> dict:
    """
    Phase 2 — Planning: Get zoning (תב"ע) and building permits at the given WGS84 coordinates.

    Data source: GovMap API. Queries GovMap identify/query services for active/pending
    plans and permits (active, approved, or pending); status e.g. "In Deposit" (בהפקדה), "Valid".

    Args:
        latitude: WGS84 latitude (e.g. 32.065).
        longitude: WGS84 longitude (e.g. 34.773).

    Returns:
        A dict with lists of plans and permits (or empty lists), plus status and metadata.
        Each plan/permit includes name, number, status, and layer information.
    """
    return _get_urban_plans_impl(latitude, longitude)


def _get_spatial_mining_impl(
    latitude: float,
    longitude: float,
    radius_permits_m: float = 100,
    radius_plans_m: float = 500,
    radius_infrastructure_m: float = 1000,
) -> dict:
    """Implementation of get_spatial_mining (Station 3 — spatial data mining by radius)."""
    return spatial_mining_at_coordinates(
        latitude,
        longitude,
        radius_permits_m=radius_permits_m,
        radius_plans_m=radius_plans_m,
        radius_infrastructure_m=radius_infrastructure_m,
    )


@mcp.tool()
def get_spatial_mining(
    latitude: float,
    longitude: float,
    radius_permits_m: float = 100,
    radius_plans_m: float = 500,
    radius_infrastructure_m: float = 1000,
) -> dict:
    """
    Station 3 — Spatial Data Mining: Query plans and permits at multiple radii around a point.

    Scans different radii (as in the production line):
    - Permits (היתרי בנייה) up to radius_permits_m (default 100 m): e.g. neighbour building permit.
    - Plans (תב"ע) up to radius_plans_m (default 500 m): e.g. future commercial centre.
    - Wider context up to radius_infrastructure_m (default 1000 m): e.g. metro, power lines.

    Args:
        latitude: WGS84 latitude (e.g. 32.08).
        longitude: WGS84 longitude (e.g. 34.78).
        radius_permits_m: Radius in meters for permit search (default 100).
        radius_plans_m: Radius in meters for plans search (default 500).
        radius_infrastructure_m: Radius in meters for wider context (default 1000).

    Returns:
        Dict with within_100m, within_500m, within_1000m (each: plans, permits) and note.
    """
    return _get_spatial_mining_impl(
        latitude,
        longitude,
        radius_permits_m=radius_permits_m,
        radius_plans_m=radius_plans_m,
        radius_infrastructure_m=radius_infrastructure_m,
    )


def _get_multi_radius_search_impl(latitude: float, longitude: float) -> dict:
    """Implementation of get_multi_radius_search (layer-based radii for real estate)."""
    return multi_radius_search(latitude, longitude)


@mcp.tool()
def get_multi_radius_search(latitude: float, longitude: float) -> dict:
    """
    Multi-Radius Search: layer-based radii for real-estate and urban planning.

    Three circles of influence (no "one size fits all"):
    - Bedroom (0–50 m): lot + immediate neighbours — TAMA 38/2, balcony extensions, noise/dust, privacy.
    - Lifestyle (50–300 m): neighborhood character — towers blocking views, schools, commercial centers.
    - Value (300–800 m): national projects, metro, interchanges; >800 m = less relevant for daily noise.

    Layer-based radii: construction permits 100 m, תב"ע 500 m, transport 1000 m, hazards 200 m.

    Enables answers like: "אין בנייה בבניין שלך, אבל יש מגדל בבנייה במרחק 200 מטר".

    Args:
        latitude: WGS84 latitude (e.g. 32.08).
        longitude: WGS84 longitude (e.g. 34.78).

    Returns:
        Dict with keys bedroom_50m, permits_100m, lifestyle_300m, plans_500m, value_800m (each: plans,
        permits, radius_m, label_he, label_en), summary (has_any_bedroom, has_any_permits_100m, …),
        and note.
    """
    return _get_multi_radius_search_impl(latitude, longitude)


def _generate_guardian_report_impl(
    latitude: float,
    longitude: float,
    address: str | None = None,
    language: str = "en",
    comprehensive: bool = True,
    include_raw_data: bool = False,
) -> dict:
    """Implementation of generate_guardian_report (used by tool and tests).

    ENHANCED VERSION: Auto-analyzes risks and generates comprehensive report.

    Runs weighted analysis (Guardian Score): fetches cadastral + multi-radius plans/permits,
    plus noise, TAMA, and transport data; applies the decision matrix, and returns score,
    consult, report, risks, and opportunities.
    
    Args:
        latitude: WGS84 latitude
        longitude: WGS84 longitude
        address: Optional display address
        language: Report language ("he" or "en")
        comprehensive: If True, includes detailed risk analysis (default: True)
        include_raw_data: If True, includes full raw API responses (default: False for user-friendly output)
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {
            "report": None,
            "risks": [],
            "opportunities": [],
            "guardian_score": None,
            "consult": None,
            "language": language,
            "note": "Coordinates outside Israel bbox.",
        }
    
    # Fetch all data sources
    cadastral = get_cadastral_at_coordinates(latitude, longitude)
    multi_radius = multi_radius_search(latitude, longitude)
    
    # Fetch enhanced data (noise, TAMA, transport)
    noise_data = query_noise_data_at_coordinates(latitude, longitude)
    tama_data = query_tama_at_coordinates(latitude, longitude, radius_m=200)
    transport_data = query_transport_infrastructure_at_coordinates(latitude, longitude, radius_m=800)
    
    # Compute Guardian Score with all data
    score_result = compute_guardian_score(
        cadastral, 
        multi_radius,
        noise_data=noise_data,
        tama_data=tama_data,
        transport_data=transport_data,
    )
    
    # Auto-analyze risks for detailed explanations
    risks = score_result.get("risks") or []
    detailed_risks = analyze_risks_detailed(risks, language=language) if comprehensive else []
    
    # Build reports
    if comprehensive:
        comprehensive_report = build_comprehensive_report(
            score_result, 
            detailed_risks, 
            address=address, 
            language=language
        )
        report = comprehensive_report
    else:
        report = build_report_text(score_result, language=language, address=address)
    
    consult = build_consult_text(score_result, language=language, address=address)
    
    # Base response (user-friendly, concise)
    result = {
        "report": report,
        "comprehensive_report": comprehensive_report if comprehensive else None,
        "risks": risks,
        "detailed_risks": detailed_risks if comprehensive else None,
        "opportunities": score_result.get("pros") or [],
        "guardian_score": score_result.get("guardian_score"),
        "consult": consult,
        "score_breakdown": score_result.get("score_breakdown"),
        "status": score_result.get("status"),
        "status_note": score_result.get("status_note"),
        "language": language,
        # Summary environmental data (user-friendly)
        "noise_data": {
            "noise_day_db": noise_data.get("noise_day_db"),
            "noise_night_db": noise_data.get("noise_night_db"),
            "assessment": noise_data.get("assessment"),
            "features_found": noise_data.get("features_found"),
            "note": noise_data.get("note"),
        } if noise_data else None,
        "tama_data": {
            "in_building": tama_data.get("in_building"),
            "adjacent": tama_data.get("adjacent"),
            "neighborhood": tama_data.get("neighborhood"),
            "count": tama_data.get("count", 0),
            "note": tama_data.get("note"),
        } if tama_data else None,
        "transport_data": {
            "metro_nearby": transport_data.get("metro_nearby"),
            "railway_nearby": transport_data.get("railway_nearby"),
            "count": transport_data.get("count", 0),
            "note": transport_data.get("note"),
        } if transport_data else None,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "note": "Enhanced Guardian Score with comprehensive risk analysis. Use include_raw_data=True for full API transparency.",
    }
    
    # Optional: Add full raw data only if explicitly requested
    if include_raw_data:
        result["raw_api_data"] = {
            "cadastral_full": cadastral,  # Complete cadastral response
            "multi_radius_full": multi_radius,  # Complete multi-radius response with all plans/permits
            "noise_full": noise_data,  # Complete noise query response
            "tama_full": tama_data,  # Complete TAMA query response
            "transport_full": transport_data,  # Complete transport query response
        }
        result["note"] = "Enhanced Guardian Score with FULL API transparency (raw_api_data included)."
    
    return result


@mcp.tool()
def generate_guardian_report(
    latitude: float,
    longitude: float,
    address: str | None = None,
    language: str = "en",
    comprehensive: bool = True,
    include_raw_data: bool = False,
) -> dict:
    """
    Phase 3 — Urban Intelligence: Synthesize cadastral + planning data into a comprehensive advisory report.

    ENHANCED VERSION: Automatically analyzes risks and provides detailed explanations.

    Uses geocode_address, get_cadastral_data, and get_urban_plans (or pre-fetched data) to produce
    a plain-language report with detailed risk analysis, timelines, and actionable recommendations.

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        address: Optional display address (e.g. for report header).
        language: Report language: "en" (English) or "he" (Hebrew). Default "en".
        comprehensive: If True, includes detailed risk analysis and formatted report. Default True.
        include_raw_data: If True, includes raw_api_data with complete GovMap responses. Default False.
            When False: User-friendly concise output (~3-5 KB)
            When True: Full transparency with all raw data (~180 KB, 13K lines)

    Returns:
        A dict with:
        - report: Comprehensive formatted report with all details
        - comprehensive_report: Full formatted text report
        - detailed_risks: Auto-analyzed risks with explanations and recommendations
        - risks: List of risk descriptions
        - opportunities: List of advantages
        - guardian_score: Score 0-100
        - score_breakdown: Detailed point breakdown
        - consult: Advisory text
        - noise_data, tama_data, transport_data: Summary environmental data
        - coordinates: Location coordinates
        - raw_api_data (only if include_raw_data=True): Complete raw API responses including:
            - cadastral_full: Complete cadastral query response
            - multi_radius_full: Complete multi-radius response with ALL plans/permits
            - noise_full: Complete noise data with all raw features
            - tama_full: Complete TAMA data with all projects and attributes
            - transport_full: Complete transport data with all features
    """
    return _generate_guardian_report_impl(latitude, longitude, address, language, comprehensive, include_raw_data)


@mcp.tool()
def get_plan_details(
    plan_number: str, 
    language: str = "he",
    coordinates: tuple[float, float] | None = None,
) -> dict:
    """
    Get detailed information about a specific urban planning plan.
    
    ENHANCED VERSION: Includes MAVAT links, timeline estimation, and comprehensive analysis.
    
    This tool provides comprehensive details about what a specific plan means,
    including risk assessment, expected timeline, MAVAT link, and actionable recommendations.
    
    **Feature Enhancement #1** (COMPLETED) from FEATURE_ROADMAP.md
    
    Args:
        plan_number: Plan number as shown in the Guardian report (e.g., "25047", "ג/1234")
        language: Response language - "he" (Hebrew, default) or "en" (English)
        coordinates: Optional (lat, lon) tuple to improve search accuracy
    
    Returns:
        Dict with:
        - plan_number, name, status
        - zoning (land use type)
        - risk_level (high/medium/low/positive)
        - explanation (what this means for you)
        - timeline (estimated start and duration)
        - mavat_url (direct link to official MAVAT page)
        - impact_assessment (points, duration, noise level)
        - recommendations (what to do next)
        - raw_attributes (full GovMap data)
    
    Example:
        plan_details = get_plan_details("25047", language="he", coordinates=(31.78, 34.64))
        # Returns: Comprehensive info about plan 25047, including:
        # - That it's a road plan (שטח לדרכים)
        # - Risk level: HIGH
        # - Expected construction: 18-36 months
        # - Direct MAVAT link
        # - Detailed recommendations
    """
    # Get enhanced plan info from GovMap with MAVAT links and timeline
    plan_info = get_detailed_plan_info(plan_number, language=language, coordinates=coordinates)
    
    if "error" in plan_info:
        return plan_info
    
    # Plan info already includes comprehensive analysis
    # (risk_analysis, timeline, MAVAT URL are integrated in get_detailed_plan_info)
    
    return plan_info


if __name__ == "__main__":
    """Run the MCP server when executed with `uv run server.py` or `python server.py`."""
    mcp.run()
