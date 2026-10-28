# real_data_tests/cpp_proof/export_leash_drift.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Proof dataset 1 of 3 for NEW TASK 1b: simulated_tests/leash_drift's
planted-drift streams, ALL SEEDS, BOTH CHANNELS -- reuses
build_scenario() directly rather than regenerating its logic. One
continuous ~2 hour timeline per (channel, seed); no clear_fault calls
mid-run (matches simulated_tests/leash_drift/run_leash_drift_test.py's
own driving pattern, which never calls clear_fault either).

Level and jump bounds are set unreachable (same convention as
agents/gracie_test.py's DRIFT_RULE fixture) so this proof isolates
leash -- the mechanism this dataset is built to exercise.

Run from the repo root, after real_data_tests/opssat_ad's download
script (the noise source):

    python -m real_data_tests.cpp_proof.export_leash_drift
"""
import os

from agents.gracie_rulebook import ChannelRule
from real_data_tests.opssat_ad.run_opssat_ad_test import (
    LEASH_WINDOW_SECONDS, LEASH_SOFT_DURATION_SECONDS, LEASH_HARD_DURATION_SECONDS,
)
from simulated_tests.leash_drift.generate_leash_drift import (
    CHANNELS, build_scenario, derive_limit_for_channel, load_real_delta_pool,
)
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)

SEEDS = [1, 2, 3, 4, 5]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = []
    for channel in CHANNELS:
        delta_pool = load_real_delta_pool(channel)
        limit = derive_limit_for_channel(channel, delta_pool)
        rule = ChannelRule(
            name=channel, units="u",
            level_high=1_000_000.0, level_low=-1_000_000.0,
            jump_limit=1_000_000.0,
            leash_window_seconds=LEASH_WINDOW_SECONDS,
            leash_slope_limit=limit,
            leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
            leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
            stuck_window_seconds=LEASH_WINDOW_SECONDS, min_normal_noise=0.0,  # Stillness: not in the C++ port yet, not exercised here
            level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
            leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
        )
        for seed in SEEDS:
            timestamps, values, _events = build_scenario(channel, delta_pool, limit, seed)
            rows = [(i, t.timestamp(), v, False) for i, (t, v) in enumerate(zip(timestamps, values))]

            tag = f"leash_drift_{channel}_seed{seed}"
            write_sidecar(os.path.join(OUT_DIR, f"{tag}_rule.txt"), rule)
            write_readings_csv(os.path.join(OUT_DIR, f"{tag}_readings.csv"), rows)
            log = run_reference(channel, rule, rows)
            write_reference_csv(os.path.join(OUT_DIR, f"{tag}_reference.csv"), log)
            manifest.append(tag)
            print(f"{tag}: {len(rows)} rows exported (slope_limit={limit:.6g}/s)")

    with open(os.path.join(OUT_DIR, "leash_drift_manifest.txt"), "w") as f:
        f.write("\n".join(manifest) + "\n")
    print(f"Done: {len(manifest)} (channel, seed) datasets exported.")


if __name__ == "__main__":
    main()
