# COROS workout ("course") JSON — cheat sheet

Used by `createScheduledWorkout`, `updateScheduledWorkout`, `createSingleWorkout`, `updateWorkoutDetails`
and by the `course:` field of sessions in `plans/*/plan.yaml`. `scripts/plan.py validate` checks every rule
below. The authoritative rules are in the live tool description: `scripts/coros.py describe createScheduledWorkout`.

## Course

```json
{
  "courseName": "≤100 chars, athlete-facing",
  "courseDescription": "non-empty, plain coaching language: what to do, at what intensity, why",
  "sportType": 1,
  "sections": [ ... ]
}
```

- `sportType`: **1 running, 2 cycling, 5 trail running** (4 = rest, training plans only).
- Never set `dayNo` (scheduled workouts take the `date` argument) or `strengthBodypart`.
- Name/description are shown on the watch as-is: no JSON field names, enum numbers, or internal IDs.

## Plain section

| Field | Values |
|---|---|
| `sectionType` | 1 warm-up · 2 training · 3 recovery · 4 cool-down (inside interval groups: only 2 or 3) |
| `targetType` | 1 distance (m) · 2 time (s) · 3 climb (m, trail only) · **4 free** (ends with the lap button) |
| `targetValue` | positive integer for 1/2/3; **omit** for 4 |
| `intensityType` | 1 heart rate · 2 pace · 3 % effort threshold pace (trail only) · 4 power |

Allowed target types: running 1/2/4, cycling 1/2/4, trail 1/3/4 (no time target on trail).
Allowed intensity types: running 1/2/4, cycling 1/4, trail 1/2/3/4.

### Intensity — exactly one format per section, or none at all

| Format | Fields | Notes |
|---|---|---|
| Zone | `sectionIntensity` 1–6 (cycling power FTP zones 1–7) | Zones derive from the athlete's COROS thresholds. Not for running power. |
| Percent | `intensityPercentStart` < `intensityPercentEnd` | % of **LTHR** (type 1, 20–120) or **threshold pace** (type 2/3, 20–140). Never for power. |
| Absolute | `intensityValueStart`, `intensityValueEnd` | HR 30–240 bpm · pace 120–1499 **s/km** (4:05/km = 245) · power 10–2000 W. Single value → both ends equal. |

- **No intensity**: omit `intensityType` *and* every format field. Only when the user asks for it (warm-ups
  "without target", recoveries "just jog"). Never send `0`.
- Pace is seconds per km; smaller = faster. Mile pace: convert to s/km and round.
- Prefer zones unless the user gave numbers; never convert user numbers to zones.
- `%effort threshold pace` (type 3) is grade-adjusted and trail-only, zones or percents only.

## Interval group

```json
{"intervalGroup": true, "repeats": 4, "sets": [
  {"sectionType": 2, "targetType": 1, "targetValue": 1000, "intensityType": 2,
   "intensityValueStart": 245, "intensityValueEnd": 245},
  {"sectionType": 3, "targetType": 2, "targetValue": 120}
]}
```

- `repeats` 1–20, `sets` non-empty, **no nesting**, no target/intensity fields on the container.
- The recovery inside the group is also executed after the last repetition. To avoid it, put
  `repeats: N-1` in the group and append the last work section as a plain section after the group.

## Free mode

`{"sectionType": 1, "targetType": 4}` — the athlete presses lap to end the section. Free sections are excluded
from COROS duration/distance/load estimates (so the estimate after creation looks shorter than reality).
Use it **only when requested** (e.g. "warm-up until ready", "cool-down with manual end").

## Full examples

See `.claude/skills/run-workout/examples/`:

| File | Pattern |
|---|---|
| `intervals-4x1000-free-wu-cd.json` | free warm-up, 4×1000 m @ 4:05/km, 2′ rest, free cool-down (created live on 2026-10-03) |
| `tempo-20min.json` | 15′ warm-up zone 1, 20′ at threshold pace range, 10′ cool-down |
| `long-run-mp-finish.json` | long run 70′ easy + 20′ at marathon pace |
| `hills-8x60s.json` | hill repeats by time with HR recovery |
| `easy-run-strides.json` | easy run + 6×20″ strides |
| `bike-endurance-hr.json` | 90′ endurance ride with HR range |
| `trail-climb.json` | trail repeats by climb target with % effort threshold pace |
