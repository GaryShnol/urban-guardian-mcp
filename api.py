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


@app.post("/generate_guardian_report")
def generate_guardian_report(body: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 3 — Generate risk/opportunity report at WGS84 coordinates.
    Body: {"latitude": 31.784, "longitude": 35.221, "address": "22 HaNevi'im St, Jerusalem", "language": "en"}
    """
    lat, lon = _parse_lat_lon(body)
    address = body.get("address")
    language = body.get("language", "en")
    if language not in ("en", "he"):
        language = "en"
    return _generate_guardian_report_impl(lat, lon, address=address, language=language)


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
