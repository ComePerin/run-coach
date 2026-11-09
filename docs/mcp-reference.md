# COROS MCP — reference

Everything learned by exploring the **official COROS MCP server** (`coroslab/COROS-MCP`) against a real account
(EU region, October 2026). The server is the source of truth: re-check with `scripts/coros.py tools --refresh`
and `scripts/coros.py describe <tool>` — the GitHub README already lags behind (it lists 32 tools and calls the
sleep tool `querySleepData`; the live server exposes **34** tools and the tool is `querySleepOverview`).

## Endpoints and auth

| | |
|---|---|
| Global endpoint | `https://mcp.coros.com/mcp` (redirects to the account's region) |
| Regional endpoints | EU `https://mcpeu.coros.com/mcp` · US `https://mcpus.coros.com/mcp` · CN `https://mcpcn.coros.com/mcp` |
| Auth | OAuth 2 (scopes `openid offline_access mcp.tools`). For CLI agents: device-style flow — the helper prints a login URL, the user signs in in any browser, the helper polls and stores tokens |
| Transport | Stateless streamable HTTP (no `Mcp-Session-Id`, no `notifications/initialized`) |
| Token storage | `~/.coros-mcp-skill-gateway/<region>/` (outside the repo, auto-refreshed) |
| Cost | Free on the COROS side |

Two ways to use it:

1. **As a connector** in Claude / ChatGPT / Codex: add `https://mcp.coros.com/mcp` as a custom MCP server and log in
   through the browser. Tools then appear natively (`mcp__coros__querySportRecords`, …).
2. **Through the helper script** (what this repo uses, works in headless containers):
   `scripts/coros.py call <tool> '<json args>'`. It wraps the official `coros_mcp_login.py` that
   `scripts/setup.sh` downloads into `.vendor/`.

## Tool catalog (34 tools, 27 read-only)

### Activities

| Tool | R/W | Arguments (required in **bold**) |
|---|---|---|
| `querySportRecords` | R | **startDate**, **endDate**, **sportTypeCodes**, **minDistanceKm**, **maxDistanceKm**, **minDurationMinutes**, **maxDurationMinutes**, **maxAveragePace**, **locationKeyword**, **limit** |
| `getActivityDetail` | R | **labelId**, **sportType** |
| `analyzeActivityDetail` | R | **labelId**, **sportType**, **focus** |
| `queryActivityLapData` | R | **labelId**, **sportType** |
| `queryCustomActivityLapData` | R | **labelId**, **sportType**, **startTimestamp**, **endTimestamp** |
| `downloadActivityFitFiles` | R | endDate, sportType, labelId, startDate, limit |
| `queryActivityFitFileDownloadUrls` | R | endDate, sportType, labelId, startDate, limit |

### Health & recovery

| Tool | R/W | Arguments (required in **bold**) |
|---|---|---|
| `queryDailyHealthData` | R | days |
| `querySleepOverview` | R | startDate, endDate, days |
| `querySleepHrv` | R | **startDate**, **endDate**, **days** |
| `queryAvgHeartRate` | R | startDate, endDate, days |
| `queryRestingHeartRate` | R | days |
| `queryStressLevel` | R | days |
| `queryStressTimeSeries` | R | **startDate**, **endDate**, **days** |
| `queryHealthCheckTimeSeries` | R | **startDate**, **endDate**, **days** |
| `queryRecoveryStatus` | R | — |
| `queryMenstruationCycles` | R | startDay, endDay |

### Fitness & load

| Tool | R/W | Arguments (required in **bold**) |
|---|---|---|
| `queryFitnessAssessmentOverview` | R | — |
| `queryTrainingLoadAssessment` | R | days |

### Calendar & plans

| Tool | R/W | Arguments (required in **bold**) |
|---|---|---|
| `queryTrainingSchedule` | R | startDate, endDate |
| `queryScheduledWorkoutDetails` | R | **date**, **idInPlan** |
| `createScheduledWorkout` | **W** | **date**, **course** |
| `updateScheduledWorkout` | **W** | **date**, **idInPlan**, **course** |
| `queryTrainingPlanLibrary` | R | statusList, planType, weeks, cursor |
| `queryTrainingPlanDetails` | R | **planId**, startDay, endDay |
| `createTrainingPlan` | **W** | **planInfo**, **courseList**, **phaseInfo** |
| `updateTrainingPlan` | **W** | **planInfo**, courseList, phaseInfo |

### Workout library

| Tool | R/W | Arguments (required in **bold**) |
|---|---|---|
| `queryWorkoutLibrary` | R | sportType, courseType |
| `queryWorkoutDetails` | R | **workoutId** |
| `createSingleWorkout` | **W** | **course** |
| `updateWorkoutDetails` | **W** | **workoutId**, **course** |
| `scheduleWorkout` | **W** | **workoutId**, **date** |

### Profile

| Tool | R/W | Arguments (required in **bold**) |
|---|---|---|
| `queryUserInfo` | R | — |
| `queryDevices` | R | — |

## Output formats and units — read before parsing

- **Most tools return text written for an LLM**, double JSON-encoded (`content[0].text` is a JSON string).
  `scripts/coros.py` decodes it; `scripts/parsers.py` turns the common ones into data.
- **Lap tools return JSON** (`columns` + `lapGroups[].laps[]`) with **Chinese column labels** and raw units:
  - `distance` in **centimetres** (`100000` = 1 km), `time`/`totalLength` in seconds,
  - `avgPace`/`adjustedPace` in **seconds per km**, `avgSpeedV2` in km/h × 100 (`1130` = 11.3 km/h),
  - `lapGroups[].type`: `10` = per km, `2` = auto laps, `11` = per 5 km, `-1` = whole activity.
  - For bouldering the "laps" are routes with `grade`, `style`, `avgHr`, `maxHr`.
- Dates in arguments are `yyyyMMdd` strings; outputs use `YYYY-MM-DD`. Timestamps are Unix seconds.
- **Sleep, HRV and daily health are dated by the wake-up day** (the night 2→3 Oct is `2026-10-03`).
- Tool texts end with instructions for the model ("Do not show Plan ID to the user"). Respect them: never show
  `labelId`, `idInPlan`, plan or workout IDs to the user.

## Limits and quirks observed

| Topic | Behaviour |
|---|---|
| `querySportRecords` | **All 10 arguments are required** (pass `null` for unused filters, `[65535]` for all sports). Max **100** records per call → split long ranges (`plan.py` does it). |
| 7-day caps | `querySleepHrv`, `queryStressTimeSeries` and recent-day `queryHealthCheckTimeSeries` queries are capped at 7 days. |
| FIT files | `downloadActivityFitFiles` max 10 per call, **50 per calendar day**. `queryActivityFitFileDownloadUrls` returns S3 URLs that are **downloadable without any authentication** — treat them as secrets (they contain full GPS tracks). |
| FIT parsing | `fitparse` fails on COROS files ("invalid field size"); **`fitdecode` works** (`check_crc=False`). Records: timestamp, lat/long, distance, heart_rate, altitude, speed, cadence, power, stance_time, vertical_oscillation, vertical_ratio, step_length, developer field `Effort Pace`. |
| Stress | `queryStressLevel` buckets (relaxed/low/medium/high) came back as "No data"; the time series reports `timezone=8` regardless of the user's zone. |
| HRV | `queryDailyHealthData` reports an "HRV Baseline" (~42 ms) that differs from the **sleep HRV baseline** in `querySleepHrv` (~68 ms). Use `querySleepHrv` (official normal range + evaluation) for readiness. |
| `analyzeActivityDetail` | Generic server-side summary; better to analyse `getActivityDetail` + laps yourself. |
| Training plans | Plans synced from **TrainingPeaks** are listed by `queryTrainingSchedule` but are **read-only** via MCP (`Editable via MCP: no`). Strength (sport 4) days cannot be expressed. |
| Library workouts | Workouts with an **empty description** are not editable via MCP. Always write a description. |
| Write scope | Create/update only for **running (1), cycling (2), trail running (5)**. Dates: today → today+90. **No delete, no move**, no quitting plans — those require the COROS app. |
| Duplicates | `createScheduledWorkout` has **no duplicate protection**: a retry after a timeout can create a second copy. Check `queryTrainingSchedule` before retrying. |
| Scheduled IDs | `updateScheduledWorkout` may return a **new `idInPlan`** — always store the returned one. |

## Sport type codes

Activity codes (used by `querySportRecords`, lap and detail tools) are **not** the same as workout codes
(`sportType` 1/2/4/5 in course JSON).

- Run 100 outdoor, 101 indoor, 102 trail, 103 track, 104 hike, 105 mountain climb, 106 multi-pitch
- Bike 200 outdoor, 201 indoor, 202 e-bike, 203 gravel, 204 MTB, 205 e-MTB, 299 helmet bike
- Swim 300 pool, 301 open water · Cardio/strength 400 gym cardio, 401 GPS cardio, 402 strength
- Ski 500 ski, 501 snowboard, 502 XC ski, 503 touring · Climb 800 indoor, 801 bouldering, 802 outdoor
- Walk/fitness 900 walk, 901 jump rope, 902 stairs, 903 elliptical, 904 yoga, 905 pilates, 906 boxing
- Ball 1000–1006 (… 1005 tennis, 1006 padel) · Hybrid fitness 1200 · Triathlon 10000 · **All: 65535**

## Safe-write protocol (from the official skill guidance)

1. Read before you write (`queryTrainingSchedule` → `queryScheduledWorkoutDetails`, or plan/library details).
2. Writes require an explicit user request; a proposal or advice is not authorisation.
3. Submit the **complete** course on updates (full replacement), preserving untouched sections.
4. Check `isError` and the returned text; on timeout **do not retry blindly** — query the calendar first.
5. Read the result back and report other workouts present on the same day.

See [`course-json.md`](course-json.md) for the workout format.
