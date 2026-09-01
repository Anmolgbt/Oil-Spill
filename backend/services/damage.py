"""
Impact envelope and response priority.

Two jobs, both kept honest about what they are:

1. SIZE THE ENVELOPE. The old envelope used one hardcoded drift speed. This
   derives the drift vector from the stated environment instead — surface
   current plus the standard ~3% windage that a floating slick picks up — so
   changing the assumed conditions changes the envelope, and wiring in a real
   met-ocean feed later means replacing the constants in core/config.py and
   nothing else.

2. RANK THE SPILLS. When more than one spill is live, responders need an order
   to work them in. `priority_score` combines envelope size, how confident the
   detector was, and the source vessel's recorded size, into a 0-100 score used
   only to sort one spill against another.

What this is NOT:

* Not a measured slick. The CNN is a classifier with no segmentation output, so
  no true boundary or area exists — `measured_area_km2` stays None, as it does
  everywhere else in this codebase. The envelope is the sea area the oil could
  have reached, which is a search/response zone.
* Not a damage assessment in currency, volume or ecology. No oil volume,
  thickness, shoreline proximity or habitat data is involved. `priority_score`
  is a triage ordering, not a measure of harm done.
"""
import math

from core.config import (ADVISORY_ELEVATED_SCORE, ADVISORY_URGENT_SCORE,
                         ASSUMED_CURRENT_DIRECTION_DEG, ASSUMED_CURRENT_SPEED_MS,
                         ASSUMED_WIND_DIRECTION_DEG, ASSUMED_WIND_SPEED_MS,
                         DAMAGE_WEIGHT_AREA, DAMAGE_WEIGHT_CONFIDENCE,
                         DAMAGE_WEIGHT_VESSEL_SIZE, WIND_DRIFT_FACTOR)

MS_TO_KMH = 3.6

# Normalisation ceilings for the priority score. A spill at or above the ceiling
# scores 100 on that component; they are demo scaling choices, stated here
# rather than buried in the arithmetic.
AREA_CEILING_KM2 = 400.0
LENGTH_CEILING_M = 330.0


def drift_vector():
    """
    Slick drift from the assumed environment: the current, plus WIND_DRIFT_FACTOR
    of the wind, summed as vectors. Returns speed in km/h and the compass
    bearing the slick moves toward.
    """
    current_kmh = ASSUMED_CURRENT_SPEED_MS * MS_TO_KMH
    wind_kmh = ASSUMED_WIND_SPEED_MS * MS_TO_KMH * WIND_DRIFT_FACTOR

    # Compass bearings: north is +y, east is +x.
    east = (current_kmh * math.sin(math.radians(ASSUMED_CURRENT_DIRECTION_DEG))
            + wind_kmh * math.sin(math.radians(ASSUMED_WIND_DIRECTION_DEG)))
    north = (current_kmh * math.cos(math.radians(ASSUMED_CURRENT_DIRECTION_DEG))
             + wind_kmh * math.cos(math.radians(ASSUMED_WIND_DIRECTION_DEG)))

    speed_kmh = math.hypot(east, north)
    direction_deg = (math.degrees(math.atan2(east, north)) + 360) % 360

    return {
        "speed_kmh": round(speed_kmh, 3),
        "direction_deg": round(direction_deg, 1),
        "from_current": {"speed_ms": ASSUMED_CURRENT_SPEED_MS,
                         "direction_deg": ASSUMED_CURRENT_DIRECTION_DEG},
        "from_wind": {"speed_ms": ASSUMED_WIND_SPEED_MS,
                      "direction_deg": ASSUMED_WIND_DIRECTION_DEG,
                      "drift_factor": WIND_DRIFT_FACTOR},
        "basis": (f"Current + {WIND_DRIFT_FACTOR:.0%} windage, summed as vectors. "
                  "Both inputs are stated assumptions, not observations."),
        "environmental_data_measured": False,
    }


