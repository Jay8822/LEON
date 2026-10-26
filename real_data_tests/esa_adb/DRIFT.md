# ESA-ADB long-term drift measurement

**Look, don't score.** No `GracieAgent`, no verdicts — pure
descriptive statistics on every monitored channel in both missions
(105 total: 58 Mission1 + 47 Mission2), via `measure_drift.py`. See
that script's module docstring for the exact method (labelled rows
and Communication Gap excluded; IQR for spread; one linear
units/year slope per channel; a simple >2x-IQR year-to-year heuristic
for "step changes," not a real change-point algorithm; test-period
median expressed in training-period IQRs, same shared cut-off dates
as the scored test).

## Headline finding: drift here is modest, not dramatic

This was run partly to test a hypothesis from `RESULTS.md`'s first
pass — that the large false-fault counts on `channel_43` and
`channel_45` were long-term drift pushing the test period outside
thresholds set early in the mission. **The measurement doesn't
strongly support that story.** `channel_43`'s test period sits only
0.55 training-IQRs from its training median (a modest amount), and
`channel_45` doesn't appear anywhere near the top of either ranking
below — its drift, by this measure, is unremarkable. Reporting this
plainly rather than forcing the earlier hypothesis to fit: whatever
drove those two channels' false-fault volume, median-level long-term
drift (as measured here) doesn't look like the main explanation. The
jump-sense finding in the Plan B rerun (see `RESULTS.md`) looks like
a much stronger candidate.

## Step changes

- Mission1: **1 of 58** monitored channels shows a year-to-year
  median jump bigger than 2x its own overall IQR (the heuristic's
  threshold).
- Mission2: **0 of 47**.

Both numbers are small — on this heuristic, calendar-year step
changes are rare across this dataset, not a general feature of either
mission.

## Biggest test-vs-training distance (training-period IQRs)

Mission1 (max 0.62 IQRs):

| Channel | Distance (training IQRs) |
|---|---|
| channel_59 | 0.62 |
| channel_57 | 0.62 |
| channel_58 | 0.59 |
| channel_60 | 0.59 |
| channel_43 | -0.55 |
| channel_15 | 0.52 |
| channel_23 | 0.49 |
| channel_30 | 0.47 |

Mission2 (max 0.88 IQRs):

| Channel | Distance (training IQRs) |
|---|---|
| channel_26 | 0.88 |
| channel_88 | -0.54 |
| channel_90 | -0.54 |
| channel_86 | -0.54 |
| channel_59 | -0.54 |
| channel_74 | 0.54 |
| channel_82 | 0.53 |
| channel_91 | -0.52 |

For context: a distance of "1.0 IQR" would mean the whole test period
sits a full interquartile spread away from where training saw this
channel's normal middle 50% — none of these channels get close to
that. The largest, Mission2's `channel_26`, is still under one IQR.

## Biggest drift slope (IQRs per year)

Mission1 (max ~0.11 IQR/year): `channel_60` (0.110), `channel_58`
(0.108), `channel_57` (0.093), `channel_59` (0.092), `channel_23`
(0.071), `channel_15` (0.070), `channel_43` (-0.068), `channel_38`
(0.057).

Mission2 (max ~0.35 IQR/year, notably bigger than Mission1's):
`channel_26` (0.354), `channel_74` (0.329), `channel_89` (-0.328),
`channel_86` (-0.325), `channel_88` (-0.325), `channel_82` (0.324),
`channel_87` (-0.324), `channel_90` (-0.323).

Mission2's channels drift noticeably faster, per year, than
Mission1's — worth keeping in mind if Mission2 channels get used for
anything ageing-related later (SPEC.md's new "Ageing" section).

## Honest limits

- The step-change figure is a simple heuristic (consecutive years'
  medians differing by more than 2x the channel's own overall IQR),
  not a real change-point algorithm — it could easily miss a real
  step that happens mid-year, or flag a borderline case that isn't
  one.
- The slope is a single straight line through yearly medians — it
  says nothing about whether drift is actually linear, accelerating,
  or seasonal.
- This doesn't explain `RESULTS.md`'s false-fault volume on its own,
  per the headline finding above — that's a real result, not a gap in
  this method, but it means the question "why were those two channels
  so noisy" is still open.
