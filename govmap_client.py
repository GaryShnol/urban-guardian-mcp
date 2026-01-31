"""
GovMap address search client for Urban Guardian.

GovMap integration reference (endpoints, layer names, response shapes):
  docs/GOVMAP_INTEGRATION.md
Official GovMap API docs (https://api.govmap.gov.il/docs) may return Access Denied;
in-repo reference above is the source of truth.

Geocoding:
  GovMap geocode: https://www.govmap.gov.il/sites/api/index.html (iframe/JS).
  Configurable GOVMAP_SEARCH_URL (default SearchRest.ashx); fallback: Nominatim (Israel).
Spatial (WFS/WMS):
  GeoServer OWS: https://www.govmap.gov.il/api/geoserver/ows — WFS GetFeature (primary),
  WMS GetFeatureInfo (fallback). Layer format: govmap:layer_<name>.
Validates input, Israel bbox; returns WGS84 or raises AddressNotFoundError with suggestions.
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

# GovMap API endpoints for querying plans and layers
GOVMAP_API_BASE = "https://www.govmap.gov.il/api"
GOVMAP_IDENTIFY_URL = f"{GOVMAP_API_BASE}/identify"
GOVMAP_QUERY_URL = f"{GOVMAP_API_BASE}/query"
GOVMAP_GEOSERVER_URL = "https://www.govmap.gov.il/api/geoserver/ows"
GOVMAP_LAYERS_CATALOG_URL = f"{GOVMAP_API_BASE}/layers-catalog/catalog"

# Discovered plan-related layers from GovMap catalog
# Correct format: govmap:layer_<name> (not govmap:<name>)
# These can be overridden via environment variables
GOVMAP_PLAN_LAYERS = os.environ.get(
    "GOVMAP_PLAN_LAYERS", 
    "govmap:layer_tabaot,govmap:layer_retzefmigrashim,govmap:layer_retzefgvulot"
).split(",")
GOVMAP_PERMIT_LAYERS = os.environ.get("GOVMAP_PERMIT_LAYERS", "").split(",") if os.environ.get("GOVMAP_PERMIT_LAYERS") else []

# Cadastral layers (גוש/חלקה) — from GovMap catalog: parcel_all (חלקות), sub_gush_all (גושים)
# parcel_all contains both block and parcel; sub_gush_all is blocks only.
GOVMAP_CADASTRAL_LAYERS = os.environ.get(
    "GOVMAP_CADASTRAL_LAYERS",
    "govmap:layer_parcel_all,govmap:layer_parcel_ownership_new,govmap:layer_sub_gush_all,govmap:layer_sub_gush",
).split(",")

# Noise & Environmental layers (רעש וזיהום)
GOVMAP_NOISE_LAYERS = os.environ.get(
    "GOVMAP_NOISE_LAYERS",
    "govmap:layer_svivanoiseday,govmap:layer_svivanoisenight"
).split(",")

# TAMA 38 & Urban Renewal layers (תמ"א ופינוי בינוי)
GOVMAP_TAMA_LAYERS = os.environ.get(
    "GOVMAP_TAMA_LAYERS",
    "govmap:layer_tamat_investor_informetion,govmap:layer_tamat_districts_polygons,govmap:layer_tama70"
).split(",")

# Transport & Infrastructure layers (תחבורה ותשתיות)
# Note: Municipal-specific layers may need city detection
GOVMAP_TRANSPORT_LAYERS = os.environ.get(
    "GOVMAP_TRANSPORT_LAYERS",
    ""  # To be populated with discovered layers
).split(",") if os.environ.get("GOVMAP_TRANSPORT_LAYERS") else []

# Conservation & Heritage layers (שימור ומורשת)
# Note: Highly municipal-specific
GOVMAP_CONSERVATION_LAYERS = os.environ.get(
    "GOVMAP_CONSERVATION_LAYERS",
    ""
).split(",") if os.environ.get("GOVMAP_CONSERVATION_LAYERS") else []

# Hazards layers (מפגעים - קווי מתח, זיהום)
GOVMAP_HAZARDS_LAYERS = os.environ.get(
    "GOVMAP_HAZARDS_LAYERS",
    ""  # High voltage, environmental hazards - to be discovered
).split(",") if os.environ.get("GOVMAP_HAZARDS_LAYERS") else []

# Multi-radius search: radius (m) by layer / circle type (for real-estate and urban planning).
# One size does not fit all — layers of influence (docs/GOVMAP_INTEGRATION.md).
# BEDROOM: lot + immediate neighbours (TAMA 38/2, balcony, noise/dust).
# PERMITS: construction permits = bulldozers under the window.
# LIFESTYLE: neighborhood character (towers, schools, commercial).
# PLANS: תב"ע at 500m still affects the neighborhood.
# VALUE: infrastructure (metro, interchanges) — accessibility vs. noise; >800m = less relevant daily.
RADIUS_BEDROOM_M = 50
RADIUS_PERMITS_M = 100
RADIUS_HAZARDS_M = 200
RADIUS_LIFESTYLE_M = 300
RADIUS_PLANS_M = 500
RADIUS_VALUE_M = 800
RADIUS_TRANSPORT_M = 1000

# Default presets for multi_radius_search: (key, radius_m, label_he, label_en)
MULTI_RADIUS_PRESETS = [
    ("bedroom_50m", RADIUS_BEDROOM_M, "מעגל מיידי", "Bedroom"),
    ("permits_100m", RADIUS_PERMITS_M, "היתרי בנייה", "Construction permits"),
    ("lifestyle_300m", RADIUS_LIFESTYLE_M, "מעגל שכונה", "Lifestyle"),
    ("plans_500m", RADIUS_PLANS_M, "תב\"ע", "Urban plans"),
    ("value_800m", RADIUS_VALUE_M, "מעגל תשתית", "Value/Infrastructure"),
]


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


def query_plans_at_coordinates(
    latitude: float, longitude: float, radius_m: float | None = None
) -> dict:
    """
    Query GovMap API for urban plans and building permits at given WGS84 coordinates.
    Optionally restrict to a radius in meters (Station 3 — spatial mining).

    All data is fetched from GovMap only. Methods used:
    1. GovMap WFS GetFeature (GeoServer) — primary; returns plans/permits.
    2. GovMap identify service (if available)
    3. GovMap intersect-features (WKT)

    Args:
        latitude: WGS84 latitude (e.g. 31.795).
        longitude: WGS84 longitude (e.g. 34.648).
        radius_m: Optional radius in meters; when set, bbox is built from this radius.

    Returns:
        Dict with 'plans' (list of plan dicts) and 'permits' (list of permit dicts).
        Each plan/permit dict contains relevant metadata (name, status, number, etc.).
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {"plans": [], "permits": [], "note": "Coordinates outside Israel bbox."}

    plans: list[dict] = []
    permits: list[dict] = []

    # Try GovMap search-service API first (we know this endpoint works from integration tests)
    try:
        result = _query_via_search_service(latitude, longitude, radius_m=radius_m)
        if result.get("plans") or result.get("permits"):
            out = dict(result)
            if radius_m is not None and radius_m > 0:
                out["radius_m_used"] = radius_m
            return out
    except Exception:
        pass

    # Try GovMap identify by coordinates and layers (from documentation)
    try:
        result = _query_via_govmap_identify(latitude, longitude)
        if result.get("plans") or result.get("permits"):
            out = dict(result)
            if radius_m is not None and radius_m > 0:
                out["radius_m_used"] = radius_m
            return out
    except Exception:
        pass

    # Try intersectFeatures with WKT geometry (from documentation)
    try:
        result = _query_via_intersect_features(latitude, longitude)
        if result.get("plans") or result.get("permits"):
            out = dict(result)
            if radius_m is not None and radius_m > 0:
                out["radius_m_used"] = radius_m
            return out
    except Exception:
        pass

    # Fallback: return what we have with metadata
    note = "Query completed. WFS GetFeature is the primary method; no features in this area or service unavailable."
    if radius_m is not None and radius_m > 0:
        note += f" (radius_m={radius_m})"
    return {
        "plans": plans,
        "permits": permits,
        "note": note,
        "radius_m_used": radius_m if radius_m and radius_m > 0 else None,
    }


