"""
Guardian Score — Weighted Analysis (ניתוח משוקלל).

Aggregates three vectors into a single "Guardian Score" (0–100) and structured consult:
- Pros (תועלת): proximity to open space, residential stability, cadastral clarity, no nearby permits.
- Risks: construction permits (noise), proposed roads, heavy commercial.
- Status: planning clarity (cadastral identified) or restrictions (preservation — when data exists).

Decision matrix is applied here in code; the same rules are documented in
docs/GUARDIAN_SCORE_MATRIX.md for use as a system prompt by an AI (e.g. Claude).
"""

from __future__ import annotations

# --- Decision matrix constants (tune here or via env) ---
BASE_SCORE = 50
SCORE_MIN, SCORE_MAX = 0, 100

# Pros (add points)
PROS_CADASTRAL_IDENTIFIED = 10  # Increased from 8 (legal clarity)
PROS_NO_PERMITS_100M = 12
PROS_OPEN_SPACE_500M = 8  # Increased from 6
PROS_RESIDENTIAL_500M = 6  # Increased from 4
PROS_DIVERSE_PLANS_500M = 4  # Increased from 3
PROS_METRO_ACCESSIBLE = 15  # 300-800m from metro (high value)
PROS_TAMA_IN_BUILDING = 10  # TAMA 38 in building (value + safety)
PROS_TAMA_NEIGHBORHOOD = 5  # TAMA 38 in neighborhood (area improvement)
PROS_SCHOOL_ACCESSIBLE = 8  # 300-800m (family-friendly)
PROS_SHELTER_NEARBY = 5  # Public shelter (safety)
PROS_HERITAGE_NEARBY = 8  # Heritage site 100-300m (cultural value)

# Risks (subtract points)
RISK_PERMITS_50M = -20  # Increased from -18 (major disruption)
RISK_PERMITS_50_100M = -6
RISK_PROPOSED_ROAD_100M = -10
RISK_PROPOSED_ROAD_500M = -4
RISK_HEAVY_COMMERCIAL_100M = -8  # Increased from -5

# New Risks - Noise & Environment
RISK_NOISE_DAY_HIGH = -15  # >70dB daytime
RISK_NOISE_DAY_MODERATE = -8  # 60-70dB
RISK_NOISE_NIGHT_HIGH = -25  # >60dB nighttime (critical for sleep)
RISK_NOISE_NIGHT_MODERATE = -12  # 50-60dB

# New Risks - Transport (proximity)
RISK_METRO_TOO_CLOSE = -10  # <100m (noise)
RISK_RAILWAY_CLOSE = -12  # 50-200m (noise + vibration)

# New Risks - TAMA & Construction
RISK_TAMA_ADJACENT = -15  # TAMA 38 adjacent <50m (construction noise 2-3 years)

# New Risks - Hazards
RISK_HIGH_VOLTAGE_CLOSE = -30  # <100m (EMF health concern)
RISK_HIGH_VOLTAGE_NEAR = -15  # 100-200m
RISK_HAZARD_SITE = -20  # Environmental hazard site

# New Risks - Conservation
RISK_CONSERVATION_BUILDING = -10  # Building in conservation area (renovation restrictions)
RISK_SCHOOL_TOO_CLOSE = -5  # <100m (noise during school hours)

# Status: no numeric score; affects narrative (clean vs. unidentified vs. restriction)
STATUS_CLEAN = "clean"  # gush/helka identified
STATUS_UNIDENTIFIED = "unidentified"  # no cadastral
STATUS_RESTRICTION = "restriction"  # e.g. preservation (future)


def _plans_in_radius(multi_radius: dict, key: str) -> list[dict]:
    """Get plans list from multi_radius_search result for a preset key."""
    cell = multi_radius.get(key) if isinstance(multi_radius, dict) else {}
    if isinstance(cell, dict):
        return cell.get("plans") or []
    return []


def _permits_in_radius(multi_radius: dict, key: str) -> list[dict]:
    """Get permits list from multi_radius_search result for a preset key."""
    cell = multi_radius.get(key) if isinstance(multi_radius, dict) else {}
    if isinstance(cell, dict):
        return cell.get("permits") or []
    return []


def _get_zoning_labels(plan: dict) -> list[str]:
    """Extract zoning type labels from a plan (kvuz_trg, targumyeud)."""
    att = plan.get("attributes") or plan.get("properties") or {}
    labels = []
    for k in ("kvuz_trg", "targumyeud"):
        v = att.get(k)
        if isinstance(v, str) and v.strip():
            labels.append(v.strip())
    return labels


