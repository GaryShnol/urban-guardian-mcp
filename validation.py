"""
Data validation and error handling utilities for Urban Guardian.

Provides robust validation for all inputs and graceful error handling.
"""

from __future__ import annotations

import re
from typing import Any


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


def validate_latitude(lat: float) -> float:
    """
    Validate latitude value.
    
    Args:
        lat: Latitude value
    
    Returns:
        Validated latitude
    
    Raises:
        ValidationError: If latitude is invalid
    """
    try:
        lat = float(lat)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Invalid latitude: must be a number, got {lat}") from e
    
    if not -90 <= lat <= 90:
        raise ValidationError(f"Latitude must be between -90 and 90, got {lat}")
    
    return lat


def validate_longitude(lon: float) -> float:
    """
    Validate longitude value.
    
    Args:
        lon: Longitude value
    
    Returns:
        Validated longitude
    
    Raises:
        ValidationError: If longitude is invalid
    """
    try:
        lon = float(lon)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Invalid longitude: must be a number, got {lon}") from e
    
    if not -180 <= lon <= 180:
        raise ValidationError(f"Longitude must be between -180 and 180, got {lon}")
    
    return lon


def validate_coordinates(lat: float, lon: float) -> tuple[float, float]:
    """
    Validate both latitude and longitude.
    
    Args:
        lat: Latitude value
        lon: Longitude value
    
    Returns:
        Tuple of validated (latitude, longitude)
    
    Raises:
        ValidationError: If coordinates are invalid
    """
    lat = validate_latitude(lat)
    lon = validate_longitude(lon)
    return lat, lon


def validate_language(language: str) -> str:
    """
    Validate language code.
    
    Args:
        language: Language code
    
    Returns:
        Validated language code (lowercase)
    
    Raises:
        ValidationError: If language is invalid
    """
    if not isinstance(language, str):
        raise ValidationError(f"Language must be a string, got {type(language)}")
    
    language = language.lower().strip()
    
    if language not in ["he", "en"]:
        raise ValidationError(f"Language must be 'he' or 'en', got '{language}'")
    
    return language


def validate_plan_number(plan_number: str) -> str:
    """
    Validate and normalize plan number.
    
    Args:
        plan_number: Plan number
    
    Returns:
        Validated plan number (trimmed)
    
    Raises:
        ValidationError: If plan number is invalid
    """
    if not plan_number:
        raise ValidationError("Plan number is required")
    
    if not isinstance(plan_number, (str, int)):
        raise ValidationError(f"Plan number must be string or int, got {type(plan_number)}")
    
    plan_number = str(plan_number).strip()
    
    if not plan_number:
        raise ValidationError("Plan number cannot be empty")
    
    # Must contain at least one digit
    if not re.search(r'\d', plan_number):
        raise ValidationError(f"Plan number must contain at least one digit, got '{plan_number}'")
    
    return plan_number


def validate_radius(radius: float, min_radius: float = 10, max_radius: float = 10000) -> float:
    """
    Validate radius value.
    
    Args:
        radius: Radius in meters
        min_radius: Minimum allowed radius (default 10m)
        max_radius: Maximum allowed radius (default 10km)
    
    Returns:
        Validated radius
    
    Raises:
        ValidationError: If radius is invalid
    """
    try:
        radius = float(radius)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Radius must be a number, got {radius}") from e
    
    if not min_radius <= radius <= max_radius:
        raise ValidationError(f"Radius must be between {min_radius}m and {max_radius}m, got {radius}m")
    
    return radius


def safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary values.
    
    Args:
        data: Dictionary to search
        keys: Sequence of keys to navigate
        default: Default value if any key is missing
    
    Returns:
        Value at nested key or default
    
    Example:
        safe_get({"a": {"b": {"c": 1}}}, "a", "b", "c")  # Returns 1
        safe_get({"a": {"b": {"c": 1}}}, "a", "x", "c")  # Returns None
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Int value or default
    """
    try:
        return int(value)
    except (TypeError, ValueError, AttributeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Float value or default
    """
    try:
        return float(value)
    except (TypeError, ValueError, AttributeError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """
    Safely convert value to string.
    
    Args:
        value: Value to convert
        default: Default value if value is None
    
    Returns:
        String value or default
    """
    if value is None:
        return default
    try:
        return str(value).strip()
    except (AttributeError, TypeError):
        return default


def validate_address(address: str) -> str:
    """
    Validate address string.
    
    Args:
        address: Address to validate
    
    Returns:
        Validated address (trimmed)
    
    Raises:
        ValidationError: If address is invalid
    """
    if not address:
        raise ValidationError("Address is required")
    
    if not isinstance(address, str):
        raise ValidationError(f"Address must be a string, got {type(address)}")
    
    address = address.strip()
    
    if not address:
        raise ValidationError("Address cannot be empty")
    
    if len(address) < 3:
        raise ValidationError(f"Address too short (minimum 3 characters), got '{address}'")
    
    return address


def handle_api_error(error: Exception, operation: str, language: str = "en") -> dict:
    """
    Generate user-friendly error response.
    
    Args:
        error: The exception that occurred
        operation: Description of operation that failed
        language: Response language
    
    Returns:
        Dict with error information
    """
    error_type = type(error).__name__
    error_msg = str(error)
    
    if language == "he":
        return {
            "error": True,
            "error_type": error_type,
            "error_message": error_msg,
            "operation": operation,
            "note": f"שגיאה בביצוע {operation}: {error_msg}",
            "suggestion": "נסה שוב מאוחר יותר או פנה לתמיכה",
        }
    else:
        return {
            "error": True,
            "error_type": error_type,
            "error_message": error_msg,
            "operation": operation,
            "note": f"Error performing {operation}: {error_msg}",
            "suggestion": "Try again later or contact support",
        }


def ensure_dict(value: Any, default: dict | None = None) -> dict:
    """
    Ensure value is a dictionary.
    
    Args:
        value: Value to check
        default: Default dict if value is not a dict
    
    Returns:
        Dict value or default
    """
    if isinstance(value, dict):
        return value
    return default or {}


def ensure_list(value: Any, default: list | None = None) -> list:
    """
    Ensure value is a list.
    
    Args:
        value: Value to check
        default: Default list if value is not a list
    
    Returns:
        List value or default
    """
    if isinstance(value, list):
        return value
    return default or []
