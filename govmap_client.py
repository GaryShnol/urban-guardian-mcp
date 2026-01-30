"""
GovMap address search client for Urban Guardian.

Official GovMap geocode API is documented at:
  https://www.govmap.gov.il/sites/api/index.html  (geocode: keyword + type)
That API is iframe/embed-only (JavaScript). No public REST geocode URL is documented;
the map app uses an internal search-service. This client uses a configurable
GOVMAP_SEARCH_URL; set it when a working REST endpoint is available.
When GovMap is unavailable or returns non-JSON (e.g. HTML), falls back to
OpenStreetMap Nominatim restricted to Israel (countrycodes=il).
Validates and cleans input, returns WGS84 coordinates or raises AddressNotFoundError
with optional "did you mean?" suggestions.
"""

import os
import re
from urllib.parse import quote

import httpx

# Israel approximate bbox (WGS84) for validation
ISRAEL_LAT_MIN, ISRAEL_LAT_MAX = 29.45, 33.28
ISRAEL_LON_MIN, ISRAEL_LON_MAX = 34.17, 35.69

# HTTP client timeout (seconds)
DEFAULT_TIMEOUT = 15.0

# No public REST geocode URL documented; see https://www.govmap.gov.il/sites/api/index.html
DEFAULT_GOVMAP_SEARCH_URL = "https://www.govmap.gov.il/Searching/SearchRest.ashx"

# Fallback when GovMap returns non-JSON or no results (Nominatim usage policy: identify app)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "UrbanGuardianMCP/1.0 (Israeli address geocode; fallback when GovMap unavailable)"


class AddressNotFoundError(Exception):
    """Raised when the address was not found. Optional suggestions for 'did you mean?'."""

    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


def clean_address(address: str) -> str:
    """Normalize address: strip, collapse whitespace, normalize commas."""
    if not address or not isinstance(address, str):
        return ""
    s = address.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*,\s*", ",", s).strip()
    return s


def validate_coordinates_in_israel(lat: float, lon: float) -> bool:
    """Return True if (lat, lon) is inside Israel bbox (WGS84)."""
    return (
        ISRAEL_LAT_MIN <= lat <= ISRAEL_LAT_MAX
        and ISRAEL_LON_MIN <= lon <= ISRAEL_LON_MAX
    )


def _parse_one_result(r: dict) -> dict | None:
    """Extract WGS84 lat/lon and display_name from one result. Returns None if invalid."""
    if not isinstance(r, dict):
        return None
    lat = r.get("latitude") or r.get("lat") or r.get("y")
    lon = r.get("longitude") or r.get("lon") or r.get("x")
    geom = r.get("geometry") if isinstance(r.get("geometry"), dict) else None
    if geom and isinstance(geom.get("coordinates"), (list, tuple)) and len(geom["coordinates"]) >= 2:
        lon, lat = geom["coordinates"][0], geom["coordinates"][1]
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if abs(lat_f) > 90 or abs(lon_f) > 180:
        return None
    if not (
        ISRAEL_LAT_MIN <= lat_f <= ISRAEL_LAT_MAX
        and ISRAEL_LON_MIN <= lon_f <= ISRAEL_LON_MAX
    ):
        return None
    props = r.get("properties") or {}
    display = (
        r.get("display_name") or r.get("address") or r.get("label") or r.get("name")
        or props.get("display_name") or props.get("name") or props.get("address")
    )
    return {"latitude": lat_f, "longitude": lon_f, "display_name": display}