def _plans_have_zoning(plans: list[dict], *keywords: str) -> bool:
    """True if any plan has any of the given Hebrew keywords in its zoning labels."""
    keywords_lower = [k.lower() for k in keywords]
    for p in plans:
        for label in _get_zoning_labels(p):
            if any(kw in label.lower() for kw in keywords_lower):
                return True
    return False


def _count_plans_with_zoning(plans: list[dict], *keywords: str) -> int:
    """Count plans that have any of the given keywords in zoning."""
    n = 0
    keywords_lower = [k.lower() for k in keywords]
    for p in plans:
        for label in _get_zoning_labels(p):
            if any(kw in label.lower() for kw in keywords_lower):
                n += 1
                break
    return n


def compute_guardian_score(
    cadastral: dict,
    multi_radius: dict,
    noise_data: dict | None = None,
    tama_data: dict | None = None,
    transport_data: dict | None = None,
) -> dict:
    """
    Run the weighted analysis (decision matrix) and return score + vectors.

    Args:
        cadastral: Result from get_cadastral_at_coordinates (gush, helka, note).
        multi_radius: Result from multi_radius_search (bedroom_50m, permits_100m, plans_500m, etc.).
        noise_data: Optional result from query_noise_data_at_coordinates.
        tama_data: Optional result from query_tama_at_coordinates.
        transport_data: Optional result from query_transport_infrastructure_at_coordinates.

    Returns:
        Dict with:
        - guardian_score: int 0–100
        - score_breakdown: { pros_points, risks_points, base, raw_before_clamp }
        - pros: list of short strings (EN) describing positive factors
        - risks: list of short strings (EN) describing risk factors
        - status: "clean" | "unidentified" | "restriction"
        - status_note: short explanation
    """
    pros_points = 0
    risks_points = 0
    pros: list[str] = []
    risks: list[str] = []

    # --- Cadastral (status + pros) ---
    gush = cadastral.get("gush")
    helka = cadastral.get("helka")
    has_cadastral = gush is not None or helka is not None
    if has_cadastral:
        pros_points += PROS_CADASTRAL_IDENTIFIED
        pros.append("Cadastral (gush/helka) identified — planning identity clear.")
        status = STATUS_CLEAN
        status_note = "Parcel is identified in the cadastral registry."
    else:
        status = STATUS_UNIDENTIFIED
        status_note = "Parcel not identified in the data; consider verifying address or coordinates."

    # --- Permits by radius (risks) ---
    perm_50 = _permits_in_radius(multi_radius, "bedroom_50m")
    perm_100 = _permits_in_radius(multi_radius, "permits_100m")
    n50 = len(perm_50)
    n100 = len(perm_100)
    if n50 > 0:
        risks_points += RISK_PERMITS_50M
        risks.append(
            f"Construction permit(s) within ~50 m ({n50}) — possible noise and dust during works."
        )
    if n100 > n50:
        risks_points += RISK_PERMITS_50_100M
        risks.append(
            f"Construction permit(s) between 50–100 m ({n100 - n50}) — some noise risk."
        )
    if n50 == 0 and n100 == 0:
        pros_points += PROS_NO_PERMITS_100M
        pros.append("No construction permits within 100 m — low immediate noise risk.")

    # --- Plans by radius: open space, residential, proposed road, commercial ---
    plans_100 = _plans_in_radius(multi_radius, "permits_100m") or _plans_in_radius(
        multi_radius, "bedroom_50m"
    )
    plans_500 = _plans_in_radius(multi_radius, "plans_500m")

    if _plans_have_zoning(plans_500, "שטח ציבורי פתוח", "שטחים פתוחים"):
        pros_points += PROS_OPEN_SPACE_500M
        pros.append("Open/public space within 500 m — quality of life plus.")
    if _plans_have_zoning(plans_500, "מגורים"):
        pros_points += PROS_RESIDENTIAL_500M
        pros.append("Residential zoning in the area — stable neighborhood character.")
    if len(plans_500) >= 5:
        pros_points += PROS_DIVERSE_PLANS_500M
        pros.append("Multiple plans in 500 m — active planning context.")

    if _plans_have_zoning(plans_100, "דרך מוצעת", "הרחבה"):
        risks_points += RISK_PROPOSED_ROAD_100M
        risks.append("Proposed road or expansion within ~100 m — future works and possible noise.")
    elif _plans_have_zoning(plans_500, "דרך מוצעת", "הרחבה"):
        risks_points += RISK_PROPOSED_ROAD_500M
        risks.append("Proposed road or expansion within 500 m — possible future impact.")
    if _plans_have_zoning(plans_100, "מסחרי", "מסחר"):
        risks_points += RISK_HEAVY_COMMERCIAL_100M
        risks.append("Commercial zoning very close — possible noise and traffic.")

    # --- NEW: Noise Analysis ---
    if noise_data:
        noise_day = noise_data.get("noise_day_db")
        noise_night = noise_data.get("noise_night_db")
        
        if noise_day is not None:
            if noise_day > 70:
                risks_points += RISK_NOISE_DAY_HIGH
                risks.append(f"High daytime traffic noise ({noise_day:.0f} dB) — health concern.")
            elif noise_day > 60:
                risks_points += RISK_NOISE_DAY_MODERATE
                risks.append(f"Moderate daytime traffic noise ({noise_day:.0f} dB).")
        
        if noise_night is not None:
            if noise_night > 60:
                risks_points += RISK_NOISE_NIGHT_HIGH
                risks.append(f"High nighttime noise ({noise_night:.0f} dB) — sleep disruption critical.")
            elif noise_night > 50:
                risks_points += RISK_NOISE_NIGHT_MODERATE
                risks.append(f"Moderate nighttime noise ({noise_night:.0f} dB) — possible sleep impact.")

    # --- NEW: TAMA 38 Analysis ---
    if tama_data:
        if tama_data.get("in_building"):
            pros_points += PROS_TAMA_IN_BUILDING
            pros.append("TAMA 38 in building — earthquake safety + property value increase.")
        elif tama_data.get("adjacent"):
            risks_points += RISK_TAMA_ADJACENT
            risks.append("TAMA 38 adjacent (<50m) — construction noise for 2-3 years.")
        elif tama_data.get("neighborhood"):
            pros_points += PROS_TAMA_NEIGHBORHOOD
            pros.append("TAMA 38 in neighborhood — area improvement and modernization.")

    # --- NEW: Transport Analysis ---
    if transport_data:
        if transport_data.get("metro_nearby"):
            # Determine if too close or accessible
            # Simplified: if metro found, assume accessible range (would need distance calculation)
            pros_points += PROS_METRO_ACCESSIBLE
            pros.append("Metro/light rail nearby (300-800m) — excellent accessibility.")
        
        if transport_data.get("railway_nearby"):
            # Railway typically means noise
            risks_points += RISK_RAILWAY_CLOSE
            risks.append("Railway line nearby (50-200m) — train noise and vibration.")

    # --- Raw score and clamp ---
    raw = BASE_SCORE + pros_points + risks_points
    guardian_score = max(SCORE_MIN, min(SCORE_MAX, int(round(raw))))

    return {
        "guardian_score": guardian_score,
        "score_breakdown": {
            "base": BASE_SCORE,
            "pros_points": pros_points,
            "risks_points": risks_points,
            "raw_before_clamp": raw,
        },
        "pros": pros,
        "risks": risks,
        "status": status,
        "status_note": status_note,
    }


