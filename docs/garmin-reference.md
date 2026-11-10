# Garmin — reference

How this repo uses Garmin data, what works, and what does not. Explored against a real account in November 2026
with the official client `garmin-connect-personal-api-python` 1.0.

## Personal API in one table

| | |
|---|---|
| What | Garmin's official [Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api) for individuals (opened October 2026) |
| Base URL | `https://personal.connectapi.garmin.com` |
| Auth | a **Personal API key** you create at <https://connect.garmin.com/app/settings/personalApiToken>, exchanged for short-lived bearer tokens (cached by the client in `~/.config/garmin/`) |
| Key lookup | `$GARMIN_PERSONAL_API_KEY`, else `~/.config/garmin/connect-personal-api-key` (`scripts/setup.sh --garmin` writes it with mode 600) |
| Access | **read-only** (every endpoint is a `GET`). No workout, calendar, training-plan, VO2max, training-load, training-readiness or recovery-time endpoint |
| Client | `garmin-connect-personal-api-python` (Apache-2.0, **Python ≥ 3.12**) — installed by the `garmin` extra |
| Wrapper | `scripts/garmin.py status | endpoints | call NAME '{json}'`, raw responses cached in `.cache/garmin/` |

## Endpoints used by the coach

| Need | Client method | Fields used | Normalized by |
|---|---|---|---|
| Activities | `search_activities(start, limit, start_date, end_date)` (paged by 100) | `activityId`, `startTimeLocal`, `activityType.typeKey`, `distance` (m), `duration` (s), `averageSpeed` (m/s), `averageHR`, `hrTimeInZone_1..5` (s), `fastestSplit_*` (s), `aerobicTrainingEffect` | `garmin_parsers.parse_activities` |
| HRV | `get_daily_hrv_summaries(start, end)` | `hrvSummaries[].lastNightAvg`, `weeklyAvg`, `baseline.balancedLow/Upper`, `status` | `parse_hrv` |
| Resting HR | `get_daily_summaries(start, end)` | `data[].heartRate.restingValue` | `parse_resting_hr` |
| Sleep | `get_daily_sleep_summaries(start, end)` | `sleepTimeSeconds`, `deepSleepSeconds`, `sleepScores.overall.value` (when present) | `parse_sleep` |
| Recovery | `get_daily_body_battery(start, end)` | `bodyBatteryValuesArray` `[timestamp, value]` pairs → the day's peak | `parse_body_battery` |
| Athlete | `get_user_profile_settings`, `get_weight_measurements` | units, latest weight (g) | `parse_user` |

Other read-only endpoints (stress, steps, SpO2, heart-rate zones, fitness age, single activity, original activity
file as ZIP…) are available through `scripts/garmin.py call`; list them with `scripts/garmin.py endpoints`.

Activity types are mapped to families by `typeKey`: `*_running`/`running`/`treadmill_running` → run,
`trail_running` → trail, `*cycling*`/`*biking*` → bike, `*swimming*` → swim, `hiking` → hike, everything else → other.

## What the coach computes instead (Garmin only)

| COROS gives | Garmin substitute | Where |
|---|---|---|
| Training load ratio (short/long) | **ACWR from Edwards TRIMP**: Σ minutes in HR zone *i* × *i* per activity; 7-day sum ÷ (28-day sum ÷ 4). Activities without HR zones count with the median TRIMP/min | `readiness.load_from_activities` |
| Threshold pace, race predictions | **Riegel** (exponent 1.06) from the best 5k / 10k / half / marathon split of the last 8 weeks; threshold = pace of the predicted 60-minute race | `readiness.estimate_fitness` |
| Recovery % | **Body Battery** peak of the day (same thresholds: < 20, < 70, ≥ 90) | `garmin_parsers.parse_body_battery` |
| VO2max, running level | none — left empty | |