def _parse_govmap_response(data: dict) -> tuple[list[dict], list[str]]:
    """
    Parse GovMap search response into list of results and optional suggestions.
    Supports dict results, GeoJSON FeatureCollection, and common API shapes.
    """
    results: list[dict] = []
    suggestions: list[str] = []

    if not isinstance(data, dict):
        return results, suggestions

    if data.get("type") == "FeatureCollection" and isinstance(data.get("features"), list):
        for f in data["features"]:
            if isinstance(f, dict) and f.get("type") == "Feature":
                one = _parse_one_result(f)
                if one:
                    results.append(one)
    else:
        raw_results = (
            data.get("results")
            or data.get("data")
            or data.get("items")
            or data.get("SearchResults")
            or data.get("list")
        )
        if isinstance(raw_results, list):
            for r in raw_results:
                one = _parse_one_result(r)
                if one:
                    results.append(one)

    # Suggestions when no exact match
    raw_suggestions = data.get("suggestions") or data.get("alternatives") or data.get("Suggestions")
    if isinstance(raw_suggestions, list):
        for s in raw_suggestions:
            if isinstance(s, str) and s.strip():
                suggestions.append(s.strip())
            elif isinstance(s, dict) and (s.get("text") or s.get("label") or s.get("address")):
                suggestions.append(
                    (s.get("text") or s.get("label") or s.get("address") or "").strip()
                )

    return results, suggestions


def _geocode_via_nominatim(address: str) -> dict | None:
    """
    Geocode an Israeli address via OpenStreetMap Nominatim (countrycodes=il).
    Returns result dict with latitude, longitude, display_name or None if not found.
    Respects Nominatim usage policy (User-Agent, 1 req/sec is caller's responsibility).
    """
    if not address or not address.strip():
        return None
    params = {
        "q": address.strip(),
        "format": "json",
        "limit": 1,
        "countrycodes": "il",
    }
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(NOMINATIM_URL, params=params, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or len(data) == 0:
        return None
    item = data[0]
    if not isinstance(item, dict):
        return None
    lat = item.get("lat")
    lon = item.get("lon")
    display = item.get("display_name")
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (
        ISRAEL_LAT_MIN <= lat_f <= ISRAEL_LAT_MAX
        and ISRAEL_LON_MIN <= lon_f <= ISRAEL_LON_MAX
    ):
        return None
    return {
        "latitude": lat_f,
        "longitude": lon_f,
        "display_name": display,
    }


def search_address(address: str) -> dict:
    """
    Geocode an Israeli address via GovMap. Returns WGS84 coordinates.
    When GovMap is unavailable or returns non-JSON (e.g. HTML), falls back to
    OpenStreetMap Nominatim (Israel only).

    Args:
        address: Full or partial address (e.g. "דיזנגוף 100,תל אביב").

    Returns:
        Dict with keys: latitude, longitude, display_name (optional).
        May include "source": "nominatim" when fallback was used.

    Raises:
        AddressNotFoundError: When address is not found, with optional suggestions
            for "did you mean?" (message and suggestions attribute).
    """
    cleaned = clean_address(address)
    if not cleaned:
        raise AddressNotFoundError("Address is empty.", suggestions=[])

    base_url = os.environ.get("GOVMAP_SEARCH_URL", DEFAULT_GOVMAP_SEARCH_URL).rstrip("/?&")
    encoded_query = quote(cleaned, safe="")
    sep = "&" if "?" in base_url else "?"
    url = f"{base_url}{sep}query={encoded_query}"

    govmap_failed_reason: str | None = None
    results: list[dict] = []
    suggestions: list[str] = []

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        govmap_failed_reason = str(e)
    else:
        try:
            data = resp.json()
        except Exception as e:
            govmap_failed_reason = f"invalid response: {e!s}"
        else:
            results, suggestions = _parse_govmap_response(data)

    # GovMap returned valid JSON with at least one result
    if results:
        first = results[0]
        return {
            "latitude": first["latitude"],
            "longitude": first["longitude"],
            "display_name": first.get("display_name"),
        }

    # Fallback to Nominatim when GovMap unavailable or no results
    fallback = _geocode_via_nominatim(cleaned)
    if fallback is not None:
        fallback["source"] = "nominatim"
        return fallback

    # Neither GovMap nor Nominatim found the address
    if govmap_failed_reason:
        msg = (
            f"GovMap unavailable ({govmap_failed_reason}) and Nominatim did not find the address."
        )
    else:
        msg = "Address could not be found."
        if suggestions:
            msg += " Did you mean: " + "; ".join(suggestions[:5]) + "?"
    raise AddressNotFoundError(msg, suggestions=suggestions)
