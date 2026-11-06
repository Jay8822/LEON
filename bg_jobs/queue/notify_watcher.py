# bg_jobs/queue/notify_watcher.py
# Added 2026-11-04 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Phone alerts for the compute queue, via ntfy.sh (Ccode update.txt,
"JAY -- PHONE ALERTS VIA NTFY"). A separate, read-only watcher -- does
NOT import or touch job2, run_compute_queue.py, or the frozen
snapshot it runs from. Reads queue_status.json, whichever job is
RUNNING's own progress file(s) (job2's two allchannels checkpoint
files, or job1/3/4/5's own bg_jobs/queue/out/*.json), and the queue's
exitcode file -- and nothing else; writes only its own tiny state
file, to remember what it already alerted on between runs.

2026-11-05 fix: the stale check used to only ever look at job2's own
checkpoint files, so it went silently dormant for any OTHER job once
job2 finished -- confirmed this let job5's SystemExit crash sit
un-alerted for ~9 hours (Ccode update.txt). Generalized to whichever
job queue_status.json shows RUNNING. The "stopped with work left"
check used to look for a "=== Compute queue finished ===" banner in
compute_queue.log -- which never prints on a crash, the exact case
that mattered. Replaced with the exitcode file: if it's newer than
the currently-RUNNING job's own started_at, the top-level process has
already exited while that job is still (wrongly) marked RUNNING.

2026-11-06 rerun batch: added job7/8/9 (the clock-health/scorer-fix
reruns) to JOB_PROGRESS_FILES -- without this they'd have hit the same
stale blind spot the 2026-11-05 fix above describes, just for new job
keys instead of old ones. Also, Jay asked for a phone ping after EACH
channel (or seed, for the sim jobs) finishes, not batched to at most
once an hour like the old job2-only version -- _completed_channels_
and_current() (job2-only) is now _completed_units_and_current(job_key)
(job2/6/7/8's channels, job1/9's seeds, via JOB_UNIT_KIND), and the
progress block below sends one low-priority ntfy per newly-done unit,
unthrottled.

Meant to be run every 10 minutes from its own scheduled task (see
Ccode update.txt for the registration command) -- reads current
state, sends 0+ notifications, writes new state, exits. Not a daemon.

Message content is progress only: channel names, status, times. No
file paths, no personal details, no scoring/results numbers -- per
instruction, since these land on Jay's phone.

Run from the repo root:
    python -m bg_jobs.queue.notify_watcher
