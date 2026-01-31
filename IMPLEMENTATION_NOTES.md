# Implementation Notes: GovMap API Integration for Urban Plans

## Summary

Implemented GovMap API integration for querying urban plans and building permits at coordinates. The implementation replaces the TODO stub in `get_urban_plans` with actual GovMap API queries.

## Changes Made

### 1. Enhanced `govmap_client.py`

- Added `query_plans_at_coordinates()` function that queries GovMap API for plans and permits
- Implements multiple query strategies:
  - GovMap search-service API
  - ArcGIS-style identify endpoints
  - Fallback with helpful error messages
- Added helper functions:
  - `_query_via_search_service()` - Uses GovMap search-service API
  - `_query_via_arcgis_identify()` - Uses ArcGIS REST API patterns

### 2. Updated `server.py`

- Modified `_get_urban_plans_impl()` to call `query_plans_at_coordinates()` instead of returning stub
- Updated tool documentation to reflect GovMap API usage
- Imported `query_plans_at_coordinates` from `govmap_client`

## Current Status

✅ **Hebrew Address Geocoding**: Works via Nominatim fallback when GovMap geocoding returns HTML
✅ **Plan Query Framework**: Implemented with multiple query strategies
⚠️ **GovMap Plans API**: Endpoints need to be discovered/configured

## GovMap API Challenge

The GovMap API for querying plans at coordinates is **not publicly documented**. The implementation has been refined to try multiple strategies:

### Refined Query Strategies

1. **WFS GetFeature** (Primary method)
   - Uses Web Feature Service standard
   - Queries with WGS84 bbox
   - Tries multiple layer name formats

2. **WMS GetFeatureInfo** (Secondary method)
   - Tries ITM (EPSG:2039), Web Mercator (EPSG:3857), and WGS84 (EPSG:4326)
   - Tests different layer name formats (with/without namespace)
   - Includes coordinate transformation approximations

3. **ArcGIS Identify** (Fallback)
   - ArcGIS REST API patterns
   - Multiple endpoint variations

4. **Search-Service API** (Fallback)
   - Known working endpoint (getTypes works)
   - Spatial query patterns

### Discovered Information

- **Layer Names Found**: `tabaot` (תב"ע), `retzefmigrashim` (planning sequence)
- **GeoServer Endpoint**: `https://www.govmap.gov.il/api/geoserver/ows`
- **Coordinate Systems**: GovMap uses ITM (EPSG:2039) internally, but accepts WGS84 queries

### Current Limitations

The API endpoints may require:
- Authentication/API keys
- Specific request headers
- Different endpoint structure than standard OGC services
- Layers may not be publicly queryable via these methods

However, the actual endpoints and layer names need to be discovered by:
- Inspecting GovMap web interface network requests when clicking on plans
- Using browser developer tools to find actual API calls
- Configuring layer names via environment variables

## Next Steps

To fully enable plan querying:

1. **Discover API Endpoints**: Use browser developer tools on govmap.gov.il to find the actual API endpoints used when clicking on the map
2. **Identify Layer Names**: Find the layer names for plans (תב"ע) and permits (היתרי בנייה)
3. **Configure Environment Variables**:
   ```bash
   export GOVMAP_PLAN_LAYERS="layer1,layer2"
   export GOVMAP_PERMIT_LAYERS="permit_layer1,permit_layer2"
   export GOVMAP_IDENTIFY_URL="https://actual-endpoint.govmap.gov.il/identify"
   ```

## Testing

To test the implementation:

```bash
# Install dependencies
uv sync  # or: pip install -r requirements.txt

# Run the MCP server
uv run server.py

# Or test via Python
python3 -c "from server import _get_urban_plans_impl; print(_get_urban_plans_impl(31.795, 34.648))"
```

## Hebrew Address Example

The system now supports Hebrew addresses like "מתחם הסטאר, אשדוד":

1. Geocoding will attempt GovMap first, then fall back to Nominatim
2. Once coordinates are obtained, `get_urban_plans` will query GovMap API
3. Results include plans and permits (when API endpoints are configured)

## Architecture

```
User Query (Hebrew Address)
    ↓
geocode_address() → Nominatim/GovMap → Coordinates
    ↓
get_urban_plans() → query_plans_at_coordinates() → GovMap API
    ↓
Returns: {plans: [...], permits: [...], note: "..."}
```

## Notes

- The implementation gracefully handles API unavailability
- Returns helpful error messages when endpoints aren't configured
- Framework is ready - just needs correct API endpoint discovery
- All existing tests should still pass (they expect the structure, not specific data)
