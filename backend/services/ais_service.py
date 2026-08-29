from .data_store import get_vessels, get_incident

def get_candidates():
    vessels = get_vessels()
    return {"count": len(vessels), "vessels": vessels}

def get_tracks():
    return {"type":"FeatureCollection","features":[
        {"type":"Feature","properties":{"vessel_id":v["vessel_id"],"vessel_name":v["vessel_name"],
        "ais_dark":v["ais_dark"]},"geometry":{"type":"LineString",
        "coordinates":[[p["lon"],p["lat"]] for p in v["track"]]}}
        for v in get_vessels()
    ]}

def sar_ais_consistency_check():
    return get_incident()["sar_ais_check"]