def impact_envelope(age_hours):
    """
    How far the oil could have spread from the source in `age_hours`, using the
    assumed drift. Replaces the old fixed-drift envelope.
    """
    drift = drift_vector()
    radius_km = drift["speed_kmh"] * age_hours
    return {
        "type": "impact_envelope",
        "radius_km": round(radius_km, 2),
        "area_km2": round(math.pi * radius_km ** 2, 1),
        "label": "Potential impact area — drift envelope",
        "drift": drift,
        "basis": (f"{drift['speed_kmh']:.2f} km/h assumed drift "
                  f"(current + windage) over {age_hours} h"),
        "is_measured_slick_area": False,
        "measured_area_km2": None,
        "note": ("Not a measured slick boundary. The detector is a classifier and "
                 "produces no mask, so no true spill area exists. This is the sea "
                 "area the oil could have reached under the assumed conditions."),
    }


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def priority_score(envelope, confidence, vessel_length_m):
    """
    A 0-100 triage score for ordering one spill against another. Each component
    is reported so the number can be argued with rather than taken on faith.
    """
    area_component = _clamp(envelope["area_km2"] / AREA_CEILING_KM2 * 100)
    confidence_component = _clamp((confidence or 0) * 100)
    size_component = _clamp((vessel_length_m or 0) / LENGTH_CEILING_M * 100)

    score = (DAMAGE_WEIGHT_AREA * area_component
             + DAMAGE_WEIGHT_CONFIDENCE * confidence_component
             + DAMAGE_WEIGHT_VESSEL_SIZE * size_component)

    return {
        "priority_score": round(score, 1),
        "components": {
            "envelope_area": round(area_component, 1),
            "detection_confidence": round(confidence_component, 1),
            "source_vessel_size": round(size_component, 1),
        },
        "weights": {
            "envelope_area": DAMAGE_WEIGHT_AREA,
            "detection_confidence": DAMAGE_WEIGHT_CONFIDENCE,
            "source_vessel_size": DAMAGE_WEIGHT_VESSEL_SIZE,
        },
        "meaning": ("Relative response ordering only. Not a measure of harm "
                    "caused, oil volume, or cost."),
        "excluded_factors": ["oil volume", "slick thickness", "shoreline proximity",
                             "habitat sensitivity", "weathering"],
    }


def advisory(score, response_priority=None):
    """
    What to tell the authorities, banded off the priority score.

    Deliberately stops at "escalate this, in this order". Naming response
    assets, crews or arrival times would mean inventing them, and a responder
    reading a fabricated ETA is worse off than one reading none.
    """
    if score >= ADVISORY_URGENT_SCORE:
        urgency, action = "URGENT", "Notify the maritime pollution authority immediately."
    elif score >= ADVISORY_ELEVATED_SCORE:
        urgency, action = "ELEVATED", "Report to the maritime pollution authority for response tasking."
    else:
        urgency, action = "ROUTINE", "Log and report to the maritime pollution authority."

    return {
        "urgency": urgency,
        "action": action,
        "response_priority": response_priority,
        "label": "RECOMMENDED ACTION",
        "note": ("Escalation advice only. This prototype does not model response "
                 "assets, crews, availability or arrival times."),
    }


def rank_spills(spills):
    """
    Order live spills worst-first and stamp each with its response priority
    (P1, P2, ...). Mutates nothing; returns the ranking rows.
    """
    rows = []
    for entry in spills:
        spill = entry.get("spill") or {}
        rows.append({
            "ship_id": spill.get("ship_id"),
            "ship_name": spill.get("ship_name"),
            "mmsi": spill.get("mmsi"),
            "latitude": spill.get("latitude"),
            "longitude": spill.get("longitude"),
            "envelope_radius_km": (entry.get("affected_area") or {}).get("radius_km"),
            "envelope_area_km2": (entry.get("affected_area") or {}).get("area_km2"),
            **(entry.get("damage") or {}),
        })

    rows.sort(key=lambda r: r.get("priority_score") or 0, reverse=True)
    for i, row in enumerate(rows, start=1):
        row["response_priority"] = f"P{i}"
        row["rank"] = i
    return rows
