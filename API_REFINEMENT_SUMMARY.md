# GovMap Plans API Refinement Summary

## What Was Refined

### 1. Multiple Query Strategies
The implementation now tries **4 different approaches** in order:

1. **WFS GetFeature** (Primary)
   - Most reliable for feature queries
   - Uses standard OGC WFS protocol
   - Queries with WGS84 bbox

2. **WMS GetFeatureInfo** (Secondary)
   - Tries 3 coordinate systems: ITM, Web Mercator, WGS84
   - Tests multiple layer name formats
   - Includes coordinate transformation

3. **ArcGIS Identify** (Tertiary)
   - Multiple endpoint variations
   - ArcGIS REST API patterns

4. **Search-Service** (Fallback)
   - Known working endpoint structure

### 2. Coordinate Transformation
- Added `_wgs84_to_itm_approx()` function
- Tries queries in multiple coordinate systems
- Handles ITM (EPSG:2039), Web Mercator (EPSG:3857), and WGS84 (EPSG:4326)

### 3. Layer Name Variants
- Tests with/without `govmap:` namespace
- Tries discovered layer names: `tabaot`, `retzefmigrashim`
- Configurable via environment variables

### 4. Better Error Handling
- Graceful fallback between methods
- Continues trying if one method fails
- Returns helpful error messages

## Code Structure

```python
query_plans_at_coordinates(lat, lon)
  ├─> _query_via_search_service()
  │   ├─> _query_via_wfs_getfeature()      # Primary
  │   ├─> _query_via_geoserver_getfeatureinfo()  # Secondary
  │   └─> search-service API attempts       # Fallback
  └─> _query_via_arcgis_identify()        # Alternative
```

## Testing Results

✅ **Geocoding**: Fully working with Hebrew addresses
⚠️ **Plans API**: Framework complete, endpoints need discovery

## Next Steps for Full Functionality

1. **Inspect Network Traffic**
   - Open GovMap website
   - Enable browser DevTools → Network tab
   - Click on a location with plans visible
   - Find the actual API call that retrieves plan data
   - Note: URL, parameters, headers, request body

2. **Identify Correct Layer Names**
   - Check the layers catalog response
   - Find the exact `serviceLayerId` or layer identifier
   - Test with those exact identifiers

3. **Check Authentication Requirements**
   - Some endpoints may require API keys
   - Check for authentication headers in network requests
   - May need to register for API access

4. **Test with Known Working Coordinates**
   - Use coordinates where plans are definitely visible on GovMap
   - Test queries with those exact coordinates
   - Compare results with what's shown on the map

## Environment Variables

You can configure layer names:

```bash
export GOVMAP_PLAN_LAYERS="tabaot,retzefmigrashim"
export GOVMAP_PERMIT_LAYERS="permits_layer_name"
```

## Current Implementation Status

- ✅ Framework: Complete with multiple strategies
- ✅ Error Handling: Robust with fallbacks
- ✅ Coordinate Systems: Multiple transformations attempted
- ⚠️ Endpoint Discovery: Needs actual API endpoint identification
- ⚠️ Layer Names: Needs exact layer identifiers from GovMap

The code is production-ready in structure - it just needs the correct endpoint URLs and layer names to be discovered from the actual GovMap website.
