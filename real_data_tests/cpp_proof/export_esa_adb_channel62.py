# real_data_tests/cpp_proof/export_esa_adb_channel62.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Proof dataset 3 of 3 for NEW TASK 1b: ESA-ADB Mission1 channel_62,
TEST PERIOD ONLY, STRICT setting. Bursty (median ~900s sample
interval, bursts to 3s) -- chosen specifically to exercise the leash
ring buffer's sizing (kLeashRingCapacity=2048 in the C++ core).

Reproduces real_data_tests/esa_adb/check_pretrip.py's exact driving
pattern (reused from there, not reimplemented): rows before the
mission's cutoff are excluded (training, not scored), Communication
Gap rows are excluded entirely (never fed to the agent), and a
clear_fault(reset_leash_timer=False) fires on every calendar-day
boundary, immediately before that day's first reading -- a day-
boundary marker written into the readings CSV as clear_before=1 for
the C++ side to reproduce exactly.

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.cpp_proof.export_esa_adb_channel62
"""
import os

from agents.gracie_rulebook import ChannelRule
from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR, MISSION_SPANS, CUTOFF_FRACTION,
    LEASH_WINDOW_SECONDS, LEASH_SOFT_DURATION_SECONDS, LEASH_HARD_DURATION_SECONDS,
    load_channel_series, load_labels_for_channel, load_anomaly_types,
    label_at, derive_rules,
)
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)
# proof_common.run_reference already honours each row's clear_before
# flag exactly as check_pretrip.py's loop does (clear_fault(channel,
# reset_leash_timer=False) immediately before that row) -- this
# dataset is the one that actually exercises that path.

MISSION_ZIP = "ESA-Mission1.zip"
CHANNEL = "channel_62"
SETTING_NAME = "STRICT"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    prefix = MISSION_ZIP.replace(".zip", "")
    path = os.path.join(DATA_DIR, MISSION_ZIP)
    anomaly_types = load_anomaly_types(path, prefix)
    start, end = MISSION_SPANS[MISSION_ZIP]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    timestamps, values = load_channel_series(path, prefix, CHANNEL)
    labels = load_labels_for_channel(path, prefix, anomaly_types, CHANNEL)
    rule_values = derive_rules(timestamps, values, labels, cutoff)[SETTING_NAME]

    rule = ChannelRule(
        name=CHANNEL, units="u",
        level_high=rule_values["level_high"], level_low=rule_values["level_low"],
        jump_limit=rule_values["jump_limit"],
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=rule_values["leash_slope_limit"],
        leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
        leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
    )

    rows = []
    last_day = None
    idx = 0
    for t, v in zip(timestamps, values):
        if t < cutoff:
            continue
        if label_at(t, labels) == "Communication Gap":
            continue
        day = t.date()
        clear_before = last_day is not None and day != last_day
        last_day = day
        rows.append((idx, t.timestamp(), v, clear_before))
        idx += 1

    tag = f"esa_adb_{CHANNEL}_test_period"
    write_sidecar(os.path.join(OUT_DIR, f"{tag}_rule.txt"), rule)
    write_readings_csv(os.path.join(OUT_DIR, f"{tag}_readings.csv"), rows)
    log = run_reference(CHANNEL, rule, rows)
    write_reference_csv(os.path.join(OUT_DIR, f"{tag}_reference.csv"), log)

    with open(os.path.join(OUT_DIR, "esa_adb_manifest.txt"), "w") as f:
        f.write(tag + "\n")
    n_clears = sum(1 for r in rows if r[3])
    print(f"{tag}: {len(rows)} rows exported ({n_clears} day-boundary clears), "
          f"level=[{rule.level_low:.6g}, {rule.level_high:.6g}], jump_limit={rule.jump_limit:.6g}/s, "
          f"leash_slope_limit={rule.leash_slope_limit:.6g}/s")


if __name__ == "__main__":
    main()
