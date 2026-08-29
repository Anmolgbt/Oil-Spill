from .data_store import get_incident

def run_filter():
    inc = get_incident()
    return inc["lookalike"]
