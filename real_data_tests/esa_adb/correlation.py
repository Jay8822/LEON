# real_data_tests/esa_adb/correlation.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Shared training-only correlation method, used by both Step 3
(command/event -> channel linking, learn_context.py) and Step 4.3
("which channels jitter together", stand_in_blueprint.py) -- Jay's
instruction was that both use the same method and the same bar.
Test-harness only; GracieAgent never sees any of this directly (the
"keep the agents lean" rule) -- callers just hand it a plain
`expected_causes` set or a `linked_channels` tuple.

Method (fixed, agreed with Jay before any result was looked at):
- During the TRAINING period only, compare how often a TRIGGER time is
  followed, within a fixed reaction window, by a TARGET event -- against
  the same rate measured from CORRELATION_N_RANDOM random control times
  drawn from the same training period (fixed seed, reproducible).
- Linked only if BOTH hold: at least CORRELATION_MIN_COOCCURRENCES real
  co-occurrences, AND the trigger rate is at least
  CORRELATION_LIFT_THRESHOLD times the random rate. Both numbers are
  fixed, labelled test choices agreed in advance, not tuned afterwards.
- Three reaction windows are used throughout this round, fixed in
  advance as labelled test choices: 1 minute, 10 minutes, 1 hour. Every
  caller reports all three, never just the nicer-looking one.
"""

import bisect
import random

CORRELATION_SEED = 20261026
CORRELATION_N_RANDOM = 1000
CORRELATION_LIFT_THRESHOLD = 3.0
CORRELATION_MIN_COOCCURRENCES = 10

REACTION_WINDOWS_SECONDS = {"1min": 60.0, "10min": 600.0, "1hour": 3600.0}


def hit_rate(trigger_times, target_times_sorted, window_seconds):
    """Fraction of trigger_times with >=1 target time in (t, t+window],
    and the raw co-occurrence count."""
    if not trigger_times:
        return 0.0, 0
    hits = 0
    for t in trigger_times:
        lo, hi = t, t + window_seconds
        i = bisect.bisect_right(target_times_sorted, lo)
        j = bisect.bisect_right(target_times_sorted, hi)
        if j > i:
            hits += 1
    return hits / len(trigger_times), hits


def random_control_times(period_start_ts, period_end_ts, n=CORRELATION_N_RANDOM,
                          seed=CORRELATION_SEED):
    rng = random.Random(seed)
    span = period_end_ts - period_start_ts
    return sorted(period_start_ts + rng.random() * span for _ in range(n))


def is_linked(trigger_times, target_times_sorted, window_seconds,
              period_start_ts, period_end_ts, control_times=None):
    """Returns a dict: linked (bool), trigger_rate, random_rate,
    n_cooccurrences -- reported in full, not just the verdict, so a
    write-up can show its working."""
    trigger_rate, n_cooc = hit_rate(trigger_times, target_times_sorted, window_seconds)
    if control_times is None:
        control_times = random_control_times(period_start_ts, period_end_ts)
    random_rate, _ = hit_rate(control_times, target_times_sorted, window_seconds)

    if n_cooc < CORRELATION_MIN_COOCCURRENCES:
        linked = False
    elif random_rate == 0:
        linked = trigger_rate > 0
    else:
        linked = trigger_rate >= CORRELATION_LIFT_THRESHOLD * random_rate

    return {
        "linked": linked,
        "trigger_rate": trigger_rate,
        "random_rate": random_rate,
        "n_cooccurrences": n_cooc,
    }
