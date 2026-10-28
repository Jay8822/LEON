# bg_jobs/queue/run_compute_queue.py
# Added 2026-10-28 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Runs all 5 "keep the laptop working while usage is low" jobs
(Ccode update.txt) back to back, ONE AT A TIME, never concurrently --
this machine has 6GB RAM and has crashed from memory pressure
multiple times this session. If a job fails, logs it plainly and
moves to the NEXT job -- never retries blindly, never lets one
failure block the rest of the queue.

Launch via the existing detached mechanism (bg_jobs/run_detached.bat,
Task Scheduler), exactly like every other long job this session:

    schtasks /Create /TN "LEON_compute_queue" /TR "\"<repo path>\bg_jobs\run_detached.bat\" compute_queue bg_jobs.queue.run_compute_queue" /SC ONCE /ST 23:59 /F
    schtasks /Run /TN "LEON_compute_queue"

Each job already does its own internal checkpointing (per seed/
channel/year/battery) and writes its own result file under
bg_jobs/queue/out/ or real_data_tests/esa_adb/results/ (job 2 only,
kept separate from the existing 16-channel files) -- this runner adds
one more thing on top: a single queue-level log
(bg_jobs/queue/out/queue_status.json) recording which jobs have
started/finished/failed, so progress can be checked at a glance
without reading every job's own log.

Run from the repo root (normally via the detached wrapper above, not
directly):
    python -m bg_jobs.queue.run_compute_queue
"""
import datetime
import json
import os
import sys
import traceback

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
STATUS_PATH = os.path.join(OUT_DIR, "queue_status.json")

# (status key, module name, one-line description) -- run in this
# fixed order. Module, not a direct import, so one job's import-time
# error can't take down the ones after it either.
JOBS = [
    ("job1_sim_50seeds", "bg_jobs.queue.job1_sim_50seeds",
     "Sim, 50 fresh seeds (201-250), frozen Item-C rule book"),
    ("job2_esa_adb_all_channels", "bg_jobs.queue.job2_esa_adb_all_channels",
     "ESA-ADB v2 method on all monitored channels not in the original 16"),
    ("job3_mars_express_kicks", "bg_jobs.queue.job3_mars_express_kicks",
     "Mars Express expected-kicks measurement, look only"),
    ("job4_battery_ageing", "bg_jobs.queue.job4_battery_ageing",
     "NASA battery ageing measurement, look only"),
    ("job5_cpp_proof_bigger", "bg_jobs.queue.job5_cpp_proof_bigger",
     "C++ proof on full channel_62 plus channel_63/64/65"),
]

PROOF_EXE_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "AI Stack C++ Test Build", "build", "proof_gracie_rulebook.exe",
)


def _load_status():
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH) as f:
            return json.load(f)
    return {}


def _save_status(status):
    with open(STATUS_PATH, "w") as f:
        json.dump(status, f, indent=2, default=str)


def _now():
    return datetime.datetime.now().isoformat()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    status = _load_status()
    print(f"=== Compute queue starting, {_now()} ===")

    for key, module_name, description in JOBS:
        if status.get(key, {}).get("outcome") == "SUCCESS":
            print(f"[{key}] already SUCCESS from a prior run -- skipping. ({description})")
            continue

        print(f"\n[{key}] STARTING, {_now()} -- {description}")
        status[key] = {"outcome": "RUNNING", "started_at": _now()}
        _save_status(status)

        try:
            import importlib
            module = importlib.import_module(module_name)
            if key == "job5_cpp_proof_bigger":
                # job5's main() takes the proof executable path as argv[1]
                sys.argv = [module_name, PROOF_EXE_DEFAULT]
            module.main()
            status[key] = {"outcome": "SUCCESS", "started_at": status[key]["started_at"], "finished_at": _now()}
            print(f"[{key}] SUCCESS, {_now()}")
        except Exception:
            tb = traceback.format_exc()
            status[key] = {
                "outcome": "FAILED", "started_at": status[key]["started_at"],
                "finished_at": _now(), "traceback": tb,
            }
            print(f"[{key}] FAILED, {_now()} -- logged, moving to the next job.\n{tb}")
        _save_status(status)

    print(f"\n=== Compute queue finished, {_now()} ===")
    for key, _, _ in JOBS:
        print(f"  {key}: {status.get(key, {}).get('outcome', 'NEVER STARTED')}")


if __name__ == "__main__":
    main()
