# bg_jobs/queue/job5_cpp_proof_bigger.py
# Added 2026-10-28 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 5 of 5 ("keep the laptop working while usage is low" --
Ccode update.txt). Extends NEW TASK 1b's existing cross-language
proof (real_data_tests/cpp_proof/, built and verified earlier this
session) to channel_62's FULL series (every prior proof pass only
used its test period) plus 3 more ESA-ADB Mission1 channels, chosen
by a FIXED rule decided here, in advance, not by looking at any
result first: the next 3 monitored channels by channel number after
channel_62 in Mission1's own monitored-channel list (confirmed via
load_channels_csv/select_channels earlier this session) --
channel_63, channel_64, channel_65. No other selection criterion.

NO design changes. gracie_rulebook.hpp/cpp is untouched (confirmed
`ninja: no work to do` on a fresh build before writing this). Reuses
real_data_tests/cpp_proof/proof_common.py's export/reference
functions and run_opssat_all_fragments_proof.py's own compare()
directly -- same bit-for-bit/1e-9-slope-tolerance standard as every
earlier proof pass, nothing loosened.

Checkpointed per channel (resume-skip). Requires the C++ proof
executable already built -- pass its path as the one argument.

Run from the repo root:
    python -m bg_jobs.queue.job5_cpp_proof_bigger "AI Stack C++ Test Build/build/proof_gracie_rulebook.exe"
"""
import csv
import json
import os
import subprocess
import sys
import time

from agents.gracie_rulebook import ChannelRule
from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR, load_channel_series, load_labels_for_channel, load_anomaly_types, derive_rules,
    MISSION_SPANS, CUTOFF_FRACTION,
    LEASH_WINDOW_SECONDS, LEASH_SOFT_DURATION_SECONDS, LEASH_HARD_DURATION_SECONDS,
)
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR as PROOF_OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)
from real_data_tests.cpp_proof.run_opssat_all_fragments_proof import compare

JOB_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
JOB_OUT_PATH = os.path.join(JOB_OUT_DIR, "job5_cpp_proof_bigger.json")

MISSION_ZIP = "ESA-Mission1.zip"
SETTING_NAME = "STRICT"
# Fixed rule, decided before running anything (see module docstring):
# channel_62 full series, then the next 3 monitored channels by
# number after it in Mission1's own list.
CHANNELS_FULL_SERIES = ["channel_62"]
CHANNELS_NEXT_THREE = ["channel_63", "channel_64", "channel_65"]


def _export_and_prove(proof_exe, channel, timestamps, values, labels, cutoff, tag):
    rule_values = derive_rules(timestamps, values, labels, cutoff)[SETTING_NAME]
    if rule_values["level_high"] is None or rule_values["jump_limit"] is None:
        return {"skipped": "insufficient nominal training days to derive a limit"}

    rule = ChannelRule(
        name=channel, units="u",
        level_high=rule_values["level_high"], level_low=rule_values["level_low"],
        jump_limit=rule_values["jump_limit"],
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=rule_values["leash_slope_limit"],
        leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
        leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
        stuck_window_seconds=LEASH_WINDOW_SECONDS, min_normal_noise=0.0,  # Stillness not in the C++ port -- not exercised
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C fault classes -- not stated for this proof
    )

    # FULL series -- every row, not test-period-only (job 5's own
    # point): day-boundary clears throughout, same driving pattern as
    # check_pretrip.py/export_esa_adb_channel62.py, just not cutoff-
    # restricted.
    rows = []
    last_day = None
    idx = 0
    for t, v in zip(timestamps, values):
        day = t.date()
        clear_before = last_day is not None and day != last_day
        last_day = day
        rows.append((idx, t.timestamp(), v, clear_before))
        idx += 1

    sidecar_path = os.path.join(PROOF_OUT_DIR, f"{tag}_rule.txt")
    readings_path = os.path.join(PROOF_OUT_DIR, f"{tag}_readings.csv")
    reference_path = os.path.join(PROOF_OUT_DIR, f"{tag}_reference.csv")
    verdicts_path = os.path.join(PROOF_OUT_DIR, f"{tag}_verdicts.csv")

    write_sidecar(sidecar_path, rule)
    write_readings_csv(readings_path, rows)
    log = run_reference(channel, rule, rows)
    write_reference_csv(reference_path, log)

    result = subprocess.run([proof_exe, sidecar_path, readings_path, verdicts_path],
                             capture_output=True, text=True)
    if result.returncode != 0:
        return {"n_rows": len(rows), "pass": False,
                "reason": f"proof executable exit code {result.returncode}: {result.stderr.strip()}"}

    ok, max_slope_diff, had_any_slope, reason = compare(reference_path, verdicts_path)
    return {"n_rows": len(rows), "pass": ok, "max_slope_diff": max_slope_diff,
            "had_any_slope": had_any_slope, "reason": reason}


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: python -m bg_jobs.queue.job5_cpp_proof_bigger <proof_gracie_rulebook.exe>")
    proof_exe = os.path.abspath(sys.argv[1])
    if not os.path.exists(proof_exe):
        raise SystemExit(f"proof executable not found: {proof_exe}")

    os.makedirs(JOB_OUT_DIR, exist_ok=True)
    os.makedirs(PROOF_OUT_DIR, exist_ok=True)

    results = {}
    if os.path.exists(JOB_OUT_PATH):
        with open(JOB_OUT_PATH) as f:
            results = json.load(f)
        print(f"resuming -- {len(results)} channel(s) already done")

    prefix = MISSION_ZIP.replace(".zip", "")
    path = os.path.join(DATA_DIR, MISSION_ZIP)
    anomaly_types = load_anomaly_types(path, prefix)
    start, end = MISSION_SPANS[MISSION_ZIP]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    channels = [(ch, "full_series") for ch in CHANNELS_FULL_SERIES] + \
               [(ch, "next_three") for ch in CHANNELS_NEXT_THREE]

    for channel, kind in channels:
        tag = f"job5_{channel}_{kind}"
        if tag in results:
            print(f"{tag}: already done, skipping (resume)")
            continue
        t0 = time.time()
        timestamps, values = load_channel_series(path, prefix, channel)
        labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
        outcome = _export_and_prove(proof_exe, channel, timestamps, values, labels, cutoff, tag)
        del timestamps, values
        outcome["elapsed_seconds"] = time.time() - t0
        results[tag] = outcome
        with open(JOB_OUT_PATH, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"{tag}: {outcome} -- checkpointed")

    n_pass = sum(1 for r in results.values() if r.get("pass"))
    n_total = sum(1 for r in results.values() if "pass" in r)
    print(f"\n{n_pass}/{n_total} channels PASS. Written to {JOB_OUT_PATH}")


if __name__ == "__main__":
    main()
