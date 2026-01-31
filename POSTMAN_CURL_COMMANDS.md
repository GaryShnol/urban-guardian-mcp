# Postman cURL Commands for Testing GovMap Plans API

## ✅ WORKING API DISCOVERED!

**Working Endpoint**: `https://www.govmap.gov.il/api/geoserver/ows`  
**Working Layer**: `govmap:layer_tabaot`  
**Method**: WFS GetFeature

## Test Coordinates
- **Address**: דיזינגוף 100, תל אביב
- **Latitude**: 32.0908154
- **Longitude**: 34.7758683

## ✅ Working cURL Commands

### 1. Get Plans (תב"ע) - WORKING ✅

```bash
curl -X GET "https://www.govmap.gov.il/api/geoserver/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=govmap:layer_tabaot&outputFormat=application/json&srsName=EPSG:4326&bbox=34.7658683,32.0808154,34.7858683,32.1008154,EPSG:4326&maxFeatures=50" \
  -H "Accept: application/json"
```

**Expected Response**: JSON with `features` array containing plan data

### 2. Get Planning Sequence (רצף מגרשים) - WORKING ✅

```bash
curl -X GET "https://www.govmap.gov.il/api/geoserver/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=govmap:layer_retzefmigrashim&outputFormat=application/json&srsName=EPSG:4326&bbox=34.7658683,32.0808154,34.7858683,32.1008154,EPSG:4326&maxFeatures=50" \
  -H "Accept: application/json"
```

### 3. Get Plan Boundaries (רצף גבולות) - WORKING ✅

```bash
curl -X GET "https://www.govmap.gov.il/api/geoserver/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=govmap:layer_retzefgvulot&outputFormat=application/json&srsName=EPSG:4326&bbox=34.7658683,32.0808154,34.7858683,32.1008154,EPSG:4326&maxFeatures=50" \
  -H "Accept: application/json"
```

## Layer Names Discovered

| Layer Name | ID | Description |
|------------|-----|-------------|
| `govmap:layer_tabaot` | 186 | תב"עות - נתיבי ישראל |
| `govmap:layer_retzefmigrashim` | 11 | רצף מגרשי תב"ע - רמ"י |
| `govmap:layer_retzefgvulot` | 357 | רצף גבולות תב"ע - רמ"י |

## Response Structure

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "...",
      "geometry": {
        "type": "Polygon",
        "coordinates": [...]
      },
      "properties": {
        "objectid_1": 123,
        "objectid": 456,
        "plan_name": "תכנית בניין עיר 1234",
        "status": "בתוקף",
        "url": "...",
        "owner": "...",
        "createAt": "...",
        "shape_area": 12345.67,
        "shape_length": 123.45
      }
    }
  ]
}
```

## Key Properties

- `plan_name`: Name of the plan (תכנית בניין עיר)
- `status`: Status of the plan (בתוקף, בהפקדה, etc.)
- `url`: Link to plan details
- `owner`: Plan owner/organization
- `shape_area`: Area in square meters
- `shape_length`: Perimeter length

## How to Use in Postman

1. **Import as cURL**: Copy any command above
2. **Create Collection**: "GovMap Plans API"
3. **Test Each Layer**: Run each command and verify responses
4. **Adjust Bbox**: Modify bbox coordinates for different areas

## Testing Different Areas

Change the `bbox` parameter:
- Format: `minLon,minLat,maxLon,maxLat,EPSG:4326`
- Example: `34.765,32.080,34.785,32.100,EPSG:4326` (~1km radius)
- Larger area: `34.75,32.07,34.79,32.11,EPSG:4326` (~2km radius)

## Notes

- ✅ All layers use format: `govmap:layer_<name>` (not `govmap:<name>`)
- ✅ Endpoint: `/api/geoserver/ows` (not `/geoserver/wfs`)
- ✅ Service: WFS (Web Feature Service)
- ✅ Output: JSON format
- ✅ Coordinate system: EPSG:4326 (WGS84)