def _parse_cadastral_attributes(props: dict) -> tuple[object, object]:
    """
    Extract gush (block) and helka (parcel) from GovMap feature attributes.
    GovMap may use GUSH, HELKA, gush, helka, גוש, חלקה, or similar keys.
    Returns (gush_value, helka_value); either may be None.
    """
    if not isinstance(props, dict):
        return None, None
    gush = None
    helka = None
    for k, v in props.items():
        if v is None:
            continue
        k_str = (k or "").strip()
        k_lower = k_str.lower()
        if k_lower in ("gush", "gush_num", "block") or k_str == "גוש":
            try:
                gush = int(v) if isinstance(v, (int, float)) else int(float(str(v).strip()))
            except (ValueError, TypeError):
                gush = v
        elif k_lower in ("helka", "helka_num", "parcel") or k_str == "חלקה":
            try:
                helka = int(v) if isinstance(v, (int, float)) else int(float(str(v).strip()))
            except (ValueError, TypeError):
                helka = v
    return gush, helka


def get_cadastral_at_coordinates(latitude: float, longitude: float) -> dict:
    """
    Station 2 — Cadastral: Run "Identify" (דקירה) on GovMap cadastral layers to get
    Block (Gush / גוש) and Parcel (Helka / חלקה) at the given WGS84 point.

    Uses WFS GetFeature with a small bbox around the point. Tries parcel_all (חלקות)
    and sub_gush_all (גושים) layers. Required for Tabu (Title Deed) legal identity.

    Args:
        latitude: WGS84 latitude (e.g. 32.08).
        longitude: WGS84 longitude (e.g. 34.78).

    Returns:
        Dict with gush, helka (int or None), source, layer, and optional note.
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {
            "gush": None,
            "helka": None,
            "note": "Coordinates outside Israel bbox.",
        }
    # Small bbox ~20m for point-in-polygon (Identify)
    delta = 0.0002
    bbox = f"{longitude - delta},{latitude - delta},{longitude + delta},{latitude + delta}"
    layers = [s.strip() for s in GOVMAP_CADASTRAL_LAYERS if s.strip()]
    if not layers:
        layers = [
            "govmap:layer_parcel_all",
            "govmap:layer_sub_gush_all",
        ]
    for layer_name in layers[:4]:
        try:
            params = {
                "service": "WFS",
                "version": "1.1.0",
                "request": "GetFeature",
                "typeName": layer_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{bbox},EPSG:4326",
                "maxFeatures": "5",
            }
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                continue
            content_type = (resp.headers.get("content-type") or "").lower()
            if "json" not in content_type:
                continue
            data = resp.json()
            features = []
            if isinstance(data, dict):
                features = data.get("features", [])
            elif isinstance(data, list):
                features = data
            if not features:
                continue
            gush, helka = None, None
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") or feature.get("attributes") or {}
                g, h = _parse_cadastral_attributes(props)
                if g is not None:
                    gush = g
                if h is not None:
                    helka = h
            if gush is not None or helka is not None:
                return {
                    "gush": gush,
                    "helka": helka,
                    "source": "govmap",
                    "layer": layer_name.replace("govmap:layer_", ""),
                    "features_count": len(features),
                    "note": "Cadastral data from GovMap WFS.",
                }
        except Exception:
            continue
    return {
        "gush": None,
        "helka": None,
        "note": "No cadastral (gush/helka) data at this location from GovMap.",
    }


def spatial_mining_at_coordinates(
    latitude: float,
    longitude: float,
    radius_permits_m: float = 100,
    radius_plans_m: float = 500,
    radius_infrastructure_m: float = 1000,
) -> dict:
    """
    Station 3 — Spatial Data Mining: Query plans and permits at multiple radii.
    - Permits (היתרי בנייה) up to radius_permits_m (default 100 m).
    - Plans (תב"ע) up to radius_plans_m (default 500 m).
    - Infrastructure / wider context up to radius_infrastructure_m (default 1000 m).

    Returns structured data by radius for use by the Brain (Phase 4).
    Infrastructure layers (metro, power lines) can be added when GovMap layers are configured.
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {
            "within_100m": {"plans": [], "permits": []},
            "within_500m": {"plans": [], "permits": []},
            "within_1000m": {"plans": [], "permits": []},
            "note": "Coordinates outside Israel bbox.",
        }
    r100 = query_plans_at_coordinates(latitude, longitude, radius_m=radius_permits_m)
    r500 = query_plans_at_coordinates(latitude, longitude, radius_m=radius_plans_m)
    r1000 = query_plans_at_coordinates(latitude, longitude, radius_m=radius_infrastructure_m)
    return {
        "within_100m": {
            "plans": r100.get("plans", []),
            "permits": r100.get("permits", []),
        },
        "within_500m": {
            "plans": r500.get("plans", []),
            "permits": r500.get("permits", []),
        },
        "within_1000m": {
            "plans": r1000.get("plans", []),
            "permits": r1000.get("permits", []),
        },
        "radius_permits_m": radius_permits_m,
        "radius_plans_m": radius_plans_m,
        "radius_infrastructure_m": radius_infrastructure_m,
        "note": f"Spatial mining by radius: permits {radius_permits_m}m, plans {radius_plans_m}m, infrastructure {radius_infrastructure_m}m.",
    }


def multi_radius_search(
    latitude: float,
    longitude: float,
    presets: list[tuple[str, int, str, str]] | None = None,
) -> dict:
    """
    Multi-Radius Search: layer-based radii for real-estate and urban planning.

    Three circles of influence (no "one size fits all"):
    - Bedroom (0–50 m): lot + immediate neighbours — TAMA 38/2, balcony, noise/dust, privacy.
    - Lifestyle (50–300 m): neighborhood character — towers, schools, commercial.
    - Value (300–800 m): national projects, metro, interchanges; >800 m = less relevant daily.

    Layer-based radii: permits 100 m (bulldozers), תב"ע 500 m, transport 1000 m, hazards 200 m.

    Returns structured data per radius so the Brain can say e.g.:
    "אין בנייה בבניין שלך, אבל יש מגדל בבנייה במרחק 200 מטר".

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        presets: Optional list of (key, radius_m, label_he, label_en). Default: MULTI_RADIUS_PRESETS.

    Returns:
        Dict with one key per preset (e.g. bedroom_50m, permits_100m), each containing
        plans, permits, radius_m, label_he, label_en; plus summary flags and note.
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        presets_out = presets or MULTI_RADIUS_PRESETS
        out = {}
        for key, radius_m, label_he, label_en in presets_out:
            out[key] = {
                "plans": [],
                "permits": [],
                "radius_m": radius_m,
                "label_he": label_he,
                "label_en": label_en,
            }
        out["summary"] = {}
        out["note"] = "Coordinates outside Israel bbox."
        return out
    presets = presets or MULTI_RADIUS_PRESETS
    result: dict = {}
    for key, radius_m, label_he, label_en in presets:
        q = query_plans_at_coordinates(latitude, longitude, radius_m=radius_m)
        result[key] = {
            "plans": q.get("plans", []),
            "permits": q.get("permits", []),
            "radius_m": radius_m,
            "label_he": label_he,
            "label_en": label_en,
        }
    # Summary flags for the Brain (e.g. "no construction in building, but tower at 200m")
    def _count(d: dict) -> int:
        return len(d.get("plans", [])) + len(d.get("permits", []))
    summary = {
        "has_any_bedroom": _count(result.get("bedroom_50m", {})) > 0,
        "has_any_permits_100m": _count(result.get("permits_100m", {})) > 0,
        "has_any_lifestyle": _count(result.get("lifestyle_300m", {})) > 0,
        "has_any_plans_500m": _count(result.get("plans_500m", {})) > 0,
        "has_any_value": _count(result.get("value_800m", {})) > 0,
    }
    result["summary"] = summary
    result["note"] = "Multi-radius search by layer (bedroom 50m, permits 100m, lifestyle 300m, plans 500m, value 800m)."
    return result


def query_noise_data_at_coordinates(latitude: float, longitude: float) -> dict:
    """
    Query noise pollution data at given coordinates.
    Checks traffic noise levels (day and night) from GovMap environmental layers.
    
    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
    
    Returns:
        Dict with noise_day_db, noise_night_db (float or None), assessment, and raw features.
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {
            "noise_day_db": None,
            "noise_night_db": None,
            "assessment": "unavailable",
            "note": "Coordinates outside Israel bbox.",
        }
    
    # Small bbox for point query
    delta = 0.0001  # ~10m
    bbox = f"{longitude - delta},{latitude - delta},{longitude + delta},{latitude + delta}"
    
    noise_day_db = None
    noise_night_db = None
    features_found = []
    
    # Query noise layers
    for layer_name in GOVMAP_NOISE_LAYERS:
        if not layer_name or not layer_name.strip():
            continue
        layer_name = layer_name.strip()
        
        try:
            params = {
                "service": "WFS",
                "version": "1.1.0",
                "request": "GetFeature",
                "typeName": layer_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{bbox},EPSG:4326",
                "maxFeatures": "5",
            }
            
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=DEFAULT_TIMEOUT)
            
            if resp.status_code != 200:
                continue
            
            content_type = (resp.headers.get("content-type") or "").lower()
            if "json" not in content_type:
                continue
            
            data = resp.json()
            features = data.get("features", []) if isinstance(data, dict) else []
            
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") or feature.get("attributes") or {}
                features_found.append({"layer": layer_name, "properties": props})
                
                # Extract noise level (varies by layer - may be in different fields)
                for key, val in props.items():
                    if val is None:
                        continue
                    key_lower = str(key).lower()
                    
                    # Try to extract numeric noise value
                    try:
                        if "svivanoiseday" in layer_name and noise_day_db is None:
                            # Day noise layer
                            if any(x in key_lower for x in ("db", "noise", "level", "value", "רעש")):
                                noise_day_db = float(val)
                        elif "svivanoisenight" in layer_name and noise_night_db is None:
                            # Night noise layer
                            if any(x in key_lower for x in ("db", "noise", "level", "value", "רעש")):
                                noise_night_db = float(val)
                    except (ValueError, TypeError):
                        continue
        
        except Exception:
            continue
    
    # Assessment based on WHO/EPA guidelines
    assessment = "unknown"
    if noise_day_db is not None or noise_night_db is not None:
        if (noise_day_db and noise_day_db > 70) or (noise_night_db and noise_night_db > 60):
            assessment = "high"  # Health concern
        elif (noise_day_db and noise_day_db > 60) or (noise_night_db and noise_night_db > 50):
            assessment = "moderate"
        else:
            assessment = "low"
    
    return {
        "noise_day_db": noise_day_db,
        "noise_night_db": noise_night_db,
        "assessment": assessment,
        "features_found": len(features_found),
        "raw_features": features_found if features_found else None,
        "note": f"Queried {len(GOVMAP_NOISE_LAYERS)} noise layers; found {len(features_found)} features.",
    }


