"""
Pytest tests for REST API (FastAPI) — used for Postman parity.

Covers: health, geocode_address, get_cadastral_data, get_urban_plans, generate_guardian_report.
"""

import pytest
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def test_api_health():
    """GET /health returns 200 and status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert "urban-guardian" in data.get("service", "")


def test_api_geocode_address_missing_body():
    """POST /geocode_address with missing address returns 400."""
    resp = client.post("/geocode_address", json={})
    assert resp.status_code == 400
    resp = client.post("/geocode_address", json={"address": ""})
    assert resp.status_code == 400


def test_api_geocode_address_success():
    """POST /geocode_address with valid address returns lat/lon or error (no mock)."""
    resp = client.post("/geocode_address", json={"address": "22 HaNeviim Jerusalem Israel"})
    # May return 200 with coords (if GovMap/Nominatim used) or 200 with error (GovMap returns HTML)
    assert resp.status_code == 200
    data = resp.json()
    assert "latitude" in data or "error" in data
    if "latitude" in data:
        assert "longitude" in data
        assert isinstance(data["latitude"], (int, float))
        assert isinstance(data["longitude"], (int, float))


def test_api_get_cadastral_data():
    """POST /get_cadastral_data returns gush, helka, note."""
    resp = client.post(
        "/get_cadastral_data",
        json={"latitude": 31.784, "longitude": 35.221},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "gush" in data and "helka" in data and "note" in data


def test_api_get_cadastral_data_invalid_body():
    """POST /get_cadastral_data with missing lat/lon returns 400."""
    resp = client.post("/get_cadastral_data", json={})
    assert resp.status_code == 400


def test_api_get_urban_plans():
    """POST /get_urban_plans returns plans, permits, note."""
    resp = client.post(
        "/get_urban_plans",
        json={"latitude": 31.784, "longitude": 35.221},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "plans" in data and "permits" in data and "note" in data
    assert isinstance(data["plans"], list)
    assert isinstance(data["permits"], list)


def test_api_get_urban_plans_invalid_body():
    """POST /get_urban_plans with invalid body returns 400."""
    resp = client.post("/get_urban_plans", json={"lat": "invalid"})
    assert resp.status_code == 400


def test_api_get_spatial_mining():
    """POST /get_spatial_mining returns within_100m, within_500m, within_1000m, note."""
    resp = client.post(
        "/get_spatial_mining",
        json={"latitude": 31.784, "longitude": 35.221},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "within_100m" in data and "within_500m" in data and "within_1000m" in data
    assert "note" in data
    assert "plans" in data["within_100m"] and "permits" in data["within_100m"]


def test_api_get_spatial_mining_invalid_body():
    """POST /get_spatial_mining with missing lat/lon returns 400."""
    resp = client.post("/get_spatial_mining", json={})
    assert resp.status_code == 400


def test_api_get_multi_radius_search():
    """POST /get_multi_radius_search returns bedroom_50m, permits_100m, ..., summary, note."""
    resp = client.post(
        "/get_multi_radius_search",
        json={"latitude": 31.784, "longitude": 35.221},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "bedroom_50m" in data and "permits_100m" in data and "value_800m" in data
    assert "summary" in data and "note" in data
    assert "plans" in data["bedroom_50m"] and "permits" in data["bedroom_50m"]


def test_api_get_multi_radius_search_invalid_body():
    """POST /get_multi_radius_search with missing lat/lon returns 400."""
    resp = client.post("/get_multi_radius_search", json={})
    assert resp.status_code == 400


def test_api_generate_guardian_report():
    """POST /generate_guardian_report returns report, risks, opportunities, guardian_score, consult, language."""
    resp = client.post(
        "/generate_guardian_report",
        json={
            "latitude": 31.784,
            "longitude": 35.221,
            "address": "22 HaNevi'im St, Jerusalem",
            "language": "en",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "report" in data and "risks" in data and "opportunities" in data and "language" in data
    assert "guardian_score" in data and "consult" in data
    assert data["language"] == "en"
    assert data["report"] is not None
    assert data["guardian_score"] is None or 0 <= data["guardian_score"] <= 100


def test_api_generate_guardian_report_language_he():
    """POST /generate_guardian_report with language he returns Hebrew."""
    resp = client.post(
        "/generate_guardian_report",
        json={"latitude": 31.784, "longitude": 35.221, "language": "he"},
    )
    assert resp.status_code == 200
    assert resp.json().get("language") == "he"


def test_api_generate_guardian_report_invalid_body():
    """POST /generate_guardian_report with missing lat/lon returns 400."""
    resp = client.post("/generate_guardian_report", json={})
    assert resp.status_code == 400
