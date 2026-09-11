"""
Shared fixtures.

Tests import backend modules as top-level packages (`services.geo`, not
`backend.services.geo`) because that is how uvicorn runs the app — main.py does
`from core.config import ...`. Keeping the test import path identical to the
runtime one means a test cannot pass against a layout the server does not use.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
