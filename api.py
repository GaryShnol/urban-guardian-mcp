"""
REST API for Urban Guardian — used for Postman/manual testing.

Exposes the same four operations as the MCP server via HTTP JSON.
Run: uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from server import (
    _geocode_address_impl,
    _generate_guardian_report_impl,
    _get_cadastral_data_impl,
    _get_multi_radius_search_impl,
    _get_spatial_mining_impl,
    _get_urban_plans_impl,
)

app = FastAPI(
    title="Urban Guardian API",
    description="REST API for Israeli real estate insights (geocode, cadastral, planning, report).",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for load balancers and Postman."""
    return {"status": "ok", "service": "urban-guardian"}


@app.post("/geocode_address")
def geocode_address(body: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 1 — Geocode an Israeli address to WGS84 (lat, lon).
    Body: {"address": "22 HaNevi'im St, Jerusalem"}
    """
    address = body.get("address")
    if address is None or (isinstance(address, str) and not address.strip()):
        raise HTTPException(status_code=400, detail="Missing or empty 'address'")
    if not isinstance(address, str):
        raise HTTPException(status_code=400, detail="'address' must be a string")
    return _geocode_address_impl(address.strip())


@app.post("/get_cadastral_data")
def get_cadastral_data(body: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 2 — Get block (gush) and parcel (helka) at WGS84 coordinates.
    Body: {"latitude": 31.784, "longitude": 35.221}
    """
    lat, lon = _parse_lat_lon(body)
    return _get_cadastral_data_impl(lat, lon)


@app.post("/get_urban_plans")
def get_urban_plans(body: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 2 — Get zoning and building permits at WGS84 coordinates.
    Body: {"latitude": 31.784, "longitude": 35.221}
    """
    lat, lon = _parse_lat_lon(body)
    return _get_urban_plans_impl(lat, lon)


@app.post("/get_spatial_mining")
def get_spatial_mining(body: dict[str, Any]) -> dict[str, Any]:
    """
    Station 3 — Spatial data mining: plans/permits at 100m, 500m, 1000m radii.
    Body: {"latitude": 31.784, "longitude": 35.221}
    Optional: radius_permits_m, radius_plans_m, radius_infrastructure_m (defaults 100, 500, 1000).
    """
    lat, lon = _parse_lat_lon(body)
    r_permits = body.get("radius_permits_m")
    r_plans = body.get("radius_plans_m")
    r_infra = body.get("radius_infrastructure_m")
    kwargs = {}
    if r_permits is not None:
        kwargs["radius_permits_m"] = float(r_permits)
    if r_plans is not None:
        kwargs["radius_plans_m"] = float(r_plans)
    if r_infra is not None:
        kwargs["radius_infrastructure_m"] = float(r_infra)
    return _get_spatial_mining_impl(lat, lon, **kwargs)


@app.post("/get_multi_radius_search")
def get_multi_radius_search(body: dict[str, Any]) -> dict[str, Any]:
    """
    Multi-Radius Search: layer-based radii (bedroom 50m, permits 100m, lifestyle 300m, plans 500m, value 800m).
    Body: {"latitude": 31.784, "longitude": 35.221}
    Returns plans/permits per circle and summary flags for the Brain.
    """
    lat, lon = _parse_lat_lon(body)
    return _get_multi_radius_search_impl(lat, lon)


@app.post("/generate_guardian_report")
def generate_guardian_report(body: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 3 — Generate risk/opportunity report at WGS84 coordinates.
    Body: {
        "latitude": 31.784, 
        "longitude": 35.221, 
        "address": "22 HaNevi'im St, Jerusalem", 
        "language": "en",
        "include_raw_data": false  // Optional: set true for full API transparency (180 KB vs 3-5 KB)
    }
    """
    lat, lon = _parse_lat_lon(body)
    address = body.get("address")
    language = body.get("language", "en")
    if language not in ("en", "he"):
        language = "en"
    include_raw_data = body.get("include_raw_data", False)
    if not isinstance(include_raw_data, bool):
        include_raw_data = False
    return _generate_guardian_report_impl(lat, lon, address=address, language=language, include_raw_data=include_raw_data)


def _parse_lat_lon(body: dict[str, Any]) -> tuple[float, float]:
    """Extract and validate latitude/longitude from request body."""
    try:
        lat = float(body.get("latitude", body.get("lat")))
        lon = float(body.get("longitude", body.get("lon")))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid 'latitude' and 'longitude' (WGS84 numbers)",
        )
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Latitude/longitude out of valid range")
    return lat, lon
