# Urban Guardian (Israel) — Project Overview

**Use as:** A System Prompt or Project Overview for any AI, or as canonical project documentation.

---

## Project Name
**Urban Guardian (Israel)**

## Objective
A **Model Context Protocol (MCP) server** that provides real-time urban planning, construction permits, and real estate insights for any address in Israel by connecting directly to official government spatial databases.

---

## Phase 1: Geographic Foundation (The "Where")

The first layer translates human-readable addresses into standardized geographic data.

| Aspect | Detail |
|--------|--------|
| **Engine** | GovMap Geocoding API |
| **Input** | Street address and city (e.g. "HaYarkon 10, Tel Aviv") |
| **Logic** | Fuzzy search for Hebrew/English address strings; conversion of local Israeli coordinates (ITM) to global **WGS84** (Lat, Lon) |
| **Output** | Precise coordinates and standardized address metadata |
| **Status** | ✅ Functional |

---

## Phase 2: Cadastral & Planning Integration (The "What")

Once coordinates are established, the system identifies the legal and planning framework of the specific plot.

| Aspect | Detail |
|--------|--------|
| **Data Sources** | GovMap Cadastral Layers & ArcGIS Planning Server (ags.teun.co.il) |
| **Key Operations** | **Legal Identity**: Block (גוש) and Parcel (חלקה) numbers |
| | **Zoning (תב"ע)**: Active zoning plans overlapping the coordinates |
| | **Permit Tracking**: Recent building permit applications (active, approved, or pending) |
| **Outcome** | A complete technical profile of the land's legal and planning status |
| **Status** | 🛠️ In Integration |

---

## Phase 3: Urban Intelligence & Risk Analysis (The "So What")

The AI-driven layer that interprets raw data into human impact reports.

| Contextual Analysis | Description |
|---------------------|-------------|
| **Construction Nuisance** | Distance between the user's location and active building permits |
| **Future Value** | "In Deposit" (בהפקדה) plans indicating gentrification or urban renewal (TAMA 38 / Pinui Binui) |
| **View Analysis** | Building heights from new plans vs. existing views (obstruction risk) |
| **Outcome** | Plain-language report: risks (noise, dust, blocked views) and opportunities (increased rights, price appreciation) |
| **Status** | 📋 Logic Definition |

---

## Phase 4: Environmental & Infrastructure (The "Environment")

The final layer assessing life-quality factors.

| Aspect | Detail |
|--------|--------|
| **Proximity Checks** | Distance to Light Rail (Metropolitan project), high-voltage power lines, public institutions, noise-polluted zones |
| **Risk Mapping** | Flood-prone areas or seismic sensitivity (government geological surveys) |
| **Status** | 🚀 Planned |

---

## Technical Implementation Flow

| Tool | Flow | Description |
|------|------|-------------|
| **geocode_address** | User provides location → API returns **Lat, Lon** (WGS84) |
| **get_cadastral_data** | Lat, Lon → Returns **Block (Gush) / Parcel (Helka)** |
| **get_urban_plans** | Lat, Lon → Returns active/pending **plans and permits** from ArcGIS |
| **generate_guardian_report** | AI synthesizes all data → **Bilingual (Hebrew/English) advisory report** |

---

## How to Use This Project with Claude (or any AI)

**User request example:** *"Analyze the development potential of HaYarkon 10, Tel Aviv."*

| Step | Action |
|------|--------|
| **Step 1** | AI calls `geocode_address` → get Lat, Lon. |
| **Step 2** | AI calls `get_cadastral_data` (Lat, Lon) → get Block/Parcel. |
| **Step 3** | AI calls `get_urban_plans` (Lat, Lon) → get plans & permits. |
| **Step 4** | AI calls `generate_guardian_report` (or synthesizes) → bilingual risk/opportunity report. |

---

## End-to-End (E2E) Project Specification

### 1. Project Mission

To provide a **"Single Source of Truth"** for Israeli real estate by translating complex, fragmented government spatial data into a clear, actionable **Risk & Opportunity Report** for citizens.

### 2. The E2E Test Scenario: "The Concerned Homebuyer"

**User Query:**

> "I am looking at an apartment on 22 HaNevi'im St, Jerusalem. What should I know about the next 5 years in this area?"

**Automated Workflow:**

| Step | Technical Action | Data Source | Expected Result |
|------|------------------|-------------|-----------------|
| 1 | Geocoding | GovMap API | Convert text to coordinates: **31.784, 35.221**. |
| 2 | Cadastral Identification | GovMap Layers | Identify Legal ID: **Block 30050, Parcel 45**. |
| 3 | Spatial Planning Query | ArcGIS (Planning) | Discover an "Urban Renewal" plan on the adjacent plot. |
| 4 | Permit Analysis | ArcGIS (Permits) | Find an active permit for Light Rail infrastructure on the street. |

### 3. Intelligence & Interpretation Logic (The "Brain")

The system does not just dump data; it cross-references findings to provide impact analysis:

| Logic | Rule | Trigger |
|-------|------|---------|
| **Proximity Logic** | If a building permit is within **50 meters**, trigger a **"Heavy Noise Warning."** |
| **Elevation Logic** | If a new plan allows for **25 floors** and is located between the user and the coastline/landmark, trigger a **"View Obstruction Warning."** |
| **Timeline Logic** | If a plan is **"In Deposit" (בהפקדה)**, notify the user they have a legal window to file objections. |

### 4. Success Criteria (Definition of Done)

- **Coordinate Precision:** The geocoder must point to the specific building polygon, not just the general street.
- **Contextual Filtering:** The system must ignore irrelevant data (e.g., a permit for a small internal renovation 200m away) and focus on high-impact projects.
- **Actionable Output:** The final report must be delivered in **plain Hebrew/English**, highlighting **Risk vs. Opportunity**.

### 5. Final Expected Output (The Guardian Report)

> **Analysis for 22 HaNevi'im St, Jerusalem:**
>
> - ⚠️ **Noise Alert:** You are on the path of the Light Rail construction. Expect significant road closures and 24/7 infrastructure noise for the next 24 months.
> - 🏙️ **Urban Change:** A 25-story tower (Plan XYZ) has been approved for the plot directly south of you. Your view toward the Old City will be partially blocked.
> - 📈 **Opportunity:** Proximity to the new Light Rail station is expected to increase property value by ~15% upon completion.

---

## GovMap API — Official Documentation Review

### 1. GovMap API Examples (geocode function)

**Source:** [GovMap API Examples — פונקציות חיפוש (Search functions)](https://www.govmap.gov.il/sites/api/index.html)

This page documents the **embed/iframe API** used to integrate GovMap into other sites:

| Function | Description |
|----------|-------------|
| **geocode** | Convert address (keyword) to coordinates. Parameters: **keyword** (address string), **type** (`govmap.geocodeType.FullResult` or `govmap.geocodeType.AccuracyOnly`). |
| **searchAndLocate** | Search and zoom to result on the map. |
| **searchInLayer** | Search within a layer. |

**Usage (JavaScript, from host page):**  
`govmap.geocode({ keyword: "דיזנגוף 100,תל אביב", type: govmap.geocodeType.AccuracyOnly })`  
The map runs in an **iframe**; the host page sends messages to the iframe, and the iframe performs the actual HTTP request to GovMap’s backend. So the **documented** geocode API is **iframe-based**, not a standalone REST URL.

**Implication for Urban Guardian:** Server-side geocoding cannot call this JavaScript API directly. The map app uses an internal **search-service** (e.g. `POST /api/search-service/getTypes` returns search types); the exact **search/geocode** REST endpoint used by the iframe is not publicly documented. Until GovMap exposes a public REST geocode endpoint (or the internal one is discovered and documented), the MCP client uses a **configurable URL** (`GOVMAP_SEARCH_URL`); set it when a working endpoint is available, or use an alternative Israeli geocoding source.

### 2. GovMap API — הקדמה (Introduction)

**Source:** [GovMap API — הקדמה (Introduction)](https://api.govmap.gov.il/docs/intro)

The official GovMap API documentation is in **Hebrew**. Summary relevant to Urban Guardian:

### Integration methods (increasing complexity)

| Method | Description |
|--------|-------------|
| **URL** | Open the map portal with predefined config: focus to coordinates, scale, map type, etc., via URL parameters. |
| **HTML** | Embed the map on another site using parameters in the URL. |
| **JavaScript** | Run advanced functionality in the embedded map via HTML/JS. |

### Critical constraint for Phase 1 (Geocoding)

- **Fields:** The API supports **numeric and text fields in English only** in URLs.
- **Hebrew and special characters:** If a field name or value contains characters that are not URL-safe (e.g. Hebrew, spaces), **URL encoding is required**. Encode the full string (field name, separator `~`, and value) using a standard encoder (e.g. [meyerweb.com/eric/tools/dencoder](http://meyerweb.com/eric/tools/dencoder)); only invalid characters are encoded.

**Implication for Urban Guardian:** Any geocoding implementation that calls GovMap (including `Searching/SearchRest.ashx`) must **encode Hebrew address queries** before sending. The portal itself handles Hebrew in the UI; server-side or MCP calls must apply encoding.

### Documented URL functions (sidebar)

- **התמקדות לפי קואורדינאטות** — Focus by coordinates  
- **הוספת שכבות מידע** — Add information layers  
- **הוספת בועית מידע על גבי המפה** — Add info bubble on the map  

### Appendices

- **נספח א’** — Map server layer names (for cadastral/Phase 4 and layer selection).  
- **נספח ב’** — Enum variable names.

**Note:** The intro does not document a REST search/geocoding endpoint. The [API Examples](https://www.govmap.gov.il/sites/api/index.html) document the **geocode** function as part of the iframe/embed API (keyword + type); the backend REST endpoint used by the iframe is not publicly documented.

---

## Summary

- **Phase 1**: Geographic Foundation (GovMap geocoding, ITM→WGS84) — ✅ Functional  
- **Phase 2**: Cadastral & Planning (Gush/Helka, תב"ע, permits; GovMap + ArcGIS) — 🛠️ In Integration  
- **Phase 3**: Urban Intelligence (construction nuisance, future value, view analysis) — 📋 Logic Definition  
- **Phase 4**: Environmental & Infrastructure (proximity, flood/seismic risk) — 🚀 Planned  