def query_tama_at_coordinates(latitude: float, longitude: float, radius_m: float = 200) -> dict:
    """
    Query TAMA 38 (תמ"א 38) and urban renewal projects at given coordinates.
    TAMA 38: National Outline Plan 38 for strengthening buildings against earthquakes.
    
    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        radius_m: Search radius in meters (default 200m for neighborhood context).
    
    Returns:
        Dict with tama_projects list, in_building (bool), adjacent (bool), neighborhood (bool).
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {
            "tama_projects": [],
            "in_building": False,
            "adjacent": False,
            "neighborhood": False,
            "note": "Coordinates outside Israel bbox.",
        }
    
    lat_delta, lon_delta = _bbox_delta_deg_from_radius_m(latitude, radius_m)
    bbox = f"{longitude - lon_delta},{latitude - lat_delta},{longitude + lon_delta},{latitude + lat_delta}"
    
    tama_projects = []
    
    for layer_name in GOVMAP_TAMA_LAYERS:
        if not layer_name or not layer_name.strip():
            continue
        layer_name = layer_name.strip()
        
        try:
            params = {
                "service": "WFS",
                "version": "1.1.0",
                "request": "GetFeature",
                "typeName": layer_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{bbox},EPSG:4326",
                "maxFeatures": "50",
            }
            
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=DEFAULT_TIMEOUT)
            
            if resp.status_code != 200:
                continue
            
            content_type = (resp.headers.get("content-type") or "").lower()
            if "json" not in content_type:
                continue
            
            data = resp.json()
            features = data.get("features", []) if isinstance(data, dict) else []
            
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") or feature.get("attributes") or {}
                geom = feature.get("geometry")
                
                project_info = {
                    "name": props.get("project_name") or props.get("name") or props.get("שם"),
                    "status": props.get("status") or props.get("סטטוס") or props.get("project_status"),
                    "type": props.get("project_type") or props.get("type") or "tama38",
                    "layer": layer_name.replace("govmap:layer_", ""),
                    "geometry": geom,
                    "attributes": props,
                }
                tama_projects.append(project_info)
        
        except Exception:
            continue
    
    # Determine proximity categories
    # For precise calculation, would need to compute actual distance from geometries
    # Simplified: any features found in radius_m are categorized
    in_building = False
    adjacent = False  # <50m
    neighborhood = False  # 50-200m
    
    if tama_projects:
        # Simplified heuristic: if we found projects in small radius query, assume close
        if radius_m <= 50:
            in_building = True
        elif radius_m <= 100:
            adjacent = True
        else:
            neighborhood = True
    
    return {
        "tama_projects": tama_projects,
        "in_building": in_building,
        "adjacent": adjacent,
        "neighborhood": neighborhood,
        "count": len(tama_projects),
        "note": f"Found {len(tama_projects)} TAMA projects within {radius_m}m.",
    }


def query_transport_infrastructure_at_coordinates(
    latitude: float, longitude: float, radius_m: float = 800
) -> dict:
    """
    Query transport infrastructure (metro, light rail, railway, bus stations) near coordinates.
    
    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        radius_m: Search radius in meters (default 800m for accessibility analysis).
    
    Returns:
        Dict with transport_features list, categorized by type and distance.
    """
    if not validate_coordinates_in_israel(latitude, longitude):
        return {
            "transport_features": [],
            "metro_nearby": False,
            "railway_nearby": False,
            "note": "Coordinates outside Israel bbox.",
        }
    
    lat_delta, lon_delta = _bbox_delta_deg_from_radius_m(latitude, radius_m)
    bbox = f"{longitude - lon_delta},{latitude - lat_delta},{longitude + lon_delta},{latitude + lat_delta}"
    
    transport_features = []
    
    # Query transport layers if configured
    if not GOVMAP_TRANSPORT_LAYERS or all(not x.strip() for x in GOVMAP_TRANSPORT_LAYERS):
        return {
            "transport_features": [],
            "metro_nearby": False,
            "railway_nearby": False,
            "note": "Transport layers not yet configured. Requires layer discovery.",
        }
    
    for layer_name in GOVMAP_TRANSPORT_LAYERS:
        if not layer_name or not layer_name.strip():
            continue
        layer_name = layer_name.strip()
        
        try:
            params = {
                "service": "WFS",
                "version": "1.1.0",
                "request": "GetFeature",
                "typeName": layer_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{bbox},EPSG:4326",
                "maxFeatures": "50",
            }
            
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=DEFAULT_TIMEOUT)
            
            if resp.status_code != 200:
                continue
            
            content_type = (resp.headers.get("content-type") or "").lower()
            if "json" not in content_type:
                continue
            
            data = resp.json()
            features = data.get("features", []) if isinstance(data, dict) else []
            
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") or feature.get("attributes") or {}
                
                feature_info = {
                    "name": props.get("name") or props.get("שם"),
                    "type": props.get("type") or props.get("סוג") or "transport",
                    "layer": layer_name.replace("govmap:layer_", ""),
                    "attributes": props,
                }
                transport_features.append(feature_info)
        
        except Exception:
            continue
    
    # Categorize findings
    metro_nearby = any("metro" in str(f.get("type", "")).lower() or "רכבת קלה" in str(f.get("name", "")) for f in transport_features)
    railway_nearby = any("rail" in str(f.get("type", "")).lower() or "מסילת" in str(f.get("name", "")) for f in transport_features)
    
    return {
        "transport_features": transport_features,
        "metro_nearby": metro_nearby,
        "railway_nearby": railway_nearby,
        "count": len(transport_features),
        "note": f"Found {len(transport_features)} transport features within {radius_m}m.",
    }


def _construct_mavat_url(plan_number: str, props: dict) -> str:
    """
    Construct MAVAT (מבא"ת) URL for plan details.
    Uses the current official site mavat.iplan.gov.il (mmi.gov.il/iturtabot is deprecated).
    
    Args:
        plan_number: Plan number (e.g. 3828, תתל/33)
        props: Plan properties from GovMap
    
    Returns:
        URL to MAVAT plan page
    """
    # Official MAVAT site (working): https://www.mavat.iplan.gov.il/
    # Clean plan number (remove prefixes like ג/, תתל/)
    clean_number = re.sub(r'^[א-ת]+/', '', str(plan_number))
    clean_number = re.sub(r'[^\d]', '', clean_number)  # Keep only digits
    
    if clean_number:
        # Direct link to plan by id (GovMap objectid often matches MAVAT)
        return f"https://www.mavat.iplan.gov.il/SV4/1/{clean_number}/310"
    return "https://www.mavat.iplan.gov.il/"


def _estimate_timeline_from_status(status: str, zoning: str, language: str = "he") -> dict:
    """
    Estimate construction timeline based on plan status and zoning type.
    
    Args:
        status: Plan status (approved, in-progress, etc.)
        zoning: Zoning/land use type
        language: Response language
    
    Returns:
        Dict with timeline estimation
    """
    status_lower = str(status).lower()
    zoning_lower = str(zoning).lower()
    
    # Determine if plan is approved/active
    is_approved = any(x in status_lower for x in ["אושר", "approved", "תקף", "valid"])
    is_in_progress = any(x in status_lower for x in ["בביצוע", "in progress", "מתבצע"])
    
    # Base timeline by zoning type
    if any(x in zoning_lower for x in ["דרך", "דרכים", "כביש", "road", "highway"]):
        duration_months = "18-36"
        start_offset = "6-12" if is_approved else "12-24"
    elif any(x in zoning_lower for x in ["מסחר", "commercial"]):
        duration_months = "12-18"
        start_offset = "3-6" if is_approved else "6-12"
    elif any(x in zoning_lower for x in ["מגורים", "residential"]):
        duration_months = "8-12"
        start_offset = "2-4" if is_approved else "4-8"
    else:
        duration_months = "12-24"
        start_offset = "6-12"
    
    if language == "he":
        if is_in_progress:
            status_text = "התוכנית בביצוע כעת"
            start_text = "כבר התחילה"
        elif is_approved:
            status_text = "התוכנית אושרה"
            start_text = f"צפוי להתחיל בעוד {start_offset} חודשים"
        else:
            status_text = "התוכנית טרם אושרה"
            start_text = f"אם תאושר, יתחיל בעוד {start_offset} חודשים"
        
        return {
            "duration_months": duration_months,
            "start_estimate": start_text,
            "status_interpretation": status_text,
            "confidence": "medium" if is_approved or is_in_progress else "low",
        }
    else:
        if is_in_progress:
            status_text = "Plan is currently in progress"
            start_text = "Already started"
        elif is_approved:
            status_text = "Plan is approved"
            start_text = f"Expected to start in {start_offset} months"
        else:
            status_text = "Plan not yet approved"
            start_text = f"If approved, will start in {start_offset} months"
        
        return {
            "duration_months": duration_months,
            "start_estimate": start_text,
            "status_interpretation": status_text,
            "confidence": "medium" if is_approved or is_in_progress else "low",
        }


def _search_plan_by_number(plan_number: str, bbox: str | None = None) -> dict | None:
    """
    Search for plan across multiple GovMap layers using various strategies.
    
    Strategies:
    1. Search by OBJECTID field
    2. Search by plan number fields (plan_name, pl_num, etc.)
    3. Search by text contains in various fields
    
    Args:
        plan_number: Plan number to search
        bbox: Optional bbox to limit search area
    
    Returns:
        Dict with plan data or None if not found
    """
    plan_number_str = str(plan_number).strip()
    
    # Try different search patterns
    search_patterns = [
        plan_number_str,  # Exact match
        plan_number_str.replace('/', ''),  # Without slash
        re.sub(r'[^\d]', '', plan_number_str),  # Only digits
    ]
    
    for layer_name in GOVMAP_PLAN_LAYERS:
        if not layer_name or not layer_name.strip():
            continue
        layer_name = layer_name.strip()
        
        try:
            params = {
                "service": "WFS",
                "version": "1.1.0",
                "request": "GetFeature",
                "typeName": layer_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "maxFeatures": "100",  # Increased for better search
            }
            
            if bbox:
                params["bbox"] = f"{bbox},EPSG:4326"
            
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=DEFAULT_TIMEOUT)
            
            if resp.status_code != 200:
                continue
            
            content_type = (resp.headers.get("content-type") or "").lower()
            if "json" not in content_type:
                continue
            
            data = resp.json()
            features = data.get("features", []) if isinstance(data, dict) else []
            
            # Search through features
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") or feature.get("attributes") or {}
                
                # Check multiple fields for match
                fields_to_check = [
                    str(props.get("objectid", "")),
                    str(props.get("OBJECTID", "")),
                    str(props.get("plan_name", "")),
                    str(props.get("plan_number", "")),
                    str(props.get("pl_num", "")),
                    str(props.get("mstama", "")),
                    str(props.get("שם", "")),
                ]
                
                # Try to match any pattern against any field
                for pattern in search_patterns:
                    for field_value in fields_to_check:
                        if pattern and field_value and pattern in field_value:
                            return {
                                "feature": feature,
                                "layer": layer_name,
                                "properties": props,
                                "matched_field": field_value,
                                "search_pattern": pattern,
                            }
        
        except Exception:
            continue
    
    return None


def get_detailed_plan_info(plan_number: str, language: str = "he", coordinates: tuple[float, float] | None = None) -> dict:
    """
    Get detailed information about a specific urban plan by plan number.
    
    ENHANCED VERSION: Includes MAVAT links, timeline estimation, better search.
    
    Extracts comprehensive details including status, dates, zoning, and impact analysis.
    This is the implementation of Feature Enhancement #1 from FEATURE_ROADMAP.md.
    
    Args:
        plan_number: Plan number (e.g., "25047", "ג/1234")
        language: Response language ("he" or "en")
        coordinates: Optional (lat, lon) tuple to limit search area
    
    Returns:
        Dict with detailed plan information including:
        - plan_number, name, status
        - zoning/land use (targumyeud)
        - timeline estimation
        - mavat_url (link to official plan)
        - risk_level (high/medium/low)
        - explanation (what this means for residents)
        - raw_attributes (full GovMap data)
    """
    if not plan_number or not str(plan_number).strip():
        return {
            "error": "Plan number is required",
            "plan_number": None,
        }
    
    plan_number = str(plan_number).strip()
    
    # Create bbox if coordinates provided (search within 2km)
    bbox = None
    if coordinates:
        lat, lon = coordinates
        lat_delta = 0.018  # ~2km
        lon_delta = 0.018
        bbox = f"{lon - lon_delta},{lat - lat_delta},{lon + lon_delta},{lat + lat_delta}"
    
    # Enhanced search with multiple strategies
    plan_data = _search_plan_by_number(plan_number, bbox)
    
    if not plan_data:
        return {
            "error": f"Plan {plan_number} not found in GovMap layers",
            "plan_number": plan_number,
            "note": "Plan may exist but is not in the queried area or layers.",
            "suggestion": "Try using coordinates to narrow search, or check MAVAT directly",
            "mavat_url": _construct_mavat_url(plan_number, {}),
        }
    
    # Extract plan details
    props = plan_data["properties"]
    
    # Get zoning/land use with multiple field fallbacks
    zoning = (
        props.get("targumyeud") or 
        props.get("kvuz_trg") or 
        props.get("יעוד") or 
        props.get("zoning") or 
        "לא זמין"
    )
    
    # Get status with multiple field fallbacks
    status = (
        props.get("status") or 
        props.get("סטטוס") or 
        props.get("matav") or 
        "לא ידוע"
    )
    
    # Get plan name with fallbacks
    plan_name = (
        props.get("plan_name") or 
        props.get("name") or 
        props.get("שם") or 
        props.get("shem_tochn") or 
        "לא זמין"
    )
    
    # Analyze risk level based on zoning type
    from guardian_score import explain_plan_risk
    risk_analysis = explain_plan_risk(zoning, language=language)
    
    # Estimate timeline
    timeline = _estimate_timeline_from_status(status, zoning, language)
    
    # Construct MAVAT URL
    mavat_url = _construct_mavat_url(plan_number, props)
    
    # Build comprehensive response
    result = {
        "plan_number": plan_number,
        "name": plan_name,
        "status": status,
        "zoning": zoning,
        "layer": plan_data["layer"].replace("govmap:layer_", ""),
        "risk_level": risk_analysis["risk_level"],
        "explanation": risk_analysis["explanation"],
        "timeline": timeline,
        "mavat_url": mavat_url,
        "matched_field": plan_data.get("matched_field", ""),
        "recommendations": risk_analysis.get("recommendations", []),
        "impact_assessment": {
            "points": risk_analysis["impact_points"],
            "duration": risk_analysis["duration"],
            "noise_level": risk_analysis["noise_level"],
        },
        "raw_attributes": props,
        "note": "Enhanced plan information with timeline and MAVAT link.",
    }
    
    return result


def _extract_plan_info_from_feature(feature: dict, layer_name: str) -> dict | None:
    """
    Extract a single plan/permit info dict from a GovMap WFS/WMS feature.
    GovMap may use plan_name, name, שם, status, סטטוס, number, מספר, etc.
    Returns None if feature has no usable name or number.
    """
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties") or feature.get("attributes") or {}
    plan_name = (
        props.get("plan_name") or props.get("name")
        or props.get("שם") or props.get("תכנית")
    )
    plan_status = (
        props.get("status") or props.get("סטטוס")
        or props.get("plan_status") or props.get("מצב")
    )
    plan_number = (
        props.get("number") or props.get("מספר")
        or props.get("plan_number") or props.get("מס_תכנית") or props.get("objectid")
    )
    if not plan_name and plan_number is None:
        return None
    layer_short = layer_name.replace("govmap:layer_", "") if layer_name else ""
    # Use working MAVAT link (by plan number) instead of broken GovMap url (mmi.gov.il)
    plan_num_str = str(plan_number) if plan_number is not None else None
    url = _construct_mavat_url(plan_num_str or "", props) if plan_num_str else None
    return {
        "name": plan_name,
        "number": plan_num_str,
        "status": plan_status,
        "layer": layer_short,
        "url": url,
        "owner": props.get("owner"),
        "area": props.get("shape_area"),
        "attributes": props,
    }


def _bbox_delta_deg_from_radius_m(latitude: float, radius_m: float) -> tuple[float, float]:
    """
    Convert radius in meters to approximate bbox deltas in degrees (WGS84).
    1 deg lat ≈ 111 km; 1 deg lon ≈ 111 * cos(lat) km.
    """
    import math
    if radius_m <= 0:
        return 0.01, 0.01
    meters_per_deg_lat = 111_000.0
    lat_rad = math.radians(latitude)
    meters_per_deg_lon = 111_000.0 * max(0.1, math.cos(lat_rad))
    lat_delta = radius_m / meters_per_deg_lat
    lon_delta = radius_m / meters_per_deg_lon
    return lat_delta, lon_delta


def _wgs84_to_itm_approx(latitude: float, longitude: float) -> tuple[float, float]:
    """
    Approximate conversion from WGS84 to ITM (Israeli Transverse Mercator, EPSG:2039).
    For production, use pyproj library for accurate transformation.
    """
    import math
    
    # ITM central point
    lat0 = 31.73439361111111
    lon0 = 35.20451694444444
    
    # Convert to radians
    lat_rad = math.radians(latitude)
    dlat = latitude - lat0
    dlon = longitude - lon0
    
    # Simplified ITM conversion (approximation)
    # Real conversion requires ellipsoid parameters and proper projection math
    itm_x = 219529.584 + 111320.702 * dlon * math.cos(lat_rad)
    itm_y = 626907.390 + 110540.0 * dlat
    
    return itm_x, itm_y


def _query_via_geoserver_getfeatureinfo(latitude: float, longitude: float) -> dict:
    """
    Query GovMap GeoServer using GetFeatureInfo (WMS standard).
    Tries multiple coordinate systems and layer name formats.
    """
    plans: list[dict] = []
    permits: list[dict] = []
    
    # Convert coordinates to different systems
    import math
    
    # Web Mercator (EPSG:3857)
    x_merc = longitude * 20037508.34 / 180
    y_merc = math.log(math.tan((90 + latitude) * math.pi / 360)) / (math.pi / 180)
    y_merc = y_merc * 20037508.34 / 180
    
    # ITM (EPSG:2039) - approximate
    itm_x, itm_y = _wgs84_to_itm_approx(latitude, longitude)
    
    # Try different layer name formats
    layer_variants = []
    for base_layer in GOVMAP_PLAN_LAYERS:
        if not base_layer.strip():
            continue
        layer_name = base_layer.strip()
        # Try different formats
        layer_variants.extend([
            layer_name,
            f"govmap:{layer_name}",
            layer_name.replace("govmap:", ""),
        ])
    
    # If no layers configured, try common names
    if not layer_variants:
        layer_variants = ["tabaot", "govmap:tabaot", "retzefmigrashim", "govmap:retzefmigrashim"]
    
    # Try different coordinate systems and layer names
    for layer_name in layer_variants[:6]:  # Limit to avoid too many requests
        # Try ITM first (GovMap likely uses ITM)
        for crs, x, y, bbox_offset in [
            ("EPSG:2039", itm_x, itm_y, 1000),  # ITM, 1km bbox
            ("EPSG:3857", x_merc, y_merc, 500),  # Web Mercator, 500m bbox
            ("EPSG:4326", longitude, latitude, 0.01),  # WGS84, ~1km bbox
        ]:
            try:
                bbox = f"{x-bbox_offset},{y-bbox_offset},{x+bbox_offset},{y+bbox_offset}"
                
                params = {
                    "service": "WMS",
                    "version": "1.3.0",
                    "request": "GetFeatureInfo",
                    "layers": layer_name,
                    "query_layers": layer_name,
                    "x": "10",
                    "y": "10",
                    "width": "20",
                    "height": "20",
                    "bbox": bbox,
                    "crs": crs,
                    "info_format": "application/json",
                    "feature_count": "50",
                }
                
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=10.0)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "").lower()
                        
                        # Check if it's JSON (success) or XML error
                        if "json" in content_type:
                            try:
                                data = resp.json()
                                # Parse GeoJSON or GeoServer response
                                features = []
                                if isinstance(data, dict):
                                    features = data.get("features", [])
                                elif isinstance(data, list):
                                    features = data
                                
                                for feature in features:
                                    plan_info = _extract_plan_info_from_feature(
                                        feature, layer_name
                                    )
                                    if plan_info:
                                        plans.append(plan_info)
                                
                                # If we got features, this method works - return early
                                if features:
                                    return {
                                        "plans": plans,
                                        "permits": permits,
                                        "method_used": "wms_getfeatureinfo",
                                        "features_count": len(features),
                                    }
                            except Exception:
                                # Not JSON, might be XML error - continue to next
                                pass
                        elif "ServiceException" not in resp.text:
                            # Unexpected response - might be HTML or other format
                            pass
            except Exception:
                continue
    
    return {"plans": plans, "permits": permits}


def _query_via_wfs_getfeature(
    latitude: float, longitude: float, radius_m: float | None = None
) -> dict:
    """
    Query via WFS GetFeature (Web Feature Service).
    More reliable for feature queries than GetFeatureInfo.
    When radius_m is set, bbox is built from that radius (Station 3 — spatial mining).
    """
    plans: list[dict] = []
    permits: list[dict] = []
    
    # Use discovered layer names (format: govmap:layer_<name>)
    layer_variants = []
    for base_layer in GOVMAP_PLAN_LAYERS:
        if not base_layer.strip():
            continue
        layer_name = base_layer.strip()
        # Ensure correct format
        if not layer_name.startswith("govmap:layer_"):
            if layer_name.startswith("govmap:"):
                layer_name = layer_name.replace("govmap:", "govmap:layer_")
            else:
                layer_name = f"govmap:layer_{layer_name}"
        layer_variants.append(layer_name)
    
    if not layer_variants:
        # Default discovered layers
        layer_variants = [
            "govmap:layer_tabaot",
            "govmap:layer_retzefmigrashim",
            "govmap:layer_retzefgvulot"
        ]
    
    # Create bbox in WGS84 (from radius_m or default ~1 km)
    if radius_m is not None and radius_m > 0:
        lat_delta, lon_delta = _bbox_delta_deg_from_radius_m(latitude, radius_m)
    else:
        lat_delta = lon_delta = 0.01
    bbox = f"{longitude - lon_delta},{latitude - lat_delta},{longitude + lon_delta},{latitude + lat_delta}"
    
    for layer_name in layer_variants[:4]:  # Limit requests
        try:
            params = {
                "service": "WFS",
                "version": "1.1.0",
                "request": "GetFeature",
                "typeName": layer_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": f"{bbox},EPSG:4326",
                "maxFeatures": "50",
            }
            
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(GOVMAP_GEOSERVER_URL, params=params, timeout=10.0)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "").lower()
                    if "json" in content_type:
                        try:
                            data = resp.json()
                            features = []
                            if isinstance(data, dict):
                                features = data.get("features", [])
                            elif isinstance(data, list):
                                features = data
                            
                            for feature in features:
                                plan_info = _extract_plan_info_from_feature(
                                    feature, layer_name
                                )
                                if plan_info:
                                    plans.append(plan_info)
                            
                            if features:
                                return {
                                    "plans": plans,
                                    "permits": permits,
                                    "method_used": "wfs_getfeature",
                                    "features_count": len(features),
                                }
                        except Exception:
                            pass
        except Exception:
            continue
    
    return {"plans": plans, "permits": permits}


def _query_via_search_service(
    latitude: float, longitude: float, radius_m: float | None = None
) -> dict:
    """Query via GovMap search-service API (known working endpoint)."""
    # Try WFS GetFeature first (most reliable for feature queries)
    result = _query_via_wfs_getfeature(latitude, longitude, radius_m=radius_m)
    if result.get("plans") or result.get("permits"):
        return result
    
    # Try GeoServer GetFeatureInfo (no radius support; uses default bbox)
    result = _query_via_geoserver_getfeatureinfo(latitude, longitude)
    if result.get("plans") or result.get("permits"):
        return result
    
    plans: list[dict] = []
    permits: list[dict] = []
    
    # Fallback: Try search-service with different query patterns
    search_endpoints = [
        f"{GOVMAP_API_BASE}/search-service/search",
        f"{GOVMAP_API_BASE}/search-service/query",
    ]
    
    for search_url in search_endpoints:
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                # Try POST with JSON body
                payload = {
                    "lat": latitude,
                    "lon": longitude,
                    "radius": 1000,  # 1km radius
                }
                resp = client.post(search_url, json=payload, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        # Parse if structure is known
                        if isinstance(data, dict) and "results" in data:
                            # Process results
                            pass
                    except Exception:
                        pass
        except Exception:
            continue
    
    return {"plans": plans, "permits": permits}


def _query_via_govmap_identify(latitude: float, longitude: float) -> dict:
    """
    Query via GovMap identify by coordinates and layers (from API documentation).
    Documentation: govmap.identify() - זיהוי לפי קוארדינטות ושכבות
    """
    plans: list[dict] = []
    permits: list[dict] = []
    
    # From documentation: identify by coordinates and layers
    # Try to find the REST endpoint that the JavaScript API uses
    identify_endpoints = [
        f"{GOVMAP_API_BASE}/identify",
        "https://www.govmap.gov.il/govmap/api/identify",
    ]
    
    # Layer names to query (from discovered layers)
    layer_names = [
        "layer_tabaot",
        "layer_retzefmigrashim", 
        "layer_retzefgvulot"
    ]
    
    for endpoint in identify_endpoints:
        for layer_name in layer_names:
            try:
                # Try POST with coordinates and layer
                payload = {
                    "x": longitude,
                    "y": latitude,
                    "layers": layer_name,
                    "tolerance": 5,
                }
                
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(endpoint, json=payload, headers={"Content-Type": "application/json"})
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            # Parse response (structure depends on actual API)
                            if isinstance(data, dict):
                                results = data.get("results", data.get("data", []))
                                if isinstance(results, list):
                                    for result in results:
                                        if isinstance(result, dict):
                                            # Extract plan info
                                            props = result.get("attributes", result.get("properties", {}))
                                            plan_name = props.get("plan_name") or props.get("name")
                                            if plan_name:
                                                num = props.get("objectid") or props.get("number")
                                                plans.append({
                                                    "name": plan_name,
                                                    "number": num,
                                                    "status": props.get("status"),
                                                    "layer": layer_name,
                                                    "url": _construct_mavat_url(str(num) if num is not None else "", props),
                                                    "attributes": props,
                                                })
                        except Exception:
                            pass
            except Exception:
                continue
    
    return {"plans": plans, "permits": permits}


def _query_via_intersect_features(latitude: float, longitude: float) -> dict:
    """
    Query via GovMap intersectFeatures with WKT geometry (from API documentation).
    Documentation: govmap.intersectFeatures() - חיפוש ישויות בשכבה לפי קואורדינטות
    """
    plans: list[dict] = []
    permits: list[dict] = []
    
    # From documentation: intersectFeatures can use geometry in WKT format
    # WKT Point format: POINT(lon lat)
    wkt_geometry = f"POINT({longitude} {latitude})"
    
    # Try REST endpoints
    intersect_endpoints = [
        f"{GOVMAP_API_BASE}/intersectFeatures",
        "https://www.govmap.gov.il/govmap/api/intersectFeatures",
    ]
    
    layer_names = [
        "layer_tabaot",
        "layer_retzefmigrashim",
    ]
    
    for endpoint in intersect_endpoints:
        for layer_name in layer_names:
            try:
                payload = {
                    "geometry": wkt_geometry,
                    "layerName": layer_name,
                    "fields": ["plan_name", "status", "objectid", "url", "owner"],
                    "getShapes": False,
                }
                
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(endpoint, json=payload, headers={"Content-Type": "application/json"})
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            # Parse response structure from documentation
                            if isinstance(data, dict):
                                results = data.get("data", [])
                                if isinstance(results, list):
                                    for result in results:
                                        if isinstance(result, dict):
                                            # Response has ObjectId and Values array
                                            object_id = result.get("ObjectId")
                                            values = result.get("Values", [])
                                            # Values array corresponds to fields requested
                                            if object_id and values:
                                                attrs = {"ObjectId": object_id, "Values": values}
                                                plans.append({
                                                    "name": values[0] if len(values) > 0 else None,
                                                    "number": str(object_id),
                                                    "status": values[1] if len(values) > 1 else None,
                                                    "layer": layer_name,
                                                    "url": _construct_mavat_url(str(object_id), attrs),
                                                    "attributes": attrs,
                                                })
                        except Exception:
                            pass
            except Exception:
                continue
    
    return {"plans": plans, "permits": permits}


def _query_plans_via_query_endpoint(latitude: float, longitude: float) -> dict:
    """
    Alternative method to query plans via GovMap query endpoint.
    Used as fallback when identify endpoint doesn't work.
    """
    plans: list[dict] = []
    permits: list[dict] = []
    
    try:
        # Try query endpoint with point geometry
        params = {
            "where": "1=1",  # Query all features
            "geometry": f"{longitude},{latitude}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "sr": "4326",
            "f": "json",
            "outFields": "*",
            "returnGeometry": "false",
        }
        
        # Try common plan/permit layer names
        # Note: Actual layer names need to be discovered from GovMap API
        layer_names = [
            "תב\"ע",
            "תכניות בניין עיר",
            "היתרי בנייה",
            "building_permits",
            "urban_plans",
        ]
        
        for layer_name in layer_names:
            try:
                params_with_layer = {**params, "layer": layer_name}
                with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                    resp = client.get(GOVMAP_QUERY_URL, params=params_with_layer)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            features = data.get("features", [])
                            for feature in features:
                                if isinstance(feature, dict):
                                    attrs = feature.get("attributes", {})
                                    if "plan" in layer_name.lower() or "תב" in layer_name:
                                        num = attrs.get("number") or attrs.get("מספר")
                                        plans.append({
                                            "name": attrs.get("name") or attrs.get("שם"),
                                            "number": num,
                                            "status": attrs.get("status") or attrs.get("סטטוס"),
                                            "layer": layer_name,
                                            "url": _construct_mavat_url(str(num) if num is not None else "", attrs),
                                            "attributes": attrs,
                                        })
                                    elif "permit" in layer_name.lower() or "היתר" in layer_name:
                                        permits.append({
                                            "name": attrs.get("name") or attrs.get("שם"),
                                            "number": attrs.get("number") or attrs.get("מספר"),
                                            "status": attrs.get("status") or attrs.get("סטטוס"),
                                            "layer": layer_name,
                                            "attributes": attrs,
                                        })
                        except Exception:
                            continue
            except Exception:
                continue
    
    except Exception:
        pass
    
    if not plans and not permits:
        return {
            "plans": [],
            "permits": [],
            "note": "GovMap API query endpoints not accessible or layer names not configured. "
                    "Please configure GOVMAP_PLAN_LAYERS and GOVMAP_PERMIT_LAYERS environment variables.",
        }
    
    return {
        "plans": plans,
        "permits": permits,
        "note": f"Found {len(plans)} plans and {len(permits)} permits from GovMap query API.",
    }
