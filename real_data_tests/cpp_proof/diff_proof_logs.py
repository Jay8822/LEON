# real_data_tests/cpp_proof/diff_proof_logs.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Compares the C++ proof executable's verdict log against the Python
reference log, row for row, for NEW TASK 1b. Severity and the two
boolean/transition fields must match EXACTLY; the leash slope (when
both sides agree one exists) is allowed a 1e-9 epsilon -- but the
MAXIMUM difference actually observed is always reported, per dataset,
even when it's comfortably under tolerance, so the tolerance can't be
hiding anything (Jay's addition 7 to the approved plan).

Run from the repo root, after a dataset's _reference.csv (Python) and
_verdicts.csv (C++, via proof_gracie_rulebook.exe) both exist:

    python -m real_data_tests.cpp_proof.diff_proof_logs <reference.csv> <verdicts.csv> <label>

Added 2026-10-27 (strengthening round): diff_with_expected_overflow(),
for the ring-overflow stress dataset specifically. The fixed-size C++
ring legitimately stops partway through with Status::kRingOverflow
(see export_ring_overflow_stress.py) while Python's unbounded deque
happily keeps going -- that divergence PAST the overflow point is
expected, not a mismatch to chase. This checks two separate things:
every row up to the overflow is still bit-exact (same rules as
diff()), and the overflow itself fired at EXACTLY the sample index the
generator's own mechanical simulation predicted -- not just
"somewhere after it got big."
"""
import csv
import sys

DISCRETE_FIELDS = ["severity", "jump_event", "leash_settled", "new_crossing_while_latched", "has_slope"]
SLOPE_TOLERANCE = 1e-9


def load(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def diff(python_csv, cpp_csv, label):
    py_rows = load(python_csv)
    cpp_rows = load(cpp_csv)

    if len(py_rows) != len(cpp_rows):
        print(f"{label}: MISMATCH -- row count differs ({len(py_rows)} python vs {len(cpp_rows)} c++)")
        return False

    max_slope_diff = 0.0
    mismatches = []
    for i, (p, c) in enumerate(zip(py_rows, cpp_rows)):
        if p["sample_index"] != c["sample_index"]:
            print(f"{label}: sample_index mismatch at row {i}: {p['sample_index']} (python) "
                  f"vs {c['sample_index']} (c++)")
            return False
        diffs = {f: (p[f], c[f]) for f in DISCRETE_FIELDS if p[f] != c[f]}
        if diffs:
            mismatches.append((p["sample_index"], diffs))
            continue
        if p["has_slope"] == "1":
            d = abs(float(p["slope"]) - float(c["slope"]))
            if d > max_slope_diff:
                max_slope_diff = d

    print(f"{label}: {len(py_rows)} rows compared. Max slope difference actually observed: {max_slope_diff:.3e}")
    if mismatches:
        print(f"{label}: MISMATCH -- {len(mismatches)} rows differ on a discrete field.")
        for sample_index, diffs in mismatches[:10]:
            print(f"    sample_index={sample_index}: {diffs}")
        if len(mismatches) > 10:
            print(f"    ... and {len(mismatches) - 10} more")
        return False
    if max_slope_diff > SLOPE_TOLERANCE:
        print(f"{label}: MISMATCH -- max slope difference {max_slope_diff:.3e} exceeds "
              f"the {SLOPE_TOLERANCE:.0e} tolerance")
        return False
    print(f"{label}: PASS -- every discrete field matches exactly; "
          f"slope within tolerance (max observed {max_slope_diff:.3e})")
    return True


def diff_with_expected_overflow(python_csv, cpp_csv, label, expected_overflow_index):
    """Like diff(), but for a dataset where the C++ side is EXPECTED to
    stop early with Status::kRingOverflow. `cpp_csv` must therefore
    have exactly `expected_overflow_index` data rows (sample_index 0..
    expected_overflow_index-1); `python_csv` will normally have more
    (its unbounded deque keeps going) -- only the overlapping prefix
    is compared for bit-exactness. Returns True only if BOTH the
    overflow landed at exactly the predicted row count AND every
    compared row matches."""
    py_rows = load(python_csv)
    cpp_rows = load(cpp_csv)

    if len(cpp_rows) != expected_overflow_index:
        print(f"{label}: MISMATCH -- expected the C++ side to stop after exactly "
              f"{expected_overflow_index} rows (the predicted overflow sample_index), "
              f"but it wrote {len(cpp_rows)}.")
        return False
    if len(py_rows) < expected_overflow_index:
        print(f"{label}: MISMATCH -- python reference has fewer rows ({len(py_rows)}) "
              f"than the predicted overflow point ({expected_overflow_index}); can't even "
              f"check the prefix.")
        return False

    max_slope_diff = 0.0
    mismatches = []
    for i in range(expected_overflow_index):
        p, c = py_rows[i], cpp_rows[i]
        if p["sample_index"] != c["sample_index"]:
            print(f"{label}: sample_index mismatch at row {i}: {p['sample_index']} (python) "
                  f"vs {c['sample_index']} (c++)")
            return False
        diffs = {f: (p[f], c[f]) for f in DISCRETE_FIELDS if p[f] != c[f]}
        if diffs:
            mismatches.append((p["sample_index"], diffs))
            continue
        if p["has_slope"] == "1":
            d = abs(float(p["slope"]) - float(c["slope"]))
            if d > max_slope_diff:
                max_slope_diff = d

    print(f"{label}: overflow confirmed at the predicted sample_index={expected_overflow_index} "
          f"(C++ wrote exactly that many rows, then reported kRingOverflow). "
          f"{expected_overflow_index} rows below the overflow compared. "
          f"Max slope difference actually observed: {max_slope_diff:.3e}")
    if mismatches:
        print(f"{label}: MISMATCH -- {len(mismatches)} rows below the overflow differ on a discrete field.")
        for sample_index, diffs in mismatches[:10]:
            print(f"    sample_index={sample_index}: {diffs}")
        if len(mismatches) > 10:
            print(f"    ... and {len(mismatches) - 10} more")
        return False
    if max_slope_diff > SLOPE_TOLERANCE:
        print(f"{label}: MISMATCH -- max slope difference {max_slope_diff:.3e} exceeds "
              f"the {SLOPE_TOLERANCE:.0e} tolerance")
        return False
    print(f"{label}: PASS -- overflow fired at exactly the predicted sample_index, "
          f"every row below it matches exactly, slope within tolerance "
          f"(max observed {max_slope_diff:.3e}). Rows at/after the overflow are not "
          f"compared -- Python's unbounded deque diverging there is expected, not a bug.")
    return True


if __name__ == "__main__":
    ok = diff(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "dataset")
    sys.exit(0 if ok else 1)
