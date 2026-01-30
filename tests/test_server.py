"""
Pytest functional tests for all Urban Guardian MCP server tools.

Covers: get_cadastral_data, get_urban_plans, generate_guardian_report, and MCP tool registration.
"""

import asyncio

import pytest

from server import (
    mcp,
    _get_cadastral_data_impl,
    _get_urban_plans_impl,
    _generate_guardian_report_impl,
)


# --- MCP server tool registration ---


def test_mcp_server_exposes_all_four_tools():
    """MCP server registers geocode_address, get_cadastral_data, get_urban_plans, generate_guardian_report."""
    async def _get_tool_names():
        tools = await mcp._tool_manager.get_tools()
        if isinstance(tools, dict):
            return list(tools.keys())
        return [t.name for t in tools]

    tool_names = asyncio.run(_get_tool_names())
    expected = {"geocode_address", "get_cadastral_data", "get_urban_plans", "generate_guardian_report"}
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
    assert r1["gush"] is None and r1["helka"] is None
    assert r2["gush"] is None and r2["helka"] is None
    assert "cadastral" in r1["note"].lower() or "stub" in r1["note"].lower()


def test_get_cadastral_data_stub_note_indicates_not_implemented():
    """get_cadastral_data stub returns note indicating not yet implemented."""
    result = _get_cadastral_data_impl(32.0, 34.0)
    assert "not yet implemented" in result["note"].lower() or "stub" in result["note"].lower()


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
    assert result["plans"] == []
    assert result["permits"] == []
    assert "ArcGIS" in result["note"] or "stub" in result["note"].lower()


def test_get_urban_plans_stub_note_indicates_not_implemented():
    """get_urban_plans stub returns note indicating not yet implemented."""
    result = _get_urban_plans_impl(32.0, 34.0)
    assert "not yet implemented" in result["note"].lower() or "stub" in result["note"].lower()


# --- generate_guardian_report ---


def test_generate_guardian_report_returns_dict_with_report_risks_opportunities_language_note():
    """generate_guardian_report returns dict with report, risks, opportunities, language, note."""
    result = _generate_guardian_report_impl(32.08, 34.78)
    assert isinstance(result, dict)
    assert "report" in result
    assert "risks" in result
    assert "opportunities" in result
    assert "language" in result
    assert "note" in result


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
    assert result["risks"] == []
    assert result["opportunities"] == []


def test_generate_guardian_report_accepts_wgs84_coordinates():
    """generate_guardian_report accepts WGS84 lat/lon."""
    result = _generate_guardian_report_impl(32.0853, 34.7818, language="en")
    assert result["report"] is None
    assert result["risks"] == []
    assert result["opportunities"] == []
    assert "not yet implemented" in result["note"].lower() or "stub" in result["note"].lower()


def test_generate_guardian_report_stub_note_indicates_not_implemented():
    """generate_guardian_report stub returns note indicating not yet implemented."""
    result = _generate_guardian_report_impl(32.0, 34.0)
    assert "not yet implemented" in result["note"].lower() or "stub" in result["note"].lower()