def score_band(score: int) -> str:
    """Return band label for a 0–100 Guardian Score (EN)."""
    if score >= 86:
        return "Excellent"
    if score >= 71:
        return "Very good"
    if score >= 51:
        return "Good"
    if score >= 31:
        return "Moderate"
    return "Low"


def build_consult_text(
    score_result: dict,
    language: str = "en",
    address: str | None = None,
) -> str:
    """
    Build a short consult (2–4 sentences) from the score result.

    language: "en" | "he"
    """
    score = score_result.get("guardian_score", 0)
    band = score_band(score)
    pros = score_result.get("pros") or []
    risks = score_result.get("risks") or []
    status_note = score_result.get("status_note", "")

    if language == "he":
        band_he = {
            "Excellent": "מצוין",
            "Very good": "טוב מאוד",
            "Good": "טוב",
            "Moderate": "בינוני",
            "Low": "נמוך",
        }.get(band, band)
        lines = [
            f"מדד Guardian: {score}/100 — {band_he}.",
            f"מצב תכנוני: {status_note}",
        ]
        if pros:
            lines.append("יתרונות: " + "; ".join(pros[:2]))
        if risks:
            lines.append("סיכונים: " + "; ".join(risks[:2]))
        return " ".join(lines)

    lines = [
        f"Guardian Score: {score}/100 — {band}.",
        status_note,
    ]
    if pros:
        lines.append("Pros: " + "; ".join(pros[:2]))
    if risks:
        lines.append("Risks: " + "; ".join(risks[:2]))
    return " ".join(lines)