The estimates are only as good as the recent efforts: if the athlete has not run hard for 8 weeks the threshold pace
is too slow. Say so, and prefer a recent race or a field test (30-min time trial) entered by hand in the profile.

## Workouts → FIT files

The API cannot write, so workouts are delivered as **FIT workout files** generated from the same course JSON as
COROS (`docs/course-json.md`):

```bash
.venv/bin/python scripts/workout.py export 2026-11-12 course.json --yes   # → exports/2026-11-12-<name>.fit
.venv/bin/python scripts/plan.py push plans/<slug> --days 7 --yes         # Garmin provider: exports the next 7 days
```

Copy each file into `GARMIN/NewFiles/` on the watch (USB). Recent watches connect over MTP instead of USB mass
storage: use the file manager (Linux: `gio`/GVFS, macOS: Android File Transfer or OpenMTP). After unplugging, the
watch imports the file and lists it under *Training → Workouts*. FIT workouts are **not dated**: the athlete starts
them from the list on the planned day, and they do not appear in the Garmin Connect calendar.

**Garmin Connect's website cannot import workout files.** *Import Data* only accepts activities and courses, and
answers *"One of your files was not accepted by the system. Please contact Support for assistance."* for any
workout `.fit`, including files copied from a Garmin watch (community reports:
[1](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/383688/workout-fit-file-not-importing-copied-from-watch),
[2](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/412177/import-workout-to-garmin-connect),
[3](https://forums.garmin.com/developer/fit-sdk/f/discussion/426425/the-fit-workout-generated-by-a-tool-i-made-keeps-getting-rejected-by-the-garmin-connect-website/2005568)).
That error does not mean the file is malformed: run `scripts/fitworkout.py check FILE.fit`. The watch is the only
destination.

### Checking pipeline

Every generated file is checked before it is written (`course_to_fit` raises `FitCheckError` otherwise), and the
same checks run in `pytest` / CI on every exportable example:

1. **Garmin's official FIT SDK** (`garmin-fit-sdk`) decodes it: FIT signature, header and CRC integrity, no decode
   errors.
2. **fit-tool's conformance validator** (wire format, full profile, workout file-type rules).
3. **Round trip**: the decoded steps are compared with the course JSON — step count, durations, targets (speed
   range covers the pace, bpm, zones), repeat steps pointing back to the right step with the right count.

Check existing files by hand with `.venv/bin/python scripts/fitworkout.py check exports/*.fit`.

One fit-tool rule is ignored on purpose: it wants `num_valid_steps` to exclude repeat steps. Garmin's profile only
says "number of valid steps"; we count every step message, as Garmin's own workout files do.

Limits of the conversion (`fitworkout.validate_for_garmin` rejects them with a clear message):

| COROS feature | Garmin |
|---|---|
| Climb target (`targetType` 3) | not supported — use time or distance |
| % effort pace (`intensityType` 3) | not supported — use pace, HR or power |
| Percent of LTHR / threshold pace | not supported — use absolute values |
| Pace zones (`sectionIntensity` with pace) | not supported — give the pace range from `plan.py zones` |
| HR zone 6 | Garmin has 5 HR zones |

Single paces become a ±5 s/km window (the watch needs a range). HR targets are written as bpm, power as watts,
HR/power zones as Garmin zones (from the athlete's Garmin settings).

## Not verified yet

- HRV field names come from Garmin's documented `hrv-service` shape; the test account had no HRV data.
- `sleepScores` is not returned by `dailySleepSummariesByDate` for every device; without it, only sleep duration is
  scored.

Please open an issue with a (redacted) response shape if your watch returns something different.

## Claude chat (no scripts)

For Claude Desktop, the community MCP server [`garmin-personal-mcp`](https://github.com/Mason-Levyy/garmin-personal-mcp)
(uses the same Personal API key) exposes these endpoints as tools. Add it as a local MCP server
(`uvx garmin-personal-mcp`) and use the instructions in `claude-chat/project-instructions.md`.
