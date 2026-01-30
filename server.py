"""
Urban Guardian (Israel) — MCP Server

Model Context Protocol server for real-time urban planning, construction
permits, and real estate insights by address in Israel.

Technical flow: geocode_address → get_cadastral_data → get_urban_plans → generate_guardian_report
Phase 1: Geographic Foundation (geocode_address) — GovMap
Phase 2: Cadastral & Planning (get_cadastral_data, get_urban_plans) — GovMap + ArcGIS
Phase 3: Urban Intelligence (generate_guardian_report) — AI synthesis
Phase 4: Environmental & Infrastructure — planned
"""

from __future__ import annotations

from fastmcp import FastMCP

from govmap_client import AddressNotFoundError, search_address

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
    # TODO: Phase 2 — GovMap Cadastral Layers (גוש/חלקה)
    return {
        "gush": None,
        "helka": None,
        "note": "GovMap cadastral integration not yet implemented; returning stub.",
    }


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
    # TODO: Phase 2 — ArcGIS Planning Server point-in-polygon
    return {
        "plans": [],
        "permits": [],
        "note": "ArcGIS Planning Server integration not yet implemented; returning stub.",
    }


@mcp.tool()
def get_urban_plans(latitude: float, longitude: float) -> dict:
    """
    Phase 2 — Planning: Get zoning (תב"ע) and building permits at the given WGS84 coordinates.

    Data source: ArcGIS Planning Server (ags.teun.co.il). Point-in-polygon for active/pending
    plans and permits (active, approved, or pending); status e.g. "In Deposit" (בהפקדה), "Valid".

    Args:
        latitude: WGS84 latitude (e.g. 32.065).
        longitude: WGS84 longitude (e.g. 34.773).

    Returns:
        A dict with lists of plans and permits (or empty lists), plus status and metadata.
    """
    return _get_urban_plans_impl(latitude, longitude)


def _generate_guardian_report_impl(
    latitude: float,
    longitude: float,
    address: str | None = None,
    language: str = "en",
) -> dict:
    """Implementation of generate_guardian_report (used by tool and tests)."""
    # TODO: Phase 3 — AI synthesis from cadastral + urban_plans
    return {
        "report": None,
        "risks": [],
        "opportunities": [],
        "language": language,
        "note": "generate_guardian_report not yet implemented; returning stub.",
    }


@mcp.tool()
def generate_guardian_report(
    latitude: float,
    longitude: float,
    address: str | None = None,
    language: str = "en",
) -> dict:
    """
    Phase 3 — Urban Intelligence: Synthesize cadastral + planning data into a bilingual advisory report.

    Uses geocode_address, get_cadastral_data, and get_urban_plans (or pre-fetched data) to produce
    a plain-language report: risks (noise, dust, blocked views) and opportunities (TAMA 38, value).

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        address: Optional display address (e.g. for report header).
        language: Report language: "en" (English) or "he" (Hebrew). Default "en".

    Returns:
        A dict with report text (bilingual if requested), risks, and opportunities.
    """
    return _generate_guardian_report_impl(latitude, longitude, address, language)


if __name__ == "__main__":
    """Run the MCP server when executed with `uv run server.py` or `python server.py`."""
    mcp.run()
