"""
Pytest functional tests for all Urban Guardian MCP server tools.

Covers: get_cadastral_data, get_urban_plans, get_spatial_mining, generate_guardian_report, and MCP tool registration.
"""

import asyncio

import pytest

from server import (
    mcp,
    _get_cadastral_data_impl,
    _get_multi_radius_search_impl,
    _get_spatial_mining_impl,
    _get_urban_plans_impl,
    _generate_guardian_report_impl,
)


# --- MCP server tool registration ---


def test_mcp_server_exposes_all_tools():
    """MCP server registers geocode_address, get_cadastral_data, get_urban_plans, get_spatial_mining, generate_guardian_report."""
    async def _get_tool_names():
        tools = await mcp._tool_manager.get_tools()
        if isinstance(tools, dict):
            return list(tools.keys())
        return [t.name for t in tools]

    tool_names = asyncio.run(_get_tool_names())
    expected = {
        "geocode_address",
        "get_cadastral_data",
        "get_urban_plans",
        "get_spatial_mining",
        "get_multi_radius_search",
        "generate_guardian_report",
    }
    assert expected.issubset(set(tool_names)), f"Expected tools {expected}, got {tool_names}"


# --- get_cadastral_data ---


def test_get_cadastral_data_returns_dict_with_gush_helka_note():
    """get_cadastral_data returns dict with gush, helka, note keys."""
    result = _get_cadastral_data_impl(32.08, 34.78)
    assert isinstance(result, dict)
    assert "gush" in result
    assert "helka" in result
    assert "note" in result


def test_get_cadastral_data_accepts_wgs84_coordinates():
    """get_cadastral_data accepts WGS84 lat/lon (Tel Aviv, Jerusalem)."""
    r1 = _get_cadastral_data_impl(32.0853, 34.7818)  # Tel Aviv
    r2 = _get_cadastral_data_impl(31.7683, 35.2137)  # Jerusalem
    assert "gush" in r1 and "helka" in r1 and "note" in r1
    assert "gush" in r2 and "helka" in r2 and "note" in r2
    # Note may indicate GovMap result or "No cadastral data"
    assert "cadastral" in r1["note"].lower() or "govmap" in r1["note"].lower() or "no cadastral" in r1["note"].lower()


def test_get_cadastral_data_note_indicates_result():
    """get_cadastral_data returns note describing result (GovMap or no data)."""
    result = _get_cadastral_data_impl(32.0, 34.0)
    assert result["note"] and isinstance(result["note"], str)


# --- get_urban_plans ---


def test_get_urban_plans_returns_dict_with_plans_permits_note():
    """get_urban_plans returns dict with plans, permits, note keys."""
    result = _get_urban_plans_impl(32.08, 34.78)
    assert isinstance(result, dict)
    assert "plans" in result
    assert "permits" in result
    assert "note" in result


def test_get_urban_plans_returns_lists():
    """get_urban_plans returns plans and permits as lists."""
    result = _get_urban_plans_impl(32.08, 34.78)
    assert isinstance(result["plans"], list)
    assert isinstance(result["permits"], list)


def test_get_urban_plans_accepts_wgs84_coordinates():
    """get_urban_plans accepts WGS84 lat/lon."""
    result = _get_urban_plans_impl(32.0853, 34.7818)
    assert isinstance(result["plans"], list)
    assert isinstance(result["permits"], list)
    assert result["note"] and isinstance(result["note"], str)


def test_get_urban_plans_note_present():
    """get_urban_plans returns a non-empty note."""
    result = _get_urban_plans_impl(32.0, 34.0)
    assert result["note"] and isinstance(result["note"], str)


# --- get_spatial_mining ---


def test_get_spatial_mining_returns_dict_with_radius_keys():
    """get_spatial_mining returns within_100m, within_500m, within_1000m and note."""
    result = _get_spatial_mining_impl(32.08, 34.78)
    assert isinstance(result, dict)
    assert "within_100m" in result
    assert "within_500m" in result
    assert "within_1000m" in result
    assert "note" in result


def test_get_spatial_mining_each_radius_has_plans_permits():
    """get_spatial_mining each radius bucket has plans and permits lists."""
    result = _get_spatial_mining_impl(32.08, 34.78)
    for key in ("within_100m", "within_500m", "within_1000m"):
        assert isinstance(result[key], dict)
        assert "plans" in result[key]
        assert "permits" in result[key]
        assert isinstance(result[key]["plans"], list)
        assert isinstance(result[key]["permits"], list)


