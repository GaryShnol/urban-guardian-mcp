"""
Integration tests: real API connections only (no mocks).

Verifies real connectivity to:
- GovMap search-service getTypes (JSON)
- GovMap default URL (reachable; may return HTML — tests skip when so)
- Nominatim (OSM) geocoding for Israeli addresses when GovMap geocode is not available

Run: pytest tests/test_integration_real_api.py -v
Run unit-only (exclude integration): pytest -m "not integration" -v
"""

import pytest
import httpx

from govmap_client import (
    DEFAULT_GOVMAP_SEARCH_URL,
    validate_coordinates_in_israel,
    search_address,
    AddressNotFoundError,
)


# Base URL for GovMap API (search-service)
GOVMAP_API_BASE = "https://www.govmap.gov.il/api"
GOVMAP_SEARCH_SERVICE_GETTYPES = f"{GOVMAP_API_BASE}/search-service/getTypes"

# Nominatim (OpenStreetMap) — real geocoding API; supports Israel, no key required
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def _govmap_default_url_returns_json() -> bool:
    """Probe GovMap default geocode URL; return True if it returns JSON."""
    url = f"{DEFAULT_GOVMAP_SEARCH_URL.rstrip('/?&')}?query=22+HaNeviim+Jerusalem"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
    except Exception:
        return False
    ct = (resp.headers.get("content-type") or "").lower()
    body = (resp.text or "").strip()[:100]
    return "json" in ct or body.startswith("{") or body.startswith("[")


# --- Real GovMap search-service (we know this endpoint works) ---


@pytest.mark.integration
def test_real_govmap_search_service_gettypes_returns_200_and_json():
    """Real API: POST GovMap search-service getTypes returns 200 and JSON array of search types."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            GOVMAP_SEARCH_SERVICE_GETTYPES,
            json={"language": "he"},
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 200, f"GovMap getTypes returned {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert isinstance(data, list), f"Expected JSON array, got {type(data)}"
    assert len(data) > 0, "Expected at least one search type"
    # Should contain address/street types
    types = [item.get("type") for item in data if isinstance(item, dict)]
    assert "address" in types or "street" in types or "settlement" in types, (
        f"Expected address/street/settlement in types: {types}"
    )


# --- Real GovMap geocode endpoint (default URL) ---


@pytest.mark.integration
def test_real_govmap_default_geocode_url_reachable():
    """Real API: GET GovMap default geocode URL returns 200 (connection works)."""
    url = f"{DEFAULT_GOVMAP_SEARCH_URL.rstrip('/?&')}?query=22+HaNeviim+Jerusalem"
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url)
    assert resp.status_code == 200, f"GovMap geocode URL returned {resp.status_code}"


@pytest.mark.integration
def test_real_govmap_default_geocode_url_response_content_type():
    """Real API: GovMap default URL returns JSON when set as geocode endpoint; skip if it returns HTML."""
    if not _govmap_default_url_returns_json():
        pytest.skip(
            "GovMap default URL returns HTML, not JSON (no public REST geocode endpoint). "
            "Set GOVMAP_SEARCH_URL to a working geocode endpoint to run this test."
        )


# --- Real geocode: Nominatim (OSM) — no mock, real API ---


@pytest.mark.integration
def test_real_nominatim_geocode_jerusalem():
    """Real API: geocode Israeli address via Nominatim (OSM); no mocks; verify coords in Israel."""
    query = "22 HaNeviim Jerusalem Israel"
    params = {"q": query, "format": "json", "limit": 1}
    headers = {"User-Agent": "UrbanGuardianMCP/1.0 (integration test; no mock)"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(NOMINATIM_URL, params=params, headers=headers)
    assert resp.status_code == 200, f"Nominatim returned {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert isinstance(data, list) and len(data) >= 1, f"Expected non-empty list: {data!r}"
    first = data[0]
    lat = float(first["lat"])
    lon = float(first["lon"])
    assert validate_coordinates_in_israel(lat, lon), f"Coords ({lat}, {lon}) outside Israel bbox"
    # Jerusalem area
    assert 31.5 <= lat <= 32.0 and 34.9 <= lon <= 35.5


@pytest.mark.integration
def test_real_nominatim_geocode_tel_aviv():
    """Real API: geocode Tel Aviv via Nominatim; no mocks."""
    params = {"q": "Dizengoff 100, Tel Aviv, Israel", "format": "json", "limit": 1}
    headers = {"User-Agent": "UrbanGuardianMCP/1.0 (integration test)"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(NOMINATIM_URL, params=params, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) >= 1
    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
    assert validate_coordinates_in_israel(lat, lon)
    assert 32.0 <= lat <= 32.2 and 34.7 <= lon <= 34.9


# --- Real geocode flow via GovMap (no mocks): skip when default URL returns HTML ---


@pytest.mark.integration
def test_real_geocode_address_22_haneviim_jerusalem():
    """Real API: geocode '22 HaNevi'im St, Jerusalem' via GovMap when endpoint returns JSON (no mocks)."""
    if not _govmap_default_url_returns_json():
        pytest.skip(
            "GovMap default URL returns HTML. Set GOVMAP_SEARCH_URL to a working endpoint to run."
        )
    address = "22 HaNevi'im St, Jerusalem"
    result = search_address(address)
    assert "latitude" in result and "longitude" in result
    lat, lon = result["latitude"], result["longitude"]
    assert isinstance(lat, (int, float)) and isinstance(lon, (int, float))
    assert validate_coordinates_in_israel(lat, lon), f"Coords ({lat}, {lon}) outside Israel bbox"
    assert 31.5 <= lat <= 32.0 and 34.9 <= lon <= 35.5


