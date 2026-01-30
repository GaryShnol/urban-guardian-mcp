"""
Pytest tests for GovMap geocoding: valid address → WGS84, not found → error with "did you mean?".
"""

import pytest
from unittest.mock import MagicMock, patch

from govmap_client import (
    AddressNotFoundError,
    clean_address,
    search_address,
    validate_coordinates_in_israel,
)
from server import _geocode_address_impl


# --- govmap_client unit tests ---


def test_clean_address_strips_and_normalizes_spaces():
    assert clean_address("  דיזנגוף 100 ,  תל אביב  ") == "דיזנגוף 100,תל אביב"
    assert clean_address("  a  b  ") == "a b"


def test_clean_address_empty():
    assert clean_address("") == ""
    assert clean_address("   ") == ""


def test_clean_address_none_or_non_string_returns_empty():
    """Edge case: non-string or None returns empty string."""
    assert clean_address("") == ""
    assert clean_address(None) == ""  # type: ignore[arg-type]
    assert clean_address(123) == ""  # type: ignore[arg-type]


def test_validate_coordinates_in_israel():
    assert validate_coordinates_in_israel(32.08, 34.78) is True  # Tel Aviv
    assert validate_coordinates_in_israel(31.77, 35.22) is True  # Jerusalem
    assert validate_coordinates_in_israel(0, 0) is False
    assert validate_coordinates_in_israel(29.46, 34.2) is True  # south edge inside bbox


@patch("govmap_client.httpx.Client")
def test_search_address_valid_returns_wgs84(mock_client_class):
    """Valid address returns WGS84 coordinates (e.g. דיזנגוף 100,תל אביב)."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {
                "latitude": 32.0775,
                "longitude": 34.7750,
                "address": "דיזנגוף 100, תל אביב",
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    result = search_address("דיזנגוף 100,תל אביב")

    assert result["latitude"] == 32.0775
    assert result["longitude"] == 34.7750
    assert result["display_name"] == "דיזנגוף 100, תל אביב"


@patch("govmap_client.httpx.Client")
def test_search_address_not_found_with_suggestions_raises_did_you_mean(mock_client_class):
    """Address not found but API returns suggestions → AddressNotFoundError with 'did you mean?'."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [],
        "suggestions": ["דיזנגוף 100, תל אביב", "דיזנגוף 99, תל אביב"],
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    with pytest.raises(AddressNotFoundError) as exc_info:
        search_address("דיזנגוף 1000,תל אביב")

    assert "could not be found" in exc_info.value.message or "didn't found" in exc_info.value.message
    assert "Did you mean" in exc_info.value.message or "did you mean" in exc_info.value.message.lower()
    assert exc_info.value.suggestions == ["דיזנגוף 100, תל אביב", "דיזנגוף 99, תל אביב"]


@patch("govmap_client.httpx.Client")
def test_search_address_not_found_no_suggestions_raises(mock_client_class):
    """Address not found and no suggestions → AddressNotFoundError without suggestions."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    with pytest.raises(AddressNotFoundError) as exc_info:
        search_address("nonexistent street 999, nowhere")

    assert "could not be found" in exc_info.value.message or "didn't found" in exc_info.value.message
    assert exc_info.value.suggestions == []


@patch("govmap_client.httpx.Client")
def test_search_address_empty_raises(mock_client_class):
    """Empty address raises AddressNotFoundError."""
    with pytest.raises(AddressNotFoundError) as exc_info:
        search_address("   ")
    assert "empty" in exc_info.value.message.lower()
    mock_client_class.assert_not_called()


@patch("govmap_client.httpx.Client")
def test_search_address_parses_geojson_feature_collection(mock_client_class):
    """GovMap response as GeoJSON FeatureCollection returns WGS84 from geometry."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [35.2137, 31.7683]},
                "properties": {"display_name": "Jerusalem"},
            }
        ],
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_class.return_value = mock_client

    result = search_address("Jerusalem")
    assert result["latitude"] == 31.7683
    assert result["longitude"] == 35.2137
    assert result.get("display_name") == "Jerusalem"  # from properties.name


# --- server tool integration tests (geocode_address returns dict) ---


@patch("server.search_address")
def test_geocode_address_tool_returns_wgs84_on_success(mock_search):
    """geocode_address returns latitude/longitude in WGS84 format when address is found."""
    mock_search.return_value = {
        "latitude": 32.0775,
        "longitude": 34.7750,
        "display_name": "דיזנגוף 100, תל אביב",
    }

    result = _geocode_address_impl("דיזנגוף 100,תל אביב")

    assert "error" not in result
    assert result["latitude"] == 32.0775
    assert result["longitude"] == 34.7750
    assert result["display_name"] == "דיזנגוף 100, תל אביב"


@patch("server.search_address")
def test_geocode_address_tool_returns_error_and_suggestions_when_not_found(mock_search):
    """geocode_address returns error and suggestions when address not found (did you mean?)."""
    mock_search.side_effect = AddressNotFoundError(
        "This address didn't found. Did you mean: דיזנגוף 100, תל אביב?",
        suggestions=["דיזנגוף 100, תל אביב"],
    )

    result = _geocode_address_impl("דיזנגוף 1000,תל אביב")

    assert "error" in result
    assert "could not be found" in result["error"] or "didn't found" in result["error"]
    assert result.get("suggestions") == ["דיזנגוף 100, תל אביב"]
    assert "latitude" not in result or result.get("latitude") is None


@patch("server.search_address")
def test_geocode_address_tool_returns_error_when_not_found_no_suggestions(mock_search):
    """geocode_address returns error when address not found and no suggestions."""
    mock_search.side_effect = AddressNotFoundError("This address didn't found.", suggestions=[])

    result = _geocode_address_impl("nonexistent 999")

    assert "error" in result
    assert "could not be found" in result["error"] or result["error"] == "This address didn't found."
    assert result.get("suggestions") == []