"""
import json
import os
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOPIC_FILE = os.path.join(REPO_ROOT, "bg_jobs", "notify_topic.txt")
STATE_FILE = os.path.join(REPO_ROOT, "bg_jobs", "notify_state.json")
EXITCODE_FILE = os.path.join(REPO_ROOT, "bg_jobs", "compute_queue.exitcode")
QUEUE_OUT_DIR = os.path.join(REPO_ROOT, "bg_jobs", "queue", "out")
STATUS_FILE = os.path.join(QUEUE_OUT_DIR, "queue_status.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "real_data_tests", "esa_adb", "results")
MISSION_FILES = ["ESA-Mission1-v2-allchannels.json", "ESA-Mission2-v2-allchannels.json"]
# 2026-11-06 rerun batch (job7/8/9): job7's own output, same per-
# channel schema as job2's MISSION_FILES above, new filenames so the
# pre-clock-health files are never touched.
CLOCKRULE_MISSION_FILES = ["ESA-Mission1-v2-allchannels-clockrule.json", "ESA-Mission2-v2-allchannels-clockrule.json"]

STALE_SECONDS = 45 * 60
SETTINGS_COUNT = 2   # STRICT/LOOSE
WINDOWS_COUNT = 3    # 1min/10min/1hour
PASSES_PER_CHANNEL = SETTINGS_COUNT * WINDOWS_COUNT

SHORT_NAME = {
    "job1_sim_50seeds": "job1", "job2_esa_adb_all_channels": "job2",
    "job3_mars_express_kicks": "job3", "job4_battery_ageing": "job4",
    "job5_cpp_proof_bigger": "job5", "job6_per_event_catch_rate": "job6",
    "job7_esa_adb_all_channels_clockrule": "job7", "job8_per_event_catch_rate_clockrule": "job8",
    "job9_sim_50seeds_rescored": "job9",
}
# Whichever job is RUNNING: its own progress file(s), used for the
# stale check. job4 writes only once, at the very end (no per-step
# checkpoint) -- falls back to just started_at, same as any job whose
# progress file doesn't exist yet.
JOB_PROGRESS_FILES = {
    "job1_sim_50seeds": [os.path.join(QUEUE_OUT_DIR, "job1_sim_50seeds.json")],
    "job2_esa_adb_all_channels": [os.path.join(RESULTS_DIR, f) for f in MISSION_FILES],
    "job3_mars_express_kicks": [os.path.join(QUEUE_OUT_DIR, "job3_mars_express_kicks.json")],
    "job4_battery_ageing": [os.path.join(QUEUE_OUT_DIR, "job4_battery_ageing.json")],
    "job5_cpp_proof_bigger": [os.path.join(QUEUE_OUT_DIR, "job5_cpp_proof_bigger.json")],
    "job6_per_event_catch_rate": [os.path.join(QUEUE_OUT_DIR, "job6_per_event_catch_rate.json")],
    "job7_esa_adb_all_channels_clockrule": [os.path.join(RESULTS_DIR, f) for f in CLOCKRULE_MISSION_FILES],
    "job8_per_event_catch_rate_clockrule": [os.path.join(QUEUE_OUT_DIR, "job8_per_event_catch_rate_clockrule.json")],
    "job9_sim_50seeds_rescored": [os.path.join(QUEUE_OUT_DIR, "job9_sim_50seeds_rescored.json")],
}
# Which "unit" each job progresses by -- a channel (job2/6/7/8) or a
# seed (job1/9) -- used to ping Jay's phone as each one finishes (Jay,
# 2026-11-06: "ping me after each channel finishes"). job3/4/5 have no
# entry: no per-unit tracking for them, only the job-level/stale/
# stopped-with-work-left checks above, unchanged.
JOB_UNIT_KIND = {
    "job2_esa_adb_all_channels": "esa_channels",
    "job7_esa_adb_all_channels_clockrule": "esa_channels",
    "job6_per_event_catch_rate": "per_event_channels",
    "job8_per_event_catch_rate_clockrule": "per_event_channels",
    "job1_sim_50seeds": "sim_seeds",
    "job9_sim_50seeds_rescored": "sim_seeds",
}


def _read_topic():
    with open(TOPIC_FILE) as f:
        return f.read().strip()


def send_ntfy(message, priority="default", title=None, tags=None):
    topic = _read_topic()
    url = f"https://ntfy.sh/{topic}"
    headers = {"Priority": priority}
    if title:
        headers["Title"] = title
    if tags:
        headers["Tags"] = tags
    req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def _channel_pass_count(channel_result):
    if channel_result is None or "error" in channel_result:
        return 0
    return sum(len(channel_result.get(setting, {})) for setting in ("STRICT", "LOOSE"))


def _esa_channel_units(paths):
    """(done channel names, most-recently-touched incomplete channel)
    from one or two job2/job7-shaped files: channel -> {setting:
    {window: ...}}, done once all PASSES_PER_CHANNEL are present."""
    done = set()
    current = None
    for path in paths:
        if not os.path.exists(path):
            continue
        data = _load_json(path, default={}) or {}
        for channel, result in data.items():
            if _channel_pass_count(result) >= PASSES_PER_CHANNEL:
                done.add(channel)
            else:
                current = channel  # dict preserves insertion order -- last wins
    return done, current


def _per_event_channel_units(path):
    """(done channel names, most-recently-touched incomplete channel)
    from a job6/job8-shaped file: tags "{prefix}_{channel}_{SETTING}",
    done once both STRICT and LOOSE exist for that channel."""
    if not os.path.exists(path):
        return set(), None
    data = _load_json(path, default={}) or {}
    settings_seen = {}
    order = []
    for tag in data:
        base, _, setting = tag.rpartition("_")
        if setting not in ("STRICT", "LOOSE"):
            continue
        settings_seen.setdefault(base, set()).add(setting)
        if base not in order:
            order.append(base)
    done = {base for base, settings in settings_seen.items() if {"STRICT", "LOOSE"} <= settings}
    current = next((base for base in reversed(order) if base not in done), None)
    return done, current


def _sim_seed_units(path):
    """(done seed labels, None) from a job1/job9-shaped file:
    {"per_seed": {"seed_201": {...}, ...}}. No partial "current" seed
    -- run_scenario() writes a seed's whole report in one shot, so a
    seed present at all is already done."""
    if not os.path.exists(path):
        return set(), None
    data = _load_json(path, default={}) or {}
    return set(data.get("per_seed", {}).keys()), None


def _completed_units_and_current(job_key):
    """Generalizes the old job2-only _completed_channels_and_current()
    to whichever job is RUNNING, by its JOB_UNIT_KIND. Returns (set(),
    None) for a job with no per-unit tracking (job3/4/5) -- the
    progress-ping block below then simply has nothing to report."""
    kind = JOB_UNIT_KIND.get(job_key)
    paths = JOB_PROGRESS_FILES.get(job_key, [])
    if kind == "esa_channels":
        return _esa_channel_units(paths)
    if kind == "per_event_channels":
        return _per_event_channel_units(paths[0]) if paths else (set(), None)
    if kind == "sim_seeds":
        return _sim_seed_units(paths[0]) if paths else (set(), None)
    return set(), None


def _latest_progress_mtime(job_key):
    """Latest mtime across whatever progress file(s) this job writes,
    or None if none exist yet (e.g. job4, which writes only once, at
    the very end -- the stale check falls back to started_at then)."""
    latest = None
    for path in JOB_PROGRESS_FILES.get(job_key, []):
        if os.path.exists(path):
            latest = max(latest or 0, os.path.getmtime(path))
    return latest


def _format_duration(started_at, finished_at):
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        t0 = time.mktime(time.strptime(started_at[:19], fmt))
        t1 = time.mktime(time.strptime(finished_at[:19], fmt))
        seconds = max(t1 - t0, 0)
    except (ValueError, TypeError):
        return "unknown time"
    if seconds < 3600:
        return f"{seconds / 60:.0f}min"
    return f"{seconds / 3600:.1f}h"


def _running_job(queue_status):
    for key, info in (queue_status or {}).items():
        if info.get("outcome") == "RUNNING":
            return key
    return None


def main():
    state = _load_json(STATE_FILE, default=None)
    first_run = state is None
    state = state or {}
    now = time.time()

    queue_status = _load_json(STATUS_FILE, default={}) or {}
    prior_statuses = state.get("job_statuses", {})
    running_job = _running_job(queue_status)
    done_units, current_unit = _completed_units_and_current(running_job) if running_job else (set(), None)

    if first_run:
        # Seed a baseline silently -- otherwise every job/unit that
        # finished before this watcher ever ran would look like a
        # brand-new transition on its very first execution.
        state["job_statuses"] = {k: v.get("outcome") for k, v in queue_status.items()}
        state["units_seen_done"] = sorted(done_units)
        state["current_unit"] = current_unit
        state["alerted_stale"] = False
        state["alerted_stopped_with_work_left"] = False
        _save_state(state)
        return

    for key, info in queue_status.items():
        name = SHORT_NAME.get(key, key)
        if info.get("outcome") == "SUCCESS" and prior_statuses.get(key) != "SUCCESS":
            duration = _format_duration(info.get("started_at"), info.get("finished_at"))
            send_ntfy(f"LEON: {name} finished (SUCCESS), {duration}.",
                      priority="default", title="LEON: job done")
        if info.get("outcome") == "FAILED" and prior_statuses.get(key) != "FAILED":
            send_ntfy(f"LEON: {name} FAILED.", priority="high",
                      title="LEON: job failed", tags="warning")

    if running_job is not None:
        running_info = queue_status[running_job]
        reference = _latest_progress_mtime(running_job)
        started = running_info.get("started_at")
        if started:
            try:
                started_ts = time.mktime(time.strptime(started[:19], "%Y-%m-%dT%H:%M:%S"))
                reference = max(reference or 0, started_ts)
            except ValueError:
                pass
        if reference is not None:
            stale_seconds = now - reference
            if stale_seconds > STALE_SECONDS:
                if not state.get("alerted_stale"):
                    send_ntfy(f"LEON: no new checkpoint for {stale_seconds / 60:.0f} min "
                              f"while {SHORT_NAME.get(running_job, running_job)} is RUNNING.",
                              priority="high", title="LEON: queue may be stuck", tags="warning")
                    state["alerted_stale"] = True
            else:
                state["alerted_stale"] = False
    else:
        state["alerted_stale"] = False

    # The process has already exited (wrote its exit code) sometime
    # after the currently-RUNNING job started, yet that job is still
    # marked RUNNING -- it crashed or was killed without the status
    # save that a clean finish (or the run_compute_queue.py FAILED
    # path) would have done. Checked via the exitcode file, not the
    # log's finished banner -- that banner never prints on a crash,
    # which is exactly the case this needs to catch (see job5, 2026-
    # 11-05).
    stopped_with_work_left = False
    if running_job is not None and os.path.exists(EXITCODE_FILE):
        started = queue_status[running_job].get("started_at")
        if started:
            try:
                started_ts = time.mktime(time.strptime(started[:19], "%Y-%m-%dT%H:%M:%S"))
                if os.path.getmtime(EXITCODE_FILE) > started_ts:
                    stopped_with_work_left = True
            except ValueError:
                pass

    if stopped_with_work_left:
        if not state.get("alerted_stopped_with_work_left"):
            send_ntfy(f"LEON: compute queue process has exited, but {SHORT_NAME.get(running_job, running_job)} "
                      f"still shows RUNNING.", priority="high", title="LEON: queue stopped early", tags="warning")
            state["alerted_stopped_with_work_left"] = True
    else:
        state["alerted_stopped_with_work_left"] = False

    # Jay, 2026-11-06: ping after EACH unit finishes, not batched to
    # at most once an hour like the old job2-only version -- one low-
    # priority ntfy per newly-done channel/seed. If several finish
    # within one 10-minute watcher tick, that's several pings, which
    # is what "after each one finishes" asks for.
    if running_job is not None:
        prior_done = set(state.get("units_seen_done", []))
        for unit in sorted(done_units - prior_done):
            send_ntfy(f"LEON: {unit} done, {SHORT_NAME.get(running_job, running_job)} RUNNING.",
                      priority="low", title="LEON: progress")

    state["job_statuses"] = {k: v.get("outcome") for k, v in queue_status.items()}
    state["units_seen_done"] = sorted(done_units)
    state["current_unit"] = current_unit
    _save_state(state)


if __name__ == "__main__":
    main()
