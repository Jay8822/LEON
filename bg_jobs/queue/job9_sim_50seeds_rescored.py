# bg_jobs/queue/job9_sim_50seeds_rescored.py
# Added 2026-11-06 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 9 ("JAY -- SMALL BUILD NOW, THEN ALL RERUNS IN THE
BACKGROUND", item 3c). Same 50 seeds (201-250), same frozen Item-C
rule book, as job1_sim_50seeds.py -- rerun because score_faults()
itself was fixed (sim/run_sim_test.py, commit 0fa0a92): a catch now
only counts inside a fault's own window plus grace, and gets no
credit if the channel was already latched FAULT when the fault
started. job1's own checkpoint already has all 50 seeds marked done
under the OLD scorer, so simply rerunning job1 would skip every one
of them (its resume check is "is this seed present at all", not "was
it scored with the current code") -- this writes to its own, separate
output instead of touching job1's.

Not a clock-health rerun (unlike job7/job8) -- the simulated craft has
no ESA-style backward timestamps, so this is purely about the scorer
fix. Named "_rescored", not "_clockrule", for that reason.

NO design changes to sim/blueprint.py, sim/rulebook.py, sim/
fault_injection.py, or sim/run_sim_test.py beyond the already-committed
scorer fix -- reuses run_scenario() and job1's own _flatten_metrics/
summarize helpers directly, not reimplemented.

Results go to bg_jobs/queue/out/job9_sim_50seeds_rescored.json -- a
new file; job1's own output is untouched.

Checkpointed per seed (resumable), same cost class as job1 (~69s/seed
observed, so ballpark under an hour for all 50 -- far lighter than
job7/job8).

Run from the repo root:
    python -m bg_jobs.queue.job9_sim_50seeds_rescored
"""
import json
import os
import time

from sim.rulebook import build_rule_book
from sim.run_sim_test import run_scenario
from bg_jobs.queue.job1_sim_50seeds import SEEDS, _flatten_metrics, summarize, current_working_set_bytes

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUT_PATH = os.path.join(OUT_DIR, "job9_sim_50seeds_rescored.json")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Job 9: sim, same 50 seeds (201-250) as job 1, rescored with the fixed score_faults().")
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
