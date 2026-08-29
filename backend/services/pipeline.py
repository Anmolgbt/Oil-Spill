"""
The investigation pipeline.

Spill-first, following the problem statement end to end:

    1. newest satellite snapshot
    2. oil model over every ship image      -> spill detected?
    3. characterise                          -> area, location
    4. hindcast                              -> probable origin point + time
    5. historic AIS around that origin       -> irrelevant traffic filtered out
    6. anomaly model + weighted scoring      -> ranked suspects
    7. forward forecast                      -> where the slick goes next

Each step returns its own block so the UI can narrate progress, and the run
stops early with a CLEAR result when no oil is found.

Nothing here contains investigation values of its own; every number comes from a
service, which in DEMO_MODE reads data/demo/pipeline_demo.json and in real mode
will come from the trained models.
"""
from core.config import COMPUTED_PROVENANCE

from .ais_service import find_vessels_near
from .data_store import get_pipeline_demo
from .drift_model import estimate_origin, forecast_from_spill
from .simulation_service import get_ships, get_latest_snapshot, get_snapshot_data
from .spill_detection import characterize, oil_provenance, scan_snapshot
from .vessel_attribution import anomaly_provenance, rank_ships


def pipeline_provenance():
    """
    Where each stage's numbers came from, so a stubbed run is never mistaken for
    a real one. Drift and the AIS filter are genuinely computed in both modes;
    only the two model-backed stages are stubbed while the models are trained.
    """
    return {
        "oil_detection": oil_provenance(),
        "anomaly_detection": anomaly_provenance(),
        "characterization": COMPUTED_PROVENANCE,
        "hindcast": COMPUTED_PROVENANCE,
        "ais_filter": COMPUTED_PROVENANCE,
        "attribution_score": COMPUTED_PROVENANCE,
        "forecast": COMPUTED_PROVENANCE,
    }


def _observed_at(snapshot_id):
    """Acquisition time of a satellite pass."""
    return get_pipeline_demo()["snapshot_times"].get(snapshot_id)


def run_investigation(snapshot_id=None):
    """
    Run the full pipeline over one satellite pass.

    Defaults to the newest snapshot. Returns a dict with one key per step plus a
    top-level `status` of NO_SNAPSHOT, CLEAR or SPILL_CONFIRMED.
    """
    snapshot_id = snapshot_id or get_latest_snapshot()
    if not snapshot_id:
        return {"status": "NO_SNAPSHOT", "message": "No satellite snapshots available.",
                "provenance": pipeline_provenance()}

    snapshot = get_snapshot_data(snapshot_id)
    if snapshot is None:
        return {"status": "NO_SNAPSHOT", "message": f"Unknown snapshot {snapshot_id}.",
                "provenance": pipeline_provenance()}

    observed_at = _observed_at(snapshot_id)

    # 1-2. scan every ship image in the pass
    scan = scan_snapshot(snapshot)
    steps = {"detection": {**scan, "observed_at": observed_at}}

    if not scan["oil_detected"]:
        return {
            "status": "CLEAR",
            "snapshot_id": snapshot_id,
            "observed_at": observed_at,
            "message": f"No oil signature in {snapshot_id}. Continue monitoring.",
            "steps": steps,
            "provenance": pipeline_provenance(),
        }

    # 3. characterise the strongest detection
    detection = scan["detections"][0]
    spill = characterize(detection)
    steps["characterization"] = spill

    # 4. trace it back to a probable origin
    origin = estimate_origin(spill, observed_at)
    steps["hindcast"] = origin

    # 5. reconstruct traffic around that origin during the release window
    ais = find_vessels_near(origin, get_ships())
    steps["ais"] = ais

    # 6. anomaly + weighted attribution over the survivors
    ranked = rank_ships(ais["candidates"], origin, ais["search_radius_km"])
    steps["attribution"] = {"ranked": ranked, "count": len(ranked)}

    # 7. where the slick goes next
    steps["forecast"] = forecast_from_spill(spill)

    return {
        "status": "SPILL_CONFIRMED",
        "snapshot_id": snapshot_id,
        "observed_at": observed_at,
        "spill": spill,
        "origin": {k: origin[k] for k in
                   ("origin_lat", "origin_lon", "estimated_time",
                    "release_window_start", "release_window_end", "confidence")},
        "top_suspect": ranked[0] if ranked else None,
        "steps": steps,
        "provenance": pipeline_provenance(),
        "disclaimer": (
            "Ranking identifies potential suspect vessels for investigation. "
            "It is not a determination of legal responsibility."
        ),
    }
