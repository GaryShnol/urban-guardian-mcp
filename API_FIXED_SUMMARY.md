# GovMap Plans API - FIXED! ✅

## Problem Solved

The `get_urban_plans` function was not working because:
1. ❌ Wrong layer name format (tried `tabaot`, should be `govmap:layer_tabaot`)
2. ❌ Wrong endpoint (tried `/geoserver/wfs`, correct is `/api/geoserver/ows`)

## Solution Discovered

### ✅ Working API Configuration

**Endpoint**: `https://www.govmap.gov.il/api/geoserver/ows`  
**Method**: WFS GetFeature  
**Layer Format**: `govmap:layer_<name>` (NOT `govmap:<name>`)

### ✅ Working Layer Names

| Layer | ID | Description |
|-------|-----|-------------|
| `govmap:layer_tabaot` | 186 | תב"עות - נתיבי ישראל |
| `govmap:layer_retzefmigrashim` | 11 | רצף מגרשי תב"ע - רמ"י |
| `govmap:layer_retzefgvulot` | 357 | רצף גבולות תב"ע - רמ"י |

## Test Results

✅ **SUCCESS**: Found 1 plan at Dizengoff 100, Tel Aviv
- Name: תתל/33
- Number: 3828
- Status: בתהליך
- URL: http://www.mmi.gov.il/iturtabot/taba4.asp?msHasava=0

## Updated Code

1. ✅ Fixed layer names in `GOVMAP_PLAN_LAYERS`
2. ✅ Updated `_query_via_wfs_getfeature()` to use correct format
3. ✅ Improved parsing to extract `plan_name`, `status`, `url`, etc.
4. ✅ Added proper field mapping from GovMap response

## cURL Commands for Postman

See `POSTMAN_CURL_COMMANDS.md` for ready-to-use curl commands.

### Quick Test:
```bash
curl "https://www.govmap.gov.il/api/geoserver/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=govmap:layer_tabaot&outputFormat=application/json&srsName=EPSG:4326&bbox=34.765,32.080,34.785,32.100,EPSG:4326&maxFeatures=50"
```

## Response Structure

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "plan_name": "תתל/33",
        "status": "בתהליך",
        "objectid": 3828,
        "url": "http://www.mmi.gov.il/iturtabot/taba4.asp?msHasava=0",
        "owner": "67809",
        "shape_area": 12345.67
      },
      "geometry": {...}
    }
  ]
}
```

## Status

🎉 **API IS NOW FULLY WORKING!**

The `get_urban_plans` function now:
- ✅ Queries correct GovMap endpoints
- ✅ Uses correct layer names
- ✅ Parses responses correctly
- ✅ Returns plan data with name, status, number, URL
