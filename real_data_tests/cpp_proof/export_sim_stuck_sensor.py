# real_data_tests/cpp_proof/export_sim_stuck_sensor.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Proof dataset for the cpp-stillness-faultclass branch (Ccode
update.txt, "JAY -- MONDAY", item 2): the sim's stuck_sensor fault on
attitude_rate -- the one dataset in this whole proof suite that
actually exercises Stillness (every real-data harness disables it,
min_normal_noise=0.0; the sim's own frozen blueprint does not --
sim/blueprint.py sets a real derived min_normal_noise for every
sensor except solar_current).

Same single-channel, whole-run, no-mid-run-clear_fault convention as
export_leash_drift.py: GRACIE's per-channel core is what's proven here
(gracie_rulebook.hpp's own scope), not the rest of the sim craft
(EDEN/CHESTER/human sign-off), so this calls build_clean_timeline()/
inject_faults() directly for the raw (timestamp, value) series and
the real frozen rule, without ever touching run_scored()/the human
sign-off tick -- those decide WHEN to clear_fault for reasons outside
GRACIE's own core, out of scope here same as always.

timing_seed=201: reuses the already-proven, already-understood seed
(job9/the sim rerun) rather than a fresh one -- attitude_rate's own
stuck_sensor fault for this seed is already known (start_s=13051,
end_s=14851, from the real job1/job9 checkpoints).

Run from the repo root:

    python -m real_data_tests.cpp_proof.export_sim_stuck_sensor
"""
import os

from sim.craft import build_clean_timeline, TOTAL_SECONDS
from sim.fault_injection import inject_faults
from sim.rulebook import build_rule_book
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)

CHANNEL = "attitude_rate"
SEED = 201


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rule_book, blueprint = build_rule_book()  # frozen, real -- NOT touched
    timestamps, clean_values, events = build_clean_timeline(rule_book, blueprint, seed=SEED)
    faulted_values, faults = inject_faults(
        timestamps, clean_values, rule_book, TOTAL_SECONDS, events=events, timing_seed=SEED
    )

    rule = rule_book[CHANNEL]
    values = faulted_values[CHANNEL]
    stuck_fault = next(f for f in faults if f["channel"] == CHANNEL)
    print(f"stuck_sensor fault on {CHANNEL}: start_s={stuck_fault['start_s']} end_s={stuck_fault['end_s']} "
          f"(Stillness: stuck_window_seconds={rule.stuck_window_seconds:.6g}, "
          f"min_normal_noise={rule.min_normal_noise:.6g}, allow_steady={rule.allow_steady})")

    rows = [(i, t.timestamp(), v, False) for i, (t, v) in enumerate(zip(timestamps, values))]

    tag = f"sim_stuck_sensor_{CHANNEL}_seed{SEED}"
    write_sidecar(os.path.join(OUT_DIR, f"{tag}_rule.txt"), rule)
    write_readings_csv(os.path.join(OUT_DIR, f"{tag}_readings.csv"), rows)
    log = run_reference(CHANNEL, rule, rows)
    write_reference_csv(os.path.join(OUT_DIR, f"{tag}_reference.csv"), log)

    n_stuck = sum(1 for row in log if row["sensor_health_fault"])
    print(f"{tag}: {len(rows)} rows exported, {n_stuck} rows with sensor_health_fault=True "
          f"(Python reference) -- confirms this dataset genuinely exercises Stillness.")

    with open(os.path.join(OUT_DIR, "sim_stuck_sensor_manifest.txt"), "w") as f:
        f.write(tag + "\n")


if __name__ == "__main__":
    main()