def analyze_risks_detailed(risks: list[str], language: str = "he") -> list[dict]:
    """
    Automatically analyze each risk and provide detailed explanation.
    
    Args:
        risks: List of risk descriptions from Guardian Score
        language: Response language
    
    Returns:
        List of dicts with detailed risk analysis
    """
    detailed_risks = []
    
    for risk in risks:
        risk_lower = risk.lower()
        analysis = None
        risk_type = None
        
        # Detect risk type from description
        if any(x in risk_lower for x in ["road", "כביש", "דרך", "הרחב"]):
            risk_type = "שטח לדרכים" if language == "he" else "road"
            analysis = explain_plan_risk(risk_type, language=language)
        elif any(x in risk_lower for x in ["commercial", "מסחר"]):
            risk_type = "מסחר" if language == "he" else "commercial"
            analysis = explain_plan_risk(risk_type, language=language)
        elif any(x in risk_lower for x in ["permit", "היתר", "construction", "בניי"]):
            # Construction/permit risk
            if language == "he":
                analysis = {
                    "risk_level": "high",
                    "impact_points": -18,
                    "duration": "12-24 חודשים",
                    "noise_level": "גבוה",
                    "explanation": "היתר בנייה קרוב מאוד - צפוי רעש בנייה משמעותי, אבק, ותנועת כלי רכב כבדים.",
                    "recommendations": [
                        "ברר את סוג הבניי (מגדל מגורים יקח יותר זמן מבית פרטי)",
                        "שאל בעירייה מתי ההיתר ניתן ומתי צפוי להתחיל",
                        "בקר במקום בשעות בוקר (07:00-08:00) כשהעבודות מתחילות",
                    ],
                }
            else:
                analysis = {
                    "risk_level": "high",
                    "impact_points": -18,
                    "duration": "12-24 months",
                    "noise_level": "high",
                    "explanation": "Building permit very close - expect significant construction noise, dust, and heavy vehicle traffic.",
                    "recommendations": [
                        "Find out the type of construction (tower takes longer than house)",
                        "Ask municipality when permit was issued and when work will start",
                        "Visit in morning hours (07:00-08:00) when work typically starts",
                    ],
                }
        
        if analysis:
            detailed_risks.append({
                "original_risk": risk,
                "risk_type": risk_type,
                "analysis": analysis,
            })
        else:
            # Generic risk without detailed analysis
            detailed_risks.append({
                "original_risk": risk,
                "risk_type": "other",
                "analysis": None,
            })
    
    return detailed_risks


def build_report_text(
    score_result: dict,
    language: str = "en",
    address: str | None = None,
) -> str:
    """
    Build a fuller report paragraph from the score result (for report field).
    """
    score = score_result.get("guardian_score", 0)
    band = score_band(score)
    pros = score_result.get("pros") or []
    risks = score_result.get("risks") or []
    status_note = score_result.get("status_note", "")
    breakdown = score_result.get("score_breakdown") or {}

    if language == "he":
        band_he = {
            "Excellent": "מצוין",
            "Very good": "טוב מאוד",
            "Good": "טוב",
            "Moderate": "בינוני",
            "Low": "נמוך",
        }.get(band, band)
        parts = [
            f"ניתוח משוקלל (Guardian Score): {score}/100 — {band_he}.",
            f"מצב תכנוני: {status_note}",
        ]
        if pros:
            parts.append("יתרונות: " + " ".join(pros))
        if risks:
            parts.append("סיכונים: " + " ".join(risks))
        return " ".join(parts)

    parts = [
        f"Weighted analysis (Guardian Score): {score}/100 — {band}.",
        f"Status: {status_note}",
    ]
    if pros:
        parts.append("Pros: " + " ".join(pros))
    if risks:
        parts.append("Risks: " + " ".join(risks))
    if breakdown:
        parts.append(
            f"(Breakdown: base {breakdown.get('base', 50)} + pros {breakdown.get('pros_points', 0)} + risks {breakdown.get('risks_points', 0)}.)"
        )
    return " ".join(parts)


