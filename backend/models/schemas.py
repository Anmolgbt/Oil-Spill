from typing import List, Optional
from pydantic import BaseModel

class DetectSpillRequest(BaseModel):
    scene_id: Optional[str] = "S1A-DEMO-20260815T140000"

class HindcastRequest(BaseModel):
    observed_lat: Optional[float] = None
    observed_lon: Optional[float] = None
    hours: Optional[int] = 4
    n_particles: Optional[int] = 40

class ForecastRequest(BaseModel):
    hours: Optional[List[int]] = None

class AttributeRequest(BaseModel):
    vessel_id: str


class SimulationRequest(BaseModel):
    snapshot_id: Optional[str] = None
