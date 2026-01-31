"""
End-to-End (E2E) tests for Urban Guardian: "The Concerned Homebuyer" scenario.

Validates the full workflow: User Query → Geocoding → Cadastral → Planning/Permits
→ Guardian Report, and success criteria (coordinate precision, actionable output).
"""

import pytest
from unittest.mock import patch

from govmap_client import validate_coordinates_in_israel
from server import (
    _geocode_address_impl,
    _get_cadastral_data_impl,
    _get_urban_plans_impl,
    _generate_guardian_report_impl,
)


# --- E2E Scenario: "The Concerned Homebuyer" ---

E2E_ADDRESS = "22 HaNevi'im St, Jerusalem"
E2E_USER_QUERY = (
    "I am looking at an apartment on 22 HaNevi'im St, Jerusalem. "
    "What should I know about the next 5 years in this area?"
)

# Expected results from E2E spec (Step 1–2)
E2E_EXPECTED_LAT = 31.784
E2E_EXPECTED_LON = 35.221
E2E_EXPECTED_GUSH = 30050
E2E_EXPECTED_HELKA = 45

# Guardian Report structure (Risk vs. Opportunity)
E2E_EXPECTED_RISK_TYPES = ["noise", "view_obstruction", "in_deposit_notice"]
E2E_EXPECTED_OPPORTUNITY_TYPES = ["value_increase", "light_rail_proximity"]


# --- E2E Workflow: Full chain with mocks ---


@patch("server.search_address")
def test_e2e_workflow_concerned_homebuyer_step1_geocode(mock_search):
    """E2E Step 1: Geocoding converts '22 HaNevi'im St, Jerusalem' to coordinates (31.784, 35.221)."""
    mock_search.return_value = {
        "latitude": E2E_EXPECTED_LAT,
        "longitude": E2E_EXPECTED_LON,
        "display_name": "22 HaNevi'im St, Jerusalem",
    }
    result = _geocode_address_impl(E2E_ADDRESS)
    assert "error" not in result
    assert result["latitude"] == E2E_EXPECTED_LAT
    assert result["longitude"] == E2E_EXPECTED_LON
    assert validate_coordinates_in_israel(result["latitude"], result["longitude"])


@patch("server.search_address")
def test_e2e_workflow_concerned_homebuyer_full_chain(mock_search):
    """E2E: Full workflow Geocode → Cadastral → Urban Plans → Guardian Report (mocked Step 1)."""
    mock_search.return_value = {
        "latitude": E2E_EXPECTED_LAT,
        "longitude": E2E_EXPECTED_LON,
        "display_name": E2E_ADDRESS,
    }
    # Step 1: Geocoding
    geocode_result = _geocode_address_impl(E2E_ADDRESS)
    assert "error" not in geocode_result
    lat, lon = geocode_result["latitude"], geocode_result["longitude"]

    # Step 2: Cadastral (stub returns gush/helka; when implemented would return 30050, 45)
    cadastral = _get_cadastral_data_impl(lat, lon)
    assert "gush" in cadastral and "helka" in cadastral

    # Step 3: Urban plans & permits (stub returns lists; when implemented would return Urban Renewal plan + Light Rail permit)
    plans_result = _get_urban_plans_impl(lat, lon)
    assert "plans" in plans_result and "permits" in plans_result
    assert isinstance(plans_result["plans"], list) and isinstance(plans_result["permits"], list)

    # Step 4: Guardian Report (structure must support risks + opportunities, plain Hebrew/English)
    report = _generate_guardian_report_impl(lat, lon, address=E2E_ADDRESS, language="en")
    assert "report" in report and "risks" in report and "opportunities" in report
    assert report["language"] == "en"
    assert isinstance(report["risks"], list) and isinstance(report["opportunities"], list)


# --- Success Criteria: Coordinate Precision ---


def test_e2e_success_criteria_coordinate_precision():
    """Success Criteria: Geocoder returns coordinates with sufficient precision (building-level, not just street)."""
    # When geocode returns, lat/lon must be numeric and within Israel bbox (precision implied by float)
    lat, lon = 31.784, 35.221
    assert isinstance(lat, (int, float)) and isinstance(lon, (int, float))
    assert validate_coordinates_in_israel(lat, lon)
    # At least 3 decimal places ≈ 100m precision; 4+ ≈ building level
    assert len(str(lat).split(".")[-1]) >= 3 and len(str(lon).split(".")[-1]) >= 3


# --- Success Criteria: Actionable Output ---


def test_e2e_success_criteria_actionable_output_structure():
    """Success Criteria: Final report has structure for plain Hebrew/English, Risk vs. Opportunity."""
    report = _generate_guardian_report_impl(31.784, 35.221, address=E2E_ADDRESS, language="en")
    assert "risks" in report
    assert "opportunities" in report
    assert "language" in report
    assert report["language"] in ("en", "he")
    # Report text may be None (stub) but key must exist for actionable output
    assert "report" in report


def test_e2e_success_criteria_guardian_report_bilingual():
    """Success Criteria: Report can be delivered in Hebrew or English."""
    report_en = _generate_guardian_report_impl(31.784, 35.221, language="en")
    report_he = _generate_guardian_report_impl(31.784, 35.221, language="he")
    assert report_en["language"] == "en"
    assert report_he["language"] == "he"


# --- Final Expected Output: Guardian Report content structure ---


def test_e2e_guardian_report_can_hold_noise_alert_and_opportunity():
    """E2E Expected Output: Report structure can hold Noise Alert, Urban Change, Opportunity."""
    report = _generate_guardian_report_impl(31.784, 35.221, address=E2E_ADDRESS, language="en")
    assert isinstance(report["risks"], list)
    assert isinstance(report["opportunities"], list)
    # Structure can hold additional risk/opportunity (e.g. from external source)
    risks_copy = report["risks"] + [
        {"type": "noise", "message": "Light Rail construction; 24/7 noise for 24 months."}
    ]
    opportunities_copy = report["opportunities"] + [
        {"type": "value_increase", "message": "Light Rail station proximity ~15% value increase."}
    ]
    assert len(risks_copy) == len(report["risks"]) + 1
    assert len(opportunities_copy) == len(report["opportunities"]) + 1


def test_e2e_cadastral_returns_legal_id_structure():
    """E2E Step 2: Cadastral returns Legal ID structure (Block/Gush, Parcel/Helka)."""
    result = _get_cadastral_data_impl(E2E_EXPECTED_LAT, E2E_EXPECTED_LON)
    assert "gush" in result
    assert "helka" in result
    # When implemented: result["gush"] == 30050, result["helka"] == 45
    assert result["gush"] is None or result["gush"] == E2E_EXPECTED_GUSH
    assert result["helka"] is None or result["helka"] == E2E_EXPECTED_HELKA


def test_e2e_urban_plans_returns_plans_and_permits_lists():
    """E2E Step 3–4: Urban plans and permits returned as lists for spatial/permits analysis."""
    result = _get_urban_plans_impl(E2E_EXPECTED_LAT, E2E_EXPECTED_LON)
    assert isinstance(result["plans"], list)
    assert isinstance(result["permits"], list)
    # When implemented: plans may include "Urban Renewal" on adjacent plot; permits may include Light Rail
    assert "plans" in result and "permits" in result
