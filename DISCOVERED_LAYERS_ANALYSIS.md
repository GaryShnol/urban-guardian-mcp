# Discovered Layers Analysis

## Key Findings

### 1. Catalog Structure
The catalog is a dictionary with:
- `services`: Array of service definitions
- `catalog`: Array of layer definitions

### 2. Discovered Plan Layers

From catalog analysis, found these plan-related layers:

1. **retzefmigrashim** (ID: 11)
   - Caption: "רצף מגרשי תב"ע - רמ"י"
   - Service ID: 4 (public service)

2. **tabaot** (ID: 186)
   - Caption: "תב"עות - נתיבי ישראל"
   - Service ID: 4 (public service)

### 3. Service Endpoints

From services structure (ID 4 = public):
- WFS: `//geoserver/wfs?service=wfs&version=1.1.0`
- WMS: `/geoserver/ows/public/`

**Note**: These are relative URLs. Full URLs would be:
- `https://www.govmap.gov.il/geoserver/wfs`
- `https://www.govmap.gov.il/geoserver/ows/public/`

### 4. Layer Name Format

From network requests:
- Format: `govmap:layer_name` (e.g., `govmap:group_mmi`)
- But WFS might use just `layer_name` without prefix

## Testing Results

### Current Status
- ❌ `govmap:tabaot` - Layer not found
- ❌ `tabaot` - Layer not found  
- ❌ `govmap:retzefmigrashim` - Layer not found
- ❌ `retzefmigrashim` - Layer not found

### Possible Issues
1. Wrong WFS endpoint (trying `/api/geoserver/ows` but might need `/geoserver/wfs`)
2. Layer names need different format
3. May need service ID in layer name
4. May require authentication

## Next Steps

1. Test with correct WFS endpoint: `/geoserver/wfs`
2. Try layer names with service ID: `public:tabaot`
3. Check if layers are queryable via WFS (might be WMS-only)
4. Try WMS GetFeatureInfo instead of WFS

## Updated cURL Commands

### Test with correct WFS endpoint:
```bash
curl "https://www.govmap.gov.il/geoserver/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=tabaot&outputFormat=application/json&srsName=EPSG:4326&bbox=34.765,32.080,34.785,32.100,EPSG:4326&maxFeatures=10"
```

### Test with service prefix:
```bash
curl "https://www.govmap.gov.il/geoserver/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=public:tabaot&outputFormat=application/json&srsName=EPSG:4326&bbox=34.765,32.080,34.785,32.100,EPSG:4326&maxFeatures=10"
```
