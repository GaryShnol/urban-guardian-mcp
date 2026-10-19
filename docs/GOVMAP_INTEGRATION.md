# GovMap API Integration — Reference & Improvement Notes

**Note:** Official GovMap API docs at `https://api.govmap.gov.il/docs` may return *Access Denied*. This document is the **in-repo reference** for endpoints, layer names, and response shapes discovered from the codebase and live testing.

---

## 1. Base URLs & Endpoints

| Purpose | URL | Method | Notes |
|--------|-----|--------|--------|
| **Geocoding (search)** | `https://www.govmap.gov.il/Searching/SearchRest.ashx` | GET `?query=<encoded>` | Configurable via `GOVMAP_SEARCH_URL`. May return HTML; fallback: Nominatim (Israel). |
| **GeoServer OGC** | `https://www.govmap.gov.il/api/geoserver/ows` | GET (WFS/WMS params) | **Primary** for WFS GetFeature, WMS GetFeatureInfo. Same base for all spatial queries. |
| **Layers catalog** | `https://www.govmap.gov.il/api/layers-catalog/catalog` | GET | Full catalog (JSON); used to discover layer IDs and `serviceLayerId`. |
| **Identify (doc)** | `https://www.govmap.gov.il/api/identify` | POST (JSON body) | Documented as JS API; REST equivalent not confirmed. |
| **Query (doc)** | `https://www.govmap.gov.il/api/query` | GET (ArcGIS-style params) | Alternative query; layer names may differ. |
| **Search-service** | `https://www.govmap.gov.il/api/search-service/getTypes` | POST/GET | Used in integration tests; returns search types (JSON). |

**Base:** `GOVMAP_API_BASE = https://www.govmap.gov.il/api`  
**GeoServer (WFS/WMS):** `GOVMAP_GEOSERVER_URL = https://www.govmap.gov.il/api/geoserver/ows`

---

## 2. Layer Names (Discovered)

### 2.1 Plan & planning layers (תב"ע, רצף מגרשים)

| Layer ID (catalog) | serviceLayerId (WFS typeName) | Description |
|--------------------|-------------------------------|-------------|
| 186 | `govmap:layer_tabaot` | תב"עות — נתיבי ישראל |
| 11 | `govmap:layer_retzefmigrashim` | רצף מגרשי תב"ע — רמ"י |
| 357 | `govmap:layer_retzefgvulot` | רצף גבולות תב"ע |

**Env:** `GOVMAP_PLAN_LAYERS` (comma-separated). Default: `govmap:layer_tabaot,govmap:layer_retzefmigrashim,govmap:layer_retzefgvulot`.

**WFS format:** Always use `govmap:layer_<name>` (e.g. `govmap:layer_tabaot`), not `govmap:tabaot`.

### 2.2 Cadastral layers (גוש/חלקה)

| Layer name | serviceLayerId | Description |
|------------|-----------------|-------------|
| parcel_all | `govmap:layer_parcel_all` | חלקות (גוש + חלקה) |
| parcel_ownership_new | `govmap:layer_parcel_ownership_new` | סוג בעלות בחלקות רשומות |
| sub_gush_all | `govmap:layer_sub_gush_all` | גושים |
| sub_gush | `govmap:layer_sub_gush` | גושים מבוססי קואורדינטות |

**Env:** `GOVMAP_CADASTRAL_LAYERS`. Default includes all four above.

**Attribute keys (possible):** `gush`, `GUSH`, `גוש`, `helka`, `HELKA`, `חלקה`, `block`, `parcel`.

### 2.3 Permit layers (היתרי בנייה)

**Env:** `GOVMAP_PERMIT_LAYERS` — comma-separated. Default empty (no dedicated permit layer name in catalog snippet).

### 2.4 Multi-radius search (layer-based radii)

No "one size fits all" — layers of influence for real-estate and urban planning:

