# bg_jobs/queue/job_eden_fault_clearing_50seeds.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Fault-clearing job, part C ("Rerun the 50 sim seeds (fixed scorer)
from a fresh frozen snapshot and compare with job9"). Same 50 seeds
(201-250), same frozen rule book, as job1/job9 -- rescored with
EDEN's expected-boom-readings + standard/boom release machinery now
wired in (branch eden-fault-clearing).

Unlike job1/job9, THIS driver script is not itself inside the
snapshot -- it lives in the main repo so it's easy to inspect/rerun,
but imports sim.rulebook/sim.run_sim_test from the frozen snapshot's
own path (sys.path, inserted before any sim import), so the actual
agent/sim CODE being measured is pinned, exactly as every other
frozen-snapshot job this project has run. Only code; data/results/
logs/queue-out stay live via the snapshot's own junctions, same as
always.

Results go to bg_jobs/queue/out/job_eden_fault_clearing_50seeds.json
-- a new file; job1's and job9's own outputs are untouched, kept as
the pre-fault-clearing record.

Run from the repo root:
    python -m bg_jobs.queue.job_eden_fault_clearing_50seeds <snapshot path>
"""
import json
import os
import sys
import time

SNAPSHOT_PATH = sys.argv[1] if len(sys.argv) > 1 else None
if SNAPSHOT_PATH:
    sys.path.insert(0, os.path.abspath(SNAPSHOT_PATH))

from sim.rulebook import build_rule_book
from sim.run_sim_test import run_scenario

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUT_PATH = os.path.join(OUT_DIR, "job_eden_fault_clearing_50seeds.json")

SEEDS = list(range(201, 251))  # same 50 seeds as job1/job9 -- disjoint from nothing, directly comparable


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    import sim.run_sim_test as rst
    print(f"Job: sim, same 50 seeds (201-250) as job1/job9, fault-clearing machinery wired in. "
          f"sim module loaded from: {rst.__file__}")

    results = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            saved = json.load(f)
            results = saved.get("per_seed", {})
            print(f"  resuming -- {len(results)} seed(s) already done")

    rule_book, blueprint = build_rule_book()

    for seed in SEEDS:
        label = f"seed_{seed}"
        if label in results:
            continue
        t0 = time.time()
        print(f"  [{label}] starting")
        scenario_report = run_scenario(rule_book, blueprint, seed, seed)
        elapsed = time.time() - t0
        results[label] = scenario_report
        results[label]["elapsed_seconds"] = elapsed
        with open(OUT_PATH, "w") as f:
            json.dump({"per_seed": results}, f, indent=2, default=str)
        print(f"  [{label}] done in {elapsed:.1f}s -- checkpointed ({len(results)}/{len(SEEDS)})")

    print(f"\nAll {len(SEEDS)} seeds done. Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
