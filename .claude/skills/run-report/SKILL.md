---
name: run-report
description: Draft a "current state of training" report from the athlete's COROS or Garmin data and their active training plan. Use when the user asks for a training report, a status / progress update, a recap of the plan so far, "where am I in my training?", "how is my plan going?", a weekly or monthly summary, or a report to share with a coach. Read-only - it never writes to COROS.
---

# COROS training report

Produce a clear, data-backed report on where the athlete stands: plan progress and adherence, key-session
quality, volume, training load, recovery/readiness, fitness vs goal, the next 7 days and a coach's assessment.
`scripts/report.py` computes every number; you add the interpretation. **Never invent or estimate numbers that are
not in the script output or in data you fetched.**

## Workflow

1. **Pick the scope**
   - Active plan: the most recent folder in `plans/` whose dates include today (or the one the user names).
   - No plan / user asks about "my training" in general: report without a plan.
   - History window: default 4 weeks; use 8–12 for a "block" or monthly report.

2. **Generate the draft** (read-only; it syncs the plan first so actuals are up to date):
   ```bash
   .venv/bin/python scripts/report.py plans/<slug> --weeks 4        # → plans/<slug>/reports/YYYY-MM-DD.md
   .venv/bin/python scripts/report.py --weeks 8                     # no plan → reports/YYYY-MM-DD.md
   ```
   If the COROS login / Garmin key is missing, follow *Setup* in `AGENTS.md`. With Garmin, the fitness numbers are
   estimates (the report says so) and the load ratio is computed from HR zones: present them as such.

3. **Dig where it matters** (optional, 1–3 extra calls max), e.g. for the last key sessions:
   `scripts/coros.py call queryActivityLapData '{"labelId": "...", "sportType": 100}'` to check rep paces vs target
   and fading; `getActivityDetail` for training effect; `querySleepHrv` raw curve if HRV is unusual.
   Lap units: distance in cm, pace in s/km (see `docs/mcp-reference.md`).

4. **Write the assessment** by replacing every `<!-- COACH: ... -->` placeholder in the generated file:
   - **Summary** (top): 3–5 sentences — where the athlete is, the main positive, the main concern, the focus for the
     coming days.
   - **Key sessions** comment: paces vs targets, HR response, consistency, compliance.
   - **Coach's assessment**: *What's going well* · *What to watch* · *Recommended adjustments* · *Questions for the
     athlete*. Base the recommendations on `.claude/skills/run-coach/references/decision-process.md` and name the
     rule (e.g. "load ratio 1.58 = Excessive → no added intensity this week"). Compare goal vs COROS prediction
     honestly.
   - Interpret, don't repeat the tables. Use the athlete's language for the prose (the template headings stay in
     English unless the athlete prefers otherwise).
   - Context to consider: unplanned activities (bouldering, padel, hikes) count as load; hikes are separated from
     runs; sleep/HRV dates are wake-up days; missing data lowers confidence.

5. **Deliver**
   - Show the athlete a short version in chat (summary + 3–5 bullets + the recommended adjustments) and the path of
     the full report.
   - Recommended plan changes are **proposals**: apply them to `plan.yaml` only if the athlete agrees, through the
     `run-coach` workflow (validate → render → journal → push after OK).
   - Persist: reports are git-ignored (personal health data). Commit `plans/<slug>/reports/` (or `reports/`) only
     under the conditions of *Persistence of personal data* in `AGENTS.md` (athlete agrees, repo is `PRIVATE`,
     `git add -f`, branch + PR, never `main`). If the athlete wants to share it, offer to export it (e.g. render to
     HTML) — share links only on explicit request, and remember the report contains personal health data.

## Rules

- Read-only: this skill never calls COROS write tools.
- Never show internal IDs (`labelId`, `idInPlan`, plan IDs) or raw JSON in the report or chat.
- If a section is empty because data is missing, say so in one line rather than guessing.
- Health caveat: you give training guidance, not medical advice; pain or illness → suggest a professional.
