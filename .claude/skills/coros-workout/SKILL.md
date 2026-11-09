---
name: coros-workout
description: Create or edit a single structured workout (running, cycling or trail running) directly on the user's COROS calendar so it syncs to their watch. Use when the user asks to add, create, schedule, put on the watch, modify or shorten one workout on a given day, e.g. "create a 4x1000 at 4:05 for today", "add a 45-minute easy ride tomorrow", "make Thursday's tempo 15 minutes shorter".
---

# COROS workout builder

Turn a natural-language workout into COROS course JSON, validate it, save it on one date of the COROS calendar,
and read it back. Uses `scripts/workout.py` (wrapper around the official COROS MCP helper).

Prerequisite: `scripts/coros.py status` must say "COROS MCP OK". If not, follow *Setup* in `AGENTS.md` (the user
must open a login link — never ask for their password). If the COROS MCP is connected natively as a connector
(`mcp__coros__*` tools), you may call the same tools directly; the rules below are identical.

## Workflow

1. **Resolve the request**
   - Date → `YYYY-MM-DD` in the athlete's timezone ("today", "tomorrow", "Thursday"). Allowed: today … today+90.
   - Sport → running (1), cycling (2), trail running (5). Strength, swimming and other sports cannot be created here:
     say so.
   - Structure → warm-up / work / recovery / cool-down sections, interval groups (repeats ≤ 20, no nesting).
   - Targets → distance when the user speaks in m/km ("4x1000"), time when in minutes, climb for trail D+.
     **Free mode** (`targetType: 4`, ends with the lap button) only when the user asks for it
     ("no target", "manual end", "until ready").
   - Intensity → exactly what the user gave: pace `m:ss/km` → absolute pace in s/km (4:05 → 245, both ends equal for a
     single value); bpm → absolute HR; "%" → ask the basis if unclear (COROS percentages are of LTHR or threshold
     pace, not HRmax); "zone N" → `sectionIntensity`. Words like "easy / threshold / marathon pace" → use the athlete's
     zones (`.venv/bin/python scripts/plan.py zones`) as an absolute pace range. **No intensity** only when asked
     ("rest", "no target", "just jog") — then omit every intensity field.
   - If something essential is missing (date, sport, main set), ask one short question. Otherwise do not ask.

2. **Write the course JSON** to a temp file following `docs/course-json.md`. Start from the closest file in
   `examples/`. Name ≤ 100 chars and a **non-empty description** in the user's language, in plain coaching words
   (no field names, no numbers like "intensityType 2"). Without a description the workout cannot be edited later.

3. **Validate and dry-run**
   ```bash
   .venv/bin/python scripts/workout.py create 2026-10-03 /tmp/course.json
   ```
   This validates, estimates the duration, and lists what is already scheduled that day. Fix any `INVALID` line.

4. **Confirm** — show the user a short readable structure (not JSON) and the other workouts that day.
   Skip the confirmation only if the user already gave the complete specification *and* explicitly asked to create it.

5. **Create** (a write to the user's COROS account):
   ```bash
   .venv/bin/python scripts/workout.py create 2026-10-03 /tmp/course.json --yes
   ```
   The script creates, then reads the workout back. Check that the read-back matches the request.
   **Never retry a failed/timeout write blindly** — run `workout.py day DATE` first; `createScheduledWorkout` has no
   duplicate protection.

6. **Report** in plain language:
   - the structure as saved, the COROS estimate (note: free sections are not counted in it),
   - other workouts on the same day (e.g. a TrainingPeaks plan session),
   - interval-group nuance: the recovery inside a group also runs after the last rep (offer `repeats: N-1` + a final
     work section if that matters),
   - "Sync the watch from the COROS app before you leave",
   - moving/deleting the workout requires the COROS app.
   Never show `idInPlan`, `labelId` or other internal IDs. Keep the returned `idInPlan` in your context (or in the
   plan YAML `coros.id_in_plan`) for later edits.

## Editing an existing workout on a date

1. `workout.py day DATE` → find the workout. If it comes from a **training plan** (Plan ID present) it must be
   changed with `updateTrainingPlan`; plans synced from TrainingPeaks are **read-only** → tell the user to change it in
   TrainingPeaks.
2. `workout.py show DATE ID` → copy the returned course JSON, change only what was asked, keep everything else
   (including free sections and sections without intensity), make sure the description is non-empty.
3. `workout.py update DATE ID course.json` (dry run) → confirm → `--yes`. Store the **new** `idInPlan` returned.
   Completed or past workouts cannot be edited.

## Library templates

"Save it as a reusable workout" → `scripts/coros.py call createSingleWorkout '{"course": {...}}'` (no date).
"Put my library workout X on Friday" → `queryWorkoutLibrary` then `scheduleWorkout` with `workoutId` + `date`
(the only way to schedule existing strength/swim workouts).

## Example

User: *"Create a session for today: free warm-up, 4×1000 at 4:05 with 2 min rest, free cool-down."*
→ `examples/intervals-4x1000-free-wu-cd.json` (this exact workout was created and verified live).
