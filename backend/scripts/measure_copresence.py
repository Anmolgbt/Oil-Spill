"""
How many vessels could the demo show WITHOUT the time shift?

build_fleet.py shifts each vessel's timestamps onto a shared t1/t2/t3 clock,
which is the project's weakest honesty claim, so the claim that the shift is
unavoidable had better be a measurement rather than an assertion. This is that
measurement.

    python scripts/measure_copresence.py

THE QUESTION HAS TO BE ASKED PRECISELY, because three looser versions of it give
three misleading answers:

  "vessels live at one instant, by min/max span"     -> 55.  Meaningless: a
      vessel with a fix at 09:00 and another at 21:00 counts as live all day.
  "vessels with >= 20 fixes in the 12 h window"      -> 12.  Better, but a
      vessel's fixes can all cluster in one hour and still clear the bar.
  "vessels overlapping in data/simulation/fleet.json" -> 12. CIRCULAR. That file
      holds the already-shifted tracks; it measures the shift, not the corpus.

The demo needs a vessel to be placeable on the map at EACH of three passes four
hours apart. That is the question below, and the answer is 3.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.config import AIS_REFERENCE_FILE

PASS_INTERVAL_H = 4
PASSES = 3
# How stale a fix may be and still place a vessel on the map for that pass.
TOLERANCE_MIN = 30
SHIPPED_T1 = "2021-03-28 13:39:59"


def main():
    import pandas as pd

    df = pd.read_csv(AIS_REFERENCE_FILE)
    tcol = next(c for c in df.columns if "time" in c.lower() or "date" in c.lower())
    mcol = next(c for c in df.columns if "mmsi" in c.lower())
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.sort_values(tcol)
    tol = pd.Timedelta(minutes=TOLERANCE_MIN)

    def present_at_all_passes(t1):
        """MMSIs with a fix within TOLERANCE of every one of the three passes."""
        together = None
        for i in range(PASSES):
            p = t1 + pd.Timedelta(hours=i * PASS_INTERVAL_H)
            window = df[(df[tcol] >= p - tol) & (df[tcol] <= p + tol)]
            seen = set(window[mcol].unique())
            together = seen if together is None else (together & seen)
        return together

    print(f"corpus: {df[mcol].nunique()} MMSIs, "
          f"{df[tcol].min()} -> {df[tcol].max()}")
    print(f"asking: a fix within +/-{TOLERANCE_MIN} min of all {PASSES} passes, "
          f"{PASS_INTERVAL_H} h apart\n")

    shipped = present_at_all_passes(pd.Timestamp(SHIPPED_T1))
    print(f"shipped demo window (t1 = {SHIPPED_T1}): {len(shipped)} vessels")

    best_n, best_t1 = 0, None
    last = df[tcol].max() - pd.Timedelta(hours=(PASSES - 1) * PASS_INTERVAL_H)
    for t1 in pd.date_range(df[tcol].min(), last, freq="1h"):
        n = len(present_at_all_passes(t1))
        if n > best_n:
            best_n, best_t1 = n, t1

    print(f"best window anywhere in the corpus:    {best_n} vessels (t1 = {best_t1})")
    print(f"\n=> {best_n} is the ceiling. The demo shows 12, so the time shift is a "
          f"corpus limit rather than a shortcut.")


if __name__ == "__main__":
    main()