| Circle / Layer | Radius (m) | Purpose |
|----------------|------------|---------|
| **Bedroom** (מעגל מיידי) | 50 | Lot + immediate neighbours — TAMA 38/2, balcony, noise/dust, privacy. |
| **Construction permits** (היתרי בנייה) | 100 | Bulldozers under the window. |
| **Hazards** (מפגעים) | 200 | High voltage — safety buffer. |
| **Lifestyle** (מעגל שכונה) | 300 | Neighborhood character — towers, schools, commercial. |
| **Urban plans** (תב"ע) | 500 | Large plan at 500 m still affects the neighborhood. |
| **Value** (מעגל תשתית) | 800 | Metro, interchanges; >800 m = less relevant daily. |
| **Transport** | 1000 | Proximity to rail is an advantage even at 10 min walk. |

Constants in `govmap_client`: `RADIUS_BEDROOM_M`, `RADIUS_PERMITS_M`, `RADIUS_HAZARDS_M`, `RADIUS_LIFESTYLE_M`, `RADIUS_PLANS_M`, `RADIUS_VALUE_M`, `RADIUS_TRANSPORT_M`. Default presets: `MULTI_RADIUS_PRESETS` (50, 100, 300, 500, 800). Tool: `get_multi_radius_search(lat, lon)`.

---

## 3. Request/Response Details

### 3.1 WFS GetFeature (plans & cadastral)

- **Service:** `WFS`, **Version:** `1.1.0`, **Request:** `GetFeature`
- **typeName:** e.g. `govmap:layer_tabaot`
- **outputFormat:** `application/json`
- **srsName:** `EPSG:4326`
- **bbox:** `minLon,minLat,maxLon,maxLat,EPSG:4326` (WGS84, lon/lat order)
- **maxFeatures:** e.g. `50`

**Response:** GeoJSON-like `FeatureCollection`: `{ "type": "FeatureCollection", "features": [ { "type": "Feature", "properties": { ... }, "geometry": { ... } } ] }`.

**Plan/permits properties (typical):** `plan_name`, `name`, `שם`, `status`, `סטטוס`, `number`, `מספר`, `plan_number`, `objectid`, `url`, `owner`, `shape_area`.

### 3.2 Geocoding (SearchRest.ashx)

- **GET** `?query=<URL-encoded address>`
- Response shape: may be JSON with `results`/`data`/`SearchResults`/`FeatureCollection`; or HTML (then we fallback to Nominatim).

---

## 4. Improvement Checklist (Code & Product)

### 4.1 Reliability & observability

- [ ] **Structured last-error:** When all cadastral or plan methods fail, return a short `last_error` or append to `note` (e.g. "WFS returned 0 features; Identify returned 404") so clients can debug.
- [ ] **Optional logging:** Add a debug/log mode (e.g. env `GOVMAP_DEBUG=1`) to log requested URLs and response status/length (no sensitive data).
- [ ] **Timeout consistency:** Use a single constant for GeoServer/WFS timeouts (e.g. 10s) and document it.

### 4.2 Response richness

- [ ] **Metadata in responses:** Include `query_bbox` (used bbox), `layers_queried` (list of layer names tried), `method_used` (e.g. `wfs_getfeature`), `features_count` where relevant.
- [ ] **radius_m in plans response:** When `query_plans_at_coordinates(..., radius_m=...)` is used, add `radius_m_used` to the returned dict.
- [ ] **Cadastral:** Optionally return `features_count` and `layer` that produced gush/helka (already partially there).

### 4.3 Code quality

- [ ] **DRY plan extraction:** Single helper `_extract_plan_info_from_feature(feature, layer_name)` used by both WFS and GetFeatureInfo code paths; same field mapping in one place.
- [ ] **Validate WFS response:** If GeoServer returns XML `ServiceException`, detect it (e.g. check `content-type` or first bytes) before parsing as JSON to avoid misleading errors.
- [ ] **Shared HTTP client:** Consider one `httpx.Client` (or a small client factory) for GovMap requests to reuse connections (respect timeout and connection limits).

### 4.4 Configuration & docs

- [ ] **Env summary in README:** Document all `GOVMAP_*` env vars (search URL, plan layers, cadastral layers, permit layers, optional debug).
- [ ] **Link this doc:** From README and from `govmap_client.py` module docstring, link to `docs/GOVMAP_INTEGRATION.md` as the GovMap reference.

### 4.5 API coverage (when docs available)

- [ ] **Identify REST:** If GovMap exposes a REST equivalent to `identify()`, use it for point-in-polygon cadastral/plans and align parameters with docs.
- [ ] **Permit layers:** Once official layer names for היתרי בנייה are known, set `GOVMAP_PERMIT_LAYERS` default and add to this table.
- [ ] **Rate limits / ToS:** If GovMap publishes rate limits or terms of use, document and optionally add client-side throttling.

---

## 5. Related Repo Files

| File | Content |
|------|--------|
| `govmap_client.py` | All GovMap HTTP calls, parsing, fallbacks |
| `FIXES_APPLIED.md` | WFS as primary method, layer name fixes |
| `POSTMAN_CURL_COMMANDS.md` | cURL examples for WFS plans |
| `DISCOVERED_LAYERS_ANALYSIS.md` | Catalog structure, WFS endpoint notes |
| `catalog_full.json` | Full GovMap catalog (layer IDs, serviceLayerId, captions). Not committed (third-party data); regenerate locally if needed. |

---

*Last updated from codebase review. When official GovMap API documentation is accessible, align this document with it.*
