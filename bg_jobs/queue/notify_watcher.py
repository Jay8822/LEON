# bg_jobs/queue/notify_watcher.py
# Added 2026-11-04 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Phone alerts for the compute queue, via ntfy.sh (Ccode update.txt,
"JAY -- PHONE ALERTS VIA NTFY"). A separate, read-only watcher -- does
NOT import or touch job2, run_compute_queue.py, or the frozen
snapshot it runs from. Reads the same files Jay/Claude already check
by hand (compute_queue.log, queue_status.json, the two allchannels
checkpoint files) and nothing else; writes only its own tiny state
file, to remember what it already alerted on between runs.

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
QUEUE_LOG = os.path.join(REPO_ROOT, "bg_jobs", "compute_queue.log")
STATUS_FILE = os.path.join(REPO_ROOT, "bg_jobs", "queue", "out", "queue_status.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "real_data_tests", "esa_adb", "results")
MISSION_FILES = ["ESA-Mission1-v2-allchannels.json", "ESA-Mission2-v2-allchannels.json"]

STALE_SECONDS = 45 * 60
PROGRESS_INTERVAL_SECONDS = 60 * 60
SETTINGS_COUNT = 2   # STRICT/LOOSE
WINDOWS_COUNT = 3    # 1min/10min/1hour
PASSES_PER_CHANNEL = SETTINGS_COUNT * WINDOWS_COUNT

EXPECTED_JOBS = [
    "job1_sim_50seeds", "job2_esa_adb_all_channels", "job3_mars_express_kicks",
    "job4_battery_ageing", "job5_cpp_proof_bigger",
]
SHORT_NAME = {
    "job1_sim_50seeds": "job1", "job2_esa_adb_all_channels": "job2",
    "job3_mars_express_kicks": "job3", "job4_battery_ageing": "job4",
    "job5_cpp_proof_bigger": "job5",
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


def _completed_channels_and_current():
    """(set of fully-done channel names, most-recently-touched
    incomplete channel or None, latest checkpoint mtime or None)."""
    done = set()
    current = None
    latest_mtime = None
    for fname in MISSION_FILES:
        path = os.path.join(RESULTS_DIR, fname)
        if not os.path.exists(path):
            continue
        latest_mtime = max(latest_mtime or 0, os.path.getmtime(path))
        data = _load_json(path, default={}) or {}
        for channel, result in data.items():
            if _channel_pass_count(result) >= PASSES_PER_CHANNEL:
                done.add(channel)
            else:
                current = channel  # dict preserves insertion order -- last wins
    return done, current, latest_mtime


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


def _format_channel_range(names):
    nums = []
    for name in names:
        try:
            nums.append(int(name.rsplit("_", 1)[1]))
        except (IndexError, ValueError):
            return ", ".join(sorted(names))
    nums.sort()
    if not nums:
        return ""
    if nums[-1] - nums[0] + 1 == len(nums):
        return f"ch{nums[0]}-{nums[-1]}" if len(nums) > 1 else f"ch{nums[0]}"
    return ", ".join(f"ch{n}" for n in nums)


def _running_job(queue_status):
    for key, info in (queue_status or {}).items():
        if info.get("outcome") == "RUNNING":
            return key
    return None


def _queue_finished_banner():
    if not os.path.exists(QUEUE_LOG):
        return False
    try:
        with open(QUEUE_LOG, errors="replace") as f:
            return "=== Compute queue finished" in f.read()
    except OSError:
        return False


def main():
    state = _load_json(STATE_FILE, default=None)
    first_run = state is None
    state = state or {}
    now = time.time()

    queue_status = _load_json(STATUS_FILE, default={}) or {}
    prior_statuses = state.get("job_statuses", {})
    done_channels, current_channel, checkpoint_mtime = _completed_channels_and_current()

    if first_run:
        # Seed a baseline silently -- otherwise every job/channel
        # that finished before this watcher ever ran would look like
        # a brand-new transition on its very first execution.
        state["job_statuses"] = {k: v.get("outcome") for k, v in queue_status.items()}
        state["channels_seen_done"] = sorted(done_channels)
        state["current_channel"] = current_channel
        state["last_progress_alert_time"] = now
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

    running_job = _running_job(queue_status)

    job2_info = queue_status.get("job2_esa_adb_all_channels", {})
    if job2_info.get("outcome") == "RUNNING" and checkpoint_mtime is not None:
        reference = checkpoint_mtime
        started = job2_info.get("started_at")
        if started:
            try:
                reference = max(reference, time.mktime(time.strptime(started[:19], "%Y-%m-%dT%H:%M:%S")))
            except ValueError:
                pass
        stale_seconds = now - reference
        if stale_seconds > STALE_SECONDS:
            if not state.get("alerted_stale"):
                send_ntfy(f"LEON: no new checkpoint for {stale_seconds / 60:.0f} min "
                          f"while {SHORT_NAME.get(running_job, running_job or 'a job')} is RUNNING.",
                          priority="high", title="LEON: queue may be stuck", tags="warning")
                state["alerted_stale"] = True
        else:
            state["alerted_stale"] = False

    all_done = all(queue_status.get(job, {}).get("outcome") == "SUCCESS" for job in EXPECTED_JOBS)
    if _queue_finished_banner() and not all_done:
        if not state.get("alerted_stopped_with_work_left"):
            send_ntfy("LEON: compute queue process has exited, but not every job shows SUCCESS yet.",
                      priority="high", title="LEON: queue stopped early", tags="warning")
            state["alerted_stopped_with_work_left"] = True
    else:
        state["alerted_stopped_with_work_left"] = False

    prior_done = set(state.get("channels_seen_done", []))
    newly_done = sorted(done_channels - prior_done)
    last_progress = state.get("last_progress_alert_time", 0)
    if newly_done and running_job and (now - last_progress) >= PROGRESS_INTERVAL_SECONDS:
        range_str = _format_channel_range(newly_done)
        on_str = f", on {current_channel}" if current_channel else ""
        send_ntfy(f"LEON: {range_str} done{on_str}, {SHORT_NAME.get(running_job, running_job)} RUNNING.",
                  priority="low", title="LEON: progress")
        state["last_progress_alert_time"] = now

    state["job_statuses"] = {k: v.get("outcome") for k, v in queue_status.items()}
    state["channels_seen_done"] = sorted(done_channels)
    state["current_channel"] = current_channel
    _save_state(state)


if __name__ == "__main__":
    main()