@pytest.mark.integration
def test_real_geocode_address_hebrew():
    """Real API: geocode Hebrew address via GovMap when endpoint returns JSON (no mocks)."""
    if not _govmap_default_url_returns_json():
        pytest.skip(
            "GovMap default URL returns HTML. Set GOVMAP_SEARCH_URL to a working endpoint to run."
        )
    address = "דיזנגוף 100, תל אביב"
    result = search_address(address)
    assert "latitude" in result and "longitude" in result
    lat, lon = result["latitude"], result["longitude"]
    assert validate_coordinates_in_israel(lat, lon)
    assert 32.0 <= lat <= 32.2 and 34.7 <= lon <= 34.9


# --- Full E2E with real geocode (no mocks); cadastral/plans still stubs ---


@pytest.mark.integration
def test_real_e2e_nominatim_geocode_then_cadastral_plans_report():
    """Real API: E2E with real geocode via Nominatim; cadastral/plans/report use current impl (no mocks)."""
    from server import (
        _get_cadastral_data_impl,
        _get_urban_plans_impl,
        _generate_guardian_report_impl,
    )
    # Step 1: real geocode via Nominatim (no mock)
    params = {"q": "22 HaNeviim Jerusalem Israel", "format": "json", "limit": 1}
    headers = {"User-Agent": "UrbanGuardianMCP/1.0 (E2E integration test)"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(NOMINATIM_URL, params=params, headers=headers)
    assert resp.status_code == 200, f"Nominatim failed: {resp.status_code}"
    data = resp.json()
    assert isinstance(data, list) and len(data) >= 1
    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
    assert validate_coordinates_in_israel(lat, lon)
    address = "22 HaNevi'im St, Jerusalem"
    # Step 2–4: current impl (stub or real when implemented)
    cadastral = _get_cadastral_data_impl(lat, lon)
    plans = _get_urban_plans_impl(lat, lon)
    report = _generate_guardian_report_impl(lat, lon, address=address, language="en")
    assert "gush" in cadastral and "helka" in cadastral
    assert "plans" in plans and "permits" in plans
    assert "risks" in report and "opportunities" in report and report["language"] == "en"


@pytest.mark.integration
def test_real_e2e_geocode_then_cadastral_then_plans_then_report():
    """Real API: E2E flow using GovMap geocode when endpoint returns JSON; else skip."""
    if not _govmap_default_url_returns_json():
        pytest.skip(
            "GovMap default URL returns HTML. Set GOVMAP_SEARCH_URL to a working endpoint to run."
        )
    from server import (
        _geocode_address_impl,
        _get_cadastral_data_impl,
        _get_urban_plans_impl,
        _generate_guardian_report_impl,
    )
    address = "22 HaNevi'im St, Jerusalem"
    geocode_result = _geocode_address_impl(address)
    if "error" in geocode_result:
        pytest.fail(f"Real E2E step 1 (geocode) failed: {geocode_result.get('error')}")
    lat = geocode_result["latitude"]
    lon = geocode_result["longitude"]
    assert validate_coordinates_in_israel(lat, lon)
    cadastral = _get_cadastral_data_impl(lat, lon)
    plans = _get_urban_plans_impl(lat, lon)
    report = _generate_guardian_report_impl(lat, lon, address=address, language="en")
    assert "gush" in cadastral and "helka" in cadastral
    assert "plans" in plans and "permits" in plans
    assert "risks" in report and "opportunities" in report and report["language"] == "en"
