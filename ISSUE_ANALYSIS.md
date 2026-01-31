# Issue Analysis: get_urban_plans Not Working

## Problem Summary
The `get_urban_plans` function returns empty results (0 plans, 0 permits) even though the framework is implemented correctly.

## Root Causes Identified

### 1. ❌ Incorrect Layer Names
**Error**: `Feature type :tabaot unknown`

**What we tried**:
- `tabaot`
- `govmap:tabaot`
- `retzefmigrashim`
- `govmap:retzefmigrashim`

**Solution**: Need to discover actual layer names from:
- WMS GetCapabilities response
- Layers catalog with proper filtering
- GovMap website network inspection

### 2. ❌ Coordinate System Mismatch
**Issue**: GovMap uses ITM (EPSG:2039) internally, but we're querying with WGS84 (EPSG:4326)

**What we tried**:
- WGS84 (EPSG:4326)
- Web Mercator (EPSG:3857)
- ITM approximation (EPSG:2039)

**Solution**: May need proper coordinate transformation library (pyproj)

### 3. ❌ API Endpoint Structure
**Issue**: GovMap may use non-standard OGC services or require authentication

**What we tried**:
- Standard WFS GetFeature
- Standard WMS GetFeatureInfo
- ArcGIS Identify patterns
- Search-service API

**Solution**: Inspect actual GovMap network requests to find real endpoints

### 4. ❌ Query Parameters
**Issue**: Bbox might be wrong, or point-in-polygon query not working

**Current bbox**: `lon-0.01, lat-0.01, lon+0.01, lat+0.01` (~1km radius)

**Solution**: Try larger bbox or different query method

## Testing Commands Created

See `POSTMAN_CURL_COMMANDS.md` for complete list of curl commands to test:

1. **GetCapabilities** - Find all available layers
2. **WFS GetFeature** - Test different layer names
3. **WMS GetFeatureInfo** - Test with different coordinate systems
4. **Layers Catalog** - Get layer metadata
5. **Identify Endpoint** - Point query test

## Next Steps

### Immediate Actions
1. ✅ Created curl commands for Postman testing
2. ⏳ Run GetCapabilities to extract actual layer names
3. ⏳ Test discovered layer names in WFS/WMS queries
4. ⏳ Inspect GovMap website network traffic when clicking on plans

### Investigation Steps
1. **Get Layer Names**:
   ```bash
   curl "https://www.govmap.gov.il/api/geoserver/ows?service=WMS&version=1.3.0&request=GetCapabilities" | grep -i "name\|taba\|plan"
   ```

2. **Test with Real Layer Names**:
   - Use discovered names in WFS queries
   - Try with/without namespace prefix

3. **Check Authentication**:
   - Inspect GovMap website requests
   - Look for API keys, tokens, or session cookies
   - May need to register for API access

4. **Alternative Data Sources**:
   - Check data.gov.il for planning data
   - May have REST API with better documentation

## Expected Resolution

Once we discover:
- ✅ Correct layer names (from GetCapabilities)
- ✅ Correct coordinate system (ITM vs WGS84)
- ✅ Correct endpoint structure (if non-standard)
- ✅ Any authentication requirements

The implementation should work immediately since the framework is complete.

## Files Created

- `POSTMAN_CURL_COMMANDS.md` - Ready-to-use curl commands
- `ISSUE_ANALYSIS.md` - This file
- `govmap_all_layers.txt` - All layer names (if GetCapabilities works)
