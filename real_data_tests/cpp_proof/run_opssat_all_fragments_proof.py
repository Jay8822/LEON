# real_data_tests/cpp_proof/run_opssat_all_fragments_proof.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""NEW TASK 1b's strengthening round, step 1: runs the full cross-
language proof (export -> Python reference -> C++ replay -> diff)
across EVERY OPS-SAT test-split fragment, on all 9 channels
run_opssat_ad_test.py itself scores (CADC0872-4 magnetometer,
CADC0884-94 photodiode) -- not a sample of one, like the original
NEW TASK 1b proof used. Reuses that module's own train/test split and
threshold/jump/leash derivation directly (STRICT setting, 95th/5th) --
never reinvents "test fragment."

Each fragment is independent (run_opssat_ad_test.py's own docstring:
"no state carries between them"), so each gets a fresh GracieAgent/
gracie_rulebook state via proof_common.run_reference() and a fresh
C++ process invocation -- no clear_fault markers needed mid-fragment.

Run from the repo root, after building "AI Stack C++ Test Build" and
after download_opssat_ad.py:

    python -m real_data_tests.cpp_proof.run_opssat_all_fragments_proof <path to proof_gracie_rulebook.exe>
"""
import csv
import os
import subprocess
import sys

from agents.gracie_rulebook import ChannelRule
from real_data_tests.opssat_ad.run_opssat_ad_test import (
    load_fragments, derive_thresholds, derive_jump_limits, derive_leash_limits,
    LEASH_WINDOW_SECONDS, LEASH_SOFT_DURATION_SECONDS, LEASH_HARD_DURATION_SECONDS,
    LEASH_SLOPE_PCT,
)
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)
from real_data_tests.cpp_proof.diff_proof_logs import DISCRETE_FIELDS, SLOPE_TOLERANCE, load as load_csv

SETTING = (95, 5)  # STRICT


def compare(python_csv, cpp_csv):
    """Same rules as diff_proof_logs.diff(), but returns the numbers
    instead of printing -- this driver aggregates across 529 fragments
    and only prints a line per fragment plus call-outs, not diff()'s
    own full verbose output 529 times over. Also returns whether this
    fragment ever had a full leash window at all (has_slope=1 on at
    least one row) -- reported so a tolerance of "0 diff" isn't
    quietly hiding that most fragments never exercised the slope
    comparison in the first place (most OPS-SAT fragments are shorter
    than LEASH_WINDOW_SECONDS + a full window of history)."""
    py_rows = load_csv(python_csv)
    cpp_rows = load_csv(cpp_csv)
    if len(py_rows) != len(cpp_rows):
        return False, 0.0, False, f"row count differs ({len(py_rows)} python vs {len(cpp_rows)} c++)"
    max_slope_diff = 0.0
    had_any_slope = False
    for p, c in zip(py_rows, cpp_rows):
        if p["sample_index"] != c["sample_index"]:
            return False, 0.0, had_any_slope, f"sample_index mismatch ({p['sample_index']} vs {c['sample_index']})"
        diffs = {f: (p[f], c[f]) for f in DISCRETE_FIELDS if p[f] != c[f]}
        if diffs:
            return False, 0.0, had_any_slope, f"discrete field mismatch at sample_index={p['sample_index']}: {diffs}"
        if p["has_slope"] == "1":
            had_any_slope = True
            d = abs(float(p["slope"]) - float(c["slope"]))
            if d > max_slope_diff:
                max_slope_diff = d
    if max_slope_diff > SLOPE_TOLERANCE:
        return False, max_slope_diff, had_any_slope, f"max slope difference {max_slope_diff:.3e} exceeds tolerance"
    return True, max_slope_diff, had_any_slope, None


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m real_data_tests.cpp_proof.run_opssat_all_fragments_proof <proof_gracie_rulebook.exe>")
    # abspath, not the raw argv value -- a forward-slash relative path
    # with spaces in a parent directory name ("AI Stack C++ Test
    # Build") was silently failing subprocess.run on Windows
    # (CreateProcess, WinError 2) until normalized. Found by testing
    # this directly, not assumed to work.
    proof_exe = os.path.abspath(sys.argv[1])
    if not os.path.exists(proof_exe):
        raise SystemExit(f"proof executable not found: {proof_exe}")

    os.makedirs(OUT_DIR, exist_ok=True)
    fragments = load_fragments()
    train = [f for f in fragments if f.is_train]
    test = [f for f in fragments if not f.is_train]

    thresholds = derive_thresholds(train, *SETTING)
    jump_limits = derive_jump_limits(train, SETTING[0])
    leash_limits = derive_leash_limits(train, LEASH_SLOPE_PCT)

    channels = sorted(set(f.channel for f in test))
    rules = {}
    skipped_channels = []
    for ch in channels:
        if ch not in thresholds or ch not in jump_limits or ch not in leash_limits:
            skipped_channels.append(ch)
            continue
        rules[ch] = ChannelRule(
            name=ch, units="u",
            level_high=thresholds[ch]["high"], level_low=thresholds[ch]["low"],
            jump_limit=jump_limits[ch]["limit"],
            leash_window_seconds=LEASH_WINDOW_SECONDS,
            leash_slope_limit=leash_limits[ch]["limit"],
            leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
            leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
            stuck_window_seconds=LEASH_WINDOW_SECONDS, min_normal_noise=0.0,  # Stillness: not in the C++ port yet, not exercised here
            level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
            leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
        )

    if skipped_channels:
        print(f"SKIPPED channels (no derivable threshold/jump/leash limit from training data, "
              f"same condition the real harness itself treats as n/a): {skipped_channels}")

    manifest_path = os.path.join(OUT_DIR, "opssat_all_manifest.csv")
    manifest_rows = []

    n_tested, n_pass, n_fail = 0, 0, 0
    worst_slope_diff = 0.0
    worst_fragment = None
    n_with_slope = 0
    failures = []

    for frag in test:
        rule = rules.get(frag.channel)
        if rule is None:
            continue
        tag = f"opssat_all_{frag.channel}_seg{frag.segment_id}"
        rows = [(i, t.timestamp(), v, False) for i, (t, v) in enumerate(zip(frag.timestamps, frag.values))]

        sidecar_path = os.path.join(OUT_DIR, f"{tag}_rule.txt")
        readings_path = os.path.join(OUT_DIR, f"{tag}_readings.csv")
        reference_path = os.path.join(OUT_DIR, f"{tag}_reference.csv")
        verdicts_path = os.path.join(OUT_DIR, f"{tag}_verdicts.csv")

        write_sidecar(sidecar_path, rule)
        write_readings_csv(readings_path, rows)
        log = run_reference(frag.channel, rule, rows)
        write_reference_csv(reference_path, log)

        result = subprocess.run(
            [proof_exe, sidecar_path, readings_path, verdicts_path],
            capture_output=True, text=True,
        )
        n_tested += 1
        if result.returncode != 0:
            n_fail += 1
            reason = f"proof executable exit code {result.returncode}: {result.stderr.strip()}"
            failures.append((tag, reason))
            manifest_rows.append((tag, frag.channel, frag.segment_id, len(rows), "FAIL", reason, ""))
            continue

        ok, max_slope_diff, had_any_slope, reason = compare(reference_path, verdicts_path)
        if had_any_slope:
            n_with_slope += 1
        if max_slope_diff >= worst_slope_diff:
            worst_slope_diff = max_slope_diff
            worst_fragment = tag
        if ok:
            n_pass += 1
            manifest_rows.append((tag, frag.channel, frag.segment_id, len(rows), "PASS", "", f"{max_slope_diff:.3e}"))
        else:
            n_fail += 1
            failures.append((tag, reason))
            manifest_rows.append((tag, frag.channel, frag.segment_id, len(rows), "FAIL", reason, f"{max_slope_diff:.3e}"))

    with open(manifest_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tag", "channel", "segment_id", "n_rows", "result", "failure_reason", "max_slope_diff"])
        w.writerows(manifest_rows)

    print(f"\n{n_tested} test fragments run across {len(rules)} channels "
          f"({len(skipped_channels)} channels skipped: {skipped_channels}).")
    print(f"PASS: {n_pass}  FAIL: {n_fail}")
    print(f"{n_with_slope}/{n_tested} fragments were long enough to produce at least one "
          f"full leash window (the rest are too short -- has_slope=0 throughout, same as "
          f"the real GracieAgent on the same data, nothing to compare for those beyond the "
          f"discrete fields already checked).")
    print(f"Worst max slope difference actually observed across all fragments: "
          f"{worst_slope_diff:.3e} (fragment {worst_fragment}), tolerance is {SLOPE_TOLERANCE:.0e}.")
    if failures:
        print(f"\n{len(failures)} FAILING FRAGMENTS, called out individually (not buried in the aggregate):")
        for tag, reason in failures:
            print(f"  {tag}: {reason}")
    print(f"\nFull per-fragment manifest: {manifest_path}")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