def test_get_spatial_mining_accepts_wgs84_coordinates():
    """get_spatial_mining accepts WGS84 lat/lon."""
    result = _get_spatial_mining_impl(32.0853, 34.7818)
    assert "within_100m" in result and "within_500m" in result and "within_1000m" in result


# --- get_multi_radius_search ---


def test_get_multi_radius_search_returns_layer_based_radii():
    """get_multi_radius_search returns bedroom_50m, permits_100m, lifestyle_300m, plans_500m, value_800m, summary, note."""
    result = _get_multi_radius_search_impl(32.08, 34.78)
    assert "bedroom_50m" in result
    assert "permits_100m" in result
    assert "lifestyle_300m" in result
    assert "plans_500m" in result
    assert "value_800m" in result
    assert "summary" in result
    assert "note" in result


def test_get_multi_radius_search_each_key_has_plans_permits_radius_labels():
    """get_multi_radius_search each radius key has plans, permits, radius_m, label_he, label_en."""
    result = _get_multi_radius_search_impl(32.08, 34.78)
    for key in ("bedroom_50m", "permits_100m", "lifestyle_300m", "plans_500m", "value_800m"):
        assert key in result
        bucket = result[key]
        assert "plans" in bucket and "permits" in bucket
        assert "radius_m" in bucket and "label_he" in bucket and "label_en" in bucket
        assert isinstance(bucket["plans"], list) and isinstance(bucket["permits"], list)


def test_get_multi_radius_search_summary_has_boolean_flags():
    """get_multi_radius_search summary has has_any_bedroom, has_any_permits_100m, etc."""
    result = _get_multi_radius_search_impl(32.08, 34.78)
    s = result.get("summary", {})
    assert "has_any_bedroom" in s
    assert "has_any_permits_100m" in s
    assert "has_any_lifestyle" in s
    assert "has_any_plans_500m" in s
    assert "has_any_value" in s
    assert isinstance(s["has_any_bedroom"], bool)


# --- generate_guardian_report ---


def test_generate_guardian_report_returns_dict_with_report_risks_opportunities_language_note():
    """generate_guardian_report returns dict with report, risks, opportunities, guardian_score, consult, language, note."""
    result = _generate_guardian_report_impl(32.08, 34.78)
    assert isinstance(result, dict)
    assert "report" in result
    assert "risks" in result
    assert "opportunities" in result
    assert "guardian_score" in result
    assert "consult" in result
    assert "language" in result
    assert "note" in result
    assert result["report"] is not None
    assert isinstance(result["guardian_score"], (int, type(None)))


def test_generate_guardian_report_default_language_is_en():
    """generate_guardian_report defaults to language 'en'."""
    result = _generate_guardian_report_impl(32.08, 34.78)
    assert result["language"] == "en"


def test_generate_guardian_report_accepts_language_he():
    """generate_guardian_report accepts language 'he'."""
    result = _generate_guardian_report_impl(32.08, 34.78, language="he")
    assert result["language"] == "he"


def test_generate_guardian_report_accepts_optional_address():
    """generate_guardian_report accepts optional address (for report header)."""
    result = _generate_guardian_report_impl(32.08, 34.78, address="HaYarkon 10, Tel Aviv")
    assert "report" in result
    assert isinstance(result["risks"], list)
    assert isinstance(result["opportunities"], list)


def test_generate_guardian_report_accepts_wgs84_coordinates():
    """generate_guardian_report accepts WGS84 lat/lon and returns weighted analysis."""
    result = _generate_guardian_report_impl(32.0853, 34.7818, language="en")
    assert result["report"] is not None
    assert isinstance(result["risks"], list)
    assert isinstance(result["opportunities"], list)
    assert "guardian" in result["note"].lower() or "weighted" in result["note"].lower()


def test_generate_guardian_report_returns_guardian_score_and_consult():
    """generate_guardian_report returns guardian_score (0–100) and consult text."""
    result = _generate_guardian_report_impl(32.0, 34.0)
    assert "guardian_score" in result
    assert result["guardian_score"] is None or 0 <= result["guardian_score"] <= 100
    assert "consult" in result
    assert result["consult"] is None or isinstance(result["consult"], str)
