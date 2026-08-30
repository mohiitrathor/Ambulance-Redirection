"""
RAAH Dispatch Performance Benchmark
====================================

Measures the current execution cost of dispatch_incident()
WITHOUT modifying any production code.

Produces:
  - Per-call timings for a representative sample of incident IDs
  - Aggregate stats: total, mean, median, min, max, std dev
  - Separate load_data() timing to isolate I/O cost
"""

import sys
import time
import statistics
from pathlib import Path

# ----------------------------------------------------------
# Make Dispatch importable (same approach as simulator.py)
# ----------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DISPATCH_DIR = ROOT / "Dispatch"

if str(DISPATCH_DIR) not in sys.path:
    sys.path.insert(0, str(DISPATCH_DIR))

from dispatch_engine import dispatch_incident, load_data


# ==============================================================
# CONFIGURATION
# ==============================================================

# 50 incident IDs spread across the 100K dataset
# Covers low, mid, and high IDs for representative coverage
SAMPLE_IDS = [
    1, 5, 10, 50, 100,
    200, 500, 750, 1000, 1500,
    2000, 3000, 4000, 5000, 6000,
    7500, 10000, 12500, 15000, 17500,
    20000, 25000, 30000, 35000, 40000,
    45000, 50000, 55000, 60000, 65000,
    70000, 72500, 75000, 77500, 80000,
    82000, 84000, 86000, 88000, 90000,
    91000, 92000, 93000, 94000, 95000,
    96000, 97000, 98000, 99000, 99999,
]

LOAD_DATA_REPS = 10  # Repetitions for load_data() timing


# ==============================================================
# BENCHMARK: load_data()
# ==============================================================

def benchmark_load_data():
    """Time load_data() independently to measure I/O cost."""

    print("=" * 70)
    print("BENCHMARK: load_data()")
    print(f"Repetitions: {LOAD_DATA_REPS}")
    print("=" * 70)

    timings = []

    for i in range(LOAD_DATA_REPS):

        start = time.perf_counter()
        load_data()
        elapsed = time.perf_counter() - start

        timings.append(elapsed)

        print(f"  Run {i + 1:>2}: {elapsed * 1000:>10.2f} ms")

    print("-" * 70)
    print(f"  Total:   {sum(timings) * 1000:>10.2f} ms")
    print(f"  Mean:    {statistics.mean(timings) * 1000:>10.2f} ms")
    print(f"  Median:  {statistics.median(timings) * 1000:>10.2f} ms")
    print(f"  Min:     {min(timings) * 1000:>10.2f} ms")
    print(f"  Max:     {max(timings) * 1000:>10.2f} ms")

    if len(timings) > 1:
        print(
            f"  Std Dev: "
            f"{statistics.stdev(timings) * 1000:>10.2f} ms"
        )

    print("=" * 70)
    print()

    return timings


# ==============================================================
# BENCHMARK: dispatch_incident()
# ==============================================================

def benchmark_dispatch():
    """Time dispatch_incident() for each sample ID."""

    n = len(SAMPLE_IDS)

    print("=" * 70)
    print("BENCHMARK: dispatch_incident()")
    print(f"Sample size: {n} incident IDs")
    print("=" * 70)

    timings = []
    errors = 0

    for incident_id in SAMPLE_IDS:

        start = time.perf_counter()

        try:
            result = dispatch_incident(incident_id)
            status = result.get("status", "UNKNOWN")
        except Exception as error:
            status = f"ERROR: {error}"
            errors += 1

        elapsed = time.perf_counter() - start
        timings.append(elapsed)

        print(
            f"  ID {incident_id:>6}: "
            f"{elapsed * 1000:>10.2f} ms  "
            f"[{status}]"
        )

    print("-" * 70)

    total = sum(timings)
    mean = statistics.mean(timings)
    median = statistics.median(timings)
    minimum = min(timings)
    maximum = max(timings)

    print(f"  Total:     {total * 1000:>10.2f} ms")
    print(f"  Mean:      {mean * 1000:>10.2f} ms")
    print(f"  Median:    {median * 1000:>10.2f} ms")
    print(f"  Min:       {minimum * 1000:>10.2f} ms")
    print(f"  Max:       {maximum * 1000:>10.2f} ms")

    if len(timings) > 1:
        print(
            f"  Std Dev:   "
            f"{statistics.stdev(timings) * 1000:>10.2f} ms"
        )

    print(f"  Errors:    {errors}")

    print("=" * 70)
    print()

    return timings


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":

    print()
    print("*" * 70)
    print("  RAAH DISPATCH PERFORMANCE BENCHMARK")
    print("  Pre-optimization baseline (M2)")
    print("*" * 70)
    print()

    # ---- Warm-up (1 call to populate caches / JIT) ----
    print("Warm-up call...")
    dispatch_incident(1)
    print("Warm-up done.\n")

    # ---- Benchmark load_data() ----
    load_timings = benchmark_load_data()

    # ---- Benchmark dispatch_incident() ----
    dispatch_timings = benchmark_dispatch()

    # ---- Summary ----
    load_mean = statistics.mean(load_timings) * 1000
    dispatch_mean = statistics.mean(dispatch_timings) * 1000
    dispatch_median = statistics.median(dispatch_timings) * 1000

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  load_data() mean:          {load_mean:>10.2f} ms")
    print(f"  dispatch_incident() mean:  {dispatch_mean:>10.2f} ms")
    print(f"  dispatch_incident() median:{dispatch_median:>10.2f} ms")
    print(
        f"  Estimated load_data() share: "
        f"{(load_mean / dispatch_mean) * 100:>5.1f}% "
        f"of mean dispatch time"
    )
    print(
        f"  50-call total:             "
        f"{sum(dispatch_timings) * 1000:>10.2f} ms"
    )
    print("=" * 70)