def build_comprehensive_report(
    score_result: dict,
    detailed_risks: list[dict],
    address: str | None = None,
    language: str = "he",
) -> str:
    """
    Build a comprehensive, formatted report with detailed risk analysis.
    
    Args:
        score_result: Result from compute_guardian_score
        detailed_risks: Result from analyze_risks_detailed
        address: Optional address
        language: Report language
    
    Returns:
        Formatted comprehensive report text
    """
    score = score_result.get("guardian_score", 0)
    band = score_band(score)
    pros = score_result.get("pros") or []
    risks = score_result.get("risks") or []
    breakdown = score_result.get("score_breakdown") or {}
    
    if language == "he":
        band_he = {
            "Excellent": "מצוין",
            "Very good": "טוב מאוד",
            "Good": "טוב",
            "Moderate": "בינוני",
            "Low": "נמוך",
        }.get(band, band)
        
        lines = [
            "╔════════════════════════════════════════════════════════════╗",
            "║           דוח Urban Guardian - ניתוח מקיף                ║",
            "╚════════════════════════════════════════════════════════════╝",
            "",
        ]
        
        if address:
            lines.append(f"📍 כתובת: {address}")
        lines.append(f"🎯 ציון Guardian: {score}/100 - {band_he}")
        lines.append("")
        lines.append("═" * 60)
        lines.append("")
        
        # Score breakdown
        lines.append("📊 פירוט הציון:")
        lines.append(f"   בסיס: {breakdown.get('base', 50)} נקודות")
        lines.append(f"   יתרונות: +{breakdown.get('pros_points', 0)} נקודות")
        lines.append(f"   סיכונים: {breakdown.get('risks_points', 0)} נקודות")
        lines.append(f"   {'─' * 20}")
        lines.append(f"   סה\"כ: {score} נקודות")
        lines.append("")
        lines.append("═" * 60)
        lines.append("")
        
        # Detailed risks
        if detailed_risks:
            lines.append("⚠️  ניתוח סיכונים מפורט:")
            lines.append("")
            for i, risk_detail in enumerate(detailed_risks, 1):
                lines.append(f"{i}. {risk_detail['original_risk']}")
                if risk_detail['analysis']:
                    analysis = risk_detail['analysis']
                    lines.append(f"   🚨 רמת סיכון: {analysis['risk_level'].upper()}")
                    lines.append(f"   📊 השפעה: {analysis['impact_points']} נקודות")
                    lines.append(f"   ⏱️  משך: {analysis['duration']}")
                    lines.append(f"   📢 רעש: {analysis['noise_level']}")
                    lines.append(f"   💬 {analysis['explanation']}")
                    if analysis.get('recommendations'):
                        lines.append(f"   ✅ המלצות:")
                        for j, rec in enumerate(analysis['recommendations'], 1):
                            lines.append(f"      {j}. {rec}")
                lines.append("")
        
        lines.append("═" * 60)
        lines.append("")
        
        # Advantages
        if pros:
            lines.append("✨ יתרונות שזוהו:")
            lines.append("")
            for i, pro in enumerate(pros, 1):
                lines.append(f"✓ {pro}")
            lines.append("")
            lines.append("═" * 60)
            lines.append("")
        
        # Final recommendation
        lines.append("🎯 המלצה סופית:")
        if score >= 80:
            lines.append("   ✅ דירה מומלצת! ציון גבוה, חסרונות מינוריים.")
            lines.append("   💡 כדאי לבדוק את הפרטים בשטח אבל זה נראה מצוין.")
        elif score >= 65:
            lines.append("   ✓ דירה טובה. יש כמה נקודות לתשומת לב.")
            lines.append("   💡 בדוק את הסיכונים בשטח ושקול אם אתה מוכן לחיות איתם.")
        else:
            lines.append("   ⚠️  דירה בינונית. יש בעיות משמעותיות.")
            lines.append("   💡 חשוב היטב או המשך לחפש.")
        
        lines.append("")
        lines.append("╚════════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)
    
    else:
        # English version
        lines = [
            "╔════════════════════════════════════════════════════════════╗",
            "║      Urban Guardian Report - Comprehensive Analysis        ║",
            "╚════════════════════════════════════════════════════════════╝",
            "",
        ]
        
        if address:
            lines.append(f"📍 Address: {address}")
        lines.append(f"🎯 Guardian Score: {score}/100 - {band}")
        lines.append("")
        lines.append("═" * 60)
        lines.append("")
        
        # Score breakdown
        lines.append("📊 Score Breakdown:")
        lines.append(f"   Base: {breakdown.get('base', 50)} points")
        lines.append(f"   Advantages: +{breakdown.get('pros_points', 0)} points")
        lines.append(f"   Risks: {breakdown.get('risks_points', 0)} points")
        lines.append(f"   {'─' * 20}")
        lines.append(f"   Total: {score} points")
        lines.append("")
        lines.append("═" * 60)
        lines.append("")
        
        # Detailed risks
        if detailed_risks:
            lines.append("⚠️  Detailed Risk Analysis:")
            lines.append("")
            for i, risk_detail in enumerate(detailed_risks, 1):
                lines.append(f"{i}. {risk_detail['original_risk']}")
                if risk_detail['analysis']:
                    analysis = risk_detail['analysis']
                    lines.append(f"   🚨 Risk Level: {analysis['risk_level'].upper()}")
                    lines.append(f"   📊 Impact: {analysis['impact_points']} points")
                    lines.append(f"   ⏱️  Duration: {analysis['duration']}")
                    lines.append(f"   📢 Noise: {analysis['noise_level']}")
                    lines.append(f"   💬 {analysis['explanation']}")
                    if analysis.get('recommendations'):
                        lines.append(f"   ✅ Recommendations:")
                        for j, rec in enumerate(analysis['recommendations'], 1):
                            lines.append(f"      {j}. {rec}")
                lines.append("")
        
        lines.append("═" * 60)
        lines.append("")
        
        # Advantages
        if pros:
            lines.append("✨ Advantages Found:")
            lines.append("")
            for i, pro in enumerate(pros, 1):
                lines.append(f"✓ {pro}")
            lines.append("")
            lines.append("═" * 60)
            lines.append("")
        
        # Final recommendation
        lines.append("🎯 Final Recommendation:")
        if score >= 80:
            lines.append("   ✅ Recommended property! High score, minor drawbacks.")
            lines.append("   💡 Worth checking details on-site, but looks excellent.")
        elif score >= 65:
            lines.append("   ✓ Good property. Some points need attention.")
            lines.append("   💡 Check risks on-site and consider if you can live with them.")
        else:
            lines.append("   ⚠️  Fair property. Significant issues present.")
            lines.append("   💡 Think carefully or continue searching.")
        
        lines.append("")
        lines.append("╚════════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)


def explain_plan_risk(zoning: str, language: str = "he") -> dict:
    """
    Explain the risk level and impact of a specific land use/zoning type.
    Helper function for detailed plan information.
    
    Args:
        zoning: Land use type (e.g., "שטח לדרכים", "מגורים", "מסחר")
        language: "he" or "en"
    
    Returns:
        Dict with risk_level, impact points, and explanation
    """
    zoning_lower = str(zoning).lower()
    
    # Roads/Highways (highest risk)
    if any(x in zoning_lower for x in ["דרך", "דרכים", "כביש", "road", "highway"]):
        if language == "he":
            return {
                "risk_level": "high",
                "impact_points": -10,
                "duration": "18-36 חודשים",
                "noise_level": "גבוה",
                "explanation": "תוכנית לדרך או כביש - צפויות עבודות תשתית ממושכות (1.5-3 שנים), רעש משמעותי בשעות היום, תנועה כבדה ופקקים באזור.",
                "recommendations": [
                    "בדוק באתר מינהל התכנון הארצי (מבא\"ת) מתי התוכנית אושרה",
                    "פנה למחלקה להנדסה בעירייה לברר מתי העבודות צפויות להתחיל",
                    "שקול האם תוכל לסבול רעש בנייה למשך 2-3 שנים",
                ],
            }
        return {
            "risk_level": "high",
            "impact_points": -10,
            "duration": "18-36 months",
            "noise_level": "high",
            "explanation": "Road/highway plan - expect prolonged infrastructure work (1.5-3 years), significant daytime noise, heavy traffic and congestion.",
            "recommendations": [
                "Check when the plan was approved on the National Planning Administration website",
                "Contact municipal engineering department for expected start date",
                "Consider if you can tolerate construction noise for 2-3 years",
            ],
        }
    
    # Commercial (medium-high risk)
    if any(x in zoning_lower for x in ["מסחר", "commercial", "מסחרי"]):
        if language == "he":
            return {
                "risk_level": "medium",
                "impact_points": -5,
                "duration": "12-18 חודשים בנייה",
                "noise_level": "בינוני-גבוה",
                "explanation": "תוכנית מסחרית - צפויה עלייה בתנועה ורעש בשעות הפעילות (בדרך כלל 08:00-23:00), קושי בחנייה, אבל גם נוחות ושירותים קרובים.",
                "recommendations": [
                    "ברר איזה סוג מסחר מתוכנן (מסעדות רועשות יותר מחנויות)",
                    "בדוק את שעות הפעילות המתוכננות",
                    "בקר במקום בשעות שונות ביום",
                ],
            }
        return {
            "risk_level": "medium",
            "impact_points": -5,
            "duration": "12-18 months construction",
            "noise_level": "medium-high",
            "explanation": "Commercial plan - expect increased traffic and noise during business hours (typically 08:00-23:00), parking difficulties, but also convenience and nearby services.",
            "recommendations": [
                "Find out what type of commerce is planned (restaurants are noisier than shops)",
                "Check planned operating hours",
                "Visit the location at different times of day",
            ],
        }
    
    # Residential (low risk)
    if any(x in zoning_lower for x in ["מגורים", "residential", "מגורי"]):
        if language == "he":
            return {
                "risk_level": "low",
                "impact_points": 0,
                "duration": "השפעה מינימלית",
                "noise_level": "נמוך",
                "explanation": "תוכנית מגורים - השפעה מינימלית. שכונה יציבה ושקטה. בנייה חדשה תהיה זמנית ובדרך כלל לא מפריעה.",
                "recommendations": [
                    "בדוק סוג המבנים (מגדלים או בתים נמוכים)",
                    "שכונת מגורים היא יתרון ולא חיסרון",
                ],
            }
        return {
            "risk_level": "low",
            "impact_points": 0,
            "duration": "minimal impact",
            "noise_level": "low",
            "explanation": "Residential plan - minimal impact. Stable and quiet neighborhood. New construction will be temporary and usually not disruptive.",
            "recommendations": [
                "Check building types (towers or low-rise)",
                "Residential neighborhood is an advantage, not a disadvantage",
            ],
        }
    
    # Open/Public space (positive!)
    if any(x in zoning_lower for x in ["פתוח", "פארק", "גן", "park", "open", "public"]):
        if language == "he":
            return {
                "risk_level": "positive",
                "impact_points": +8,
                "duration": "יתרון קבוע",
                "noise_level": "נמוך",
                "explanation": "שטח ציבורי פתוח - יתרון משמעותי! פארק או גן ציבורי משפרים איכות חיים, מספקים שטח פעילות, ומעלים ערך נכס.",
                "recommendations": [
                    "בדוק איזה סוג שטח פתוח (פארק עירוני, גן שכונתי)",
                    "זה יתרון גדול - נצל אותו!",
                ],
            }
        return {
            "risk_level": "positive",
            "impact_points": +8,
            "duration": "permanent advantage",
            "noise_level": "low",
            "explanation": "Public open space - significant advantage! Park or public garden improves quality of life, provides activity space, and increases property value.",
            "recommendations": [
                "Check what type of open space (city park, neighborhood garden)",
                "This is a major advantage - take advantage of it!",
            ],
        }
    
    # Unknown/Other
    if language == "he":
        return {
            "risk_level": "unknown",
            "impact_points": 0,
            "duration": "לא ידוע",
            "noise_level": "לא ידוע",
            "explanation": f"ייעוד: {zoning}. לא נמצא מידע ספציפי על סוג ייעוד זה.",
            "recommendations": [
                "פנה לעיריה לקבלת מידע מפורט על תוכנית זו",
                "בדוק באתר מבא\"ת (מינהל התכנון) את מסמכי התוכנית",
            ],
        }
    return {
        "risk_level": "unknown",
        "impact_points": 0,
        "duration": "unknown",
        "noise_level": "unknown",
        "explanation": f"Zoning: {zoning}. No specific information found for this zoning type.",
        "recommendations": [
            "Contact municipality for detailed information about this plan",
            "Check the National Planning Administration website for plan documents",
        ],
    }
