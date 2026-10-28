# bg_jobs/queue/job1_sim_50seeds.py
# Added 2026-10-28 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 1 of 5 ("keep the laptop working while usage is low" --
Ccode update.txt). Runs the EXISTING, frozen Item-C simulated craft
(sim/blueprint.py / sim/rulebook.py / sim/fault_injection.py /
sim/run_sim_test.py, none of them touched here) on 50 never-before-
used seeds -- this session has already used scenario_seed/timing_seed
1 and 101-104; this job uses 201-250, a disjoint fixed range, written
here as an explicit list, not generated at runtime.

NO design changes. Reuses sim.run_sim_test's own build_rule_book() and
run_scenario() exactly -- same frozen rule book, same fault-injection
method, same scoring (noticed/flagged per sense, false alarms,
background false alarms, safe-state time per class), both expected-
cause modes, human sign-off on (sim.run_sim_test's own default). Only
new code here: the seed list, per-seed checkpointing to a SEPARATE
output file (never touches sim/out/sim_results.json), and the final
summary stats (mean/stdev/min/max across all 50 seeds).

Checkpointed per seed: safe to stop and resume. Output:
bg_jobs/queue/out/job1_sim_50seeds.json -- gitignored, same as every
other results/out directory in this project.

Run from the repo root:
    python -m bg_jobs.queue.job1_sim_50seeds
"""
import ctypes
import json
import os
import statistics
import time

from sim.rulebook import build_rule_book
from sim.run_sim_test import run_scenario

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUT_PATH = os.path.join(OUT_DIR, "job1_sim_50seeds.json")

SEEDS = list(range(201, 251))  # 50 seeds, disjoint from 1 and 101-104 already used this session


# --- memory logging, same ctypes/psapi approach as run_esa_adb_test_v2.py ---
class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32.dll")
_kernel32.GetCurrentProcess.restype = ctypes.c_void_p
_psapi = ctypes.WinDLL("psapi.dll")
_psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS), ctypes.c_ulong]
_psapi.GetProcessMemoryInfo.restype = ctypes.c_int


def current_working_set_bytes():
    counters = _PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
    handle = _kernel32.GetCurrentProcess()
    ok = _psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize if ok else None


def _flatten_metrics(scenario_report):
    """Pulls the handful of per-seed numbers the summary cares about
    out of run_scenario()'s full report, per mode. fs["senses"]
    ["combined"]["flagged"] is the bool score_faults() already
    computes (see sim/run_sim_test.py) -- reused directly, not
    re-derived."""
    out = {}
    for mode in ("without_expected_causes", "with_expected_causes"):
        run = scenario_report["runs"][mode]
        out[mode] = {
            "safe_state_time": run["safe_state_time"],
            "n_false_alarms": sum(1 for a in run["false_alarms_on_normal_events"] if a["false_alarmed"]),
            "n_normal_events": len(run["false_alarms_on_normal_events"]),
            "n_background_false_alarm_channels": len(run["background_false_alarms"]),
            "ghost_mode_disagreements": run["ghost_mode_disagreements"],
            "faults_flagged": sum(1 for fs in run["fault_detection"] if fs["senses"]["combined"]["flagged"]),
            "n_faults": len(run["fault_detection"]),
        }
    return out


def summarize(per_seed_metrics):
    """mean/stdev/min/max across every completed seed, per mode, per metric."""
    summary = {}
    for mode in ("without_expected_causes", "with_expected_causes"):
        summary[mode] = {}
        for bucket in ("IDLE", "MONITORING_NOMINAL", "MONITORING_NON_URGENT_FLAGGED", "HOLD", "SAFE_MODE"):
            values = [m[mode]["safe_state_time"].get(bucket, 0) for m in per_seed_metrics.values()]
            summary[mode][f"safe_state_time.{bucket}"] = {
                "mean": statistics.mean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "min": min(values), "max": max(values),
            }
        for key in ("n_false_alarms", "n_background_false_alarm_channels", "ghost_mode_disagreements", "faults_flagged"):
            values = [m[mode][key] for m in per_seed_metrics.values()]
            summary[mode][key] = {
                "mean": statistics.mean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "min": min(values), "max": max(values),
            }
    return summary


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Job 1: sim, 50 fresh seeds (201-250). Frozen Item-C rule book, unchanged.")
    t_start = time.time()

    results = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            saved = json.load(f)
            results = saved.get("per_seed", {})
            print(f"  resuming -- {len(results)} seed(s) already done")

    rule_book, blueprint = build_rule_book()  # frozen, derived once, reused across every seed -- NOT touched

    for seed in SEEDS:
        label = f"seed_{seed}"
        if label in results:
            continue
        t0 = time.time()
        mem = current_working_set_bytes()
        print(f"  [{label}] starting (working set: {mem/1e6:.1f} MB)" if mem else f"  [{label}] starting")
        scenario_report = run_scenario(rule_book, blueprint, seed, seed)
        elapsed = time.time() - t0
        results[label] = scenario_report
        results[label]["elapsed_seconds"] = elapsed
        with open(OUT_PATH, "w") as f:
            json.dump({"per_seed": results, "summary": None}, f, indent=2, default=str)
        print(f"  [{label}] done in {elapsed:.1f}s -- checkpointed ({len(results)}/{len(SEEDS)})")

    if len(results) == len(SEEDS):
        per_seed_metrics = {label: _flatten_metrics(r) for label, r in results.items()}
        summary = summarize(per_seed_metrics)
        with open(OUT_PATH, "w") as f:
            json.dump({"per_seed": results, "summary": summary}, f, indent=2, default=str)
        print(f"\nAll {len(SEEDS)} seeds done in {time.time()-t_start:.1f}s total. Summary written.")
    else:
        print(f"\n{len(results)}/{len(SEEDS)} seeds done this run -- summary written once all complete.")

    print(f"Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
