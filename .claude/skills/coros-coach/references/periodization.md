# Periodisation recipe

How to lay out an N-week plan from the intake answers and `athlete/profile.yaml`.

## 1. Inputs

- Goal: race distance + date + target (or "general fitness"), or "build base".
- Weeks N (4–24), sessions per week K, time budget (minutes per day and/or per week), available days, sports.
- Baseline from `plan.py profile`: last 8 weeks avg/max run km, avg minutes, avg sessions, threshold pace,
  race predictions, load ratio.
- Other activities (bouldering, padel, hikes…) and constraints (injuries, travel).

## 2. Phase split

| N weeks | Base | Build | Peak | Taper |
|---|---|---|---|---|
| 4–5 | 1 | 2 | 1 | 0–1 (short taper week if race) |
| 6–8 | 2 | 3 | 1–2 | 1 |
| 9–12 | 3–4 | 4 | 2 | 1–2 |
| 13–16 | 4–5 | 5–6 | 2–3 | 2–3 (marathon 3) |
| > 16 | 5+ | 6+ | 3 | 3 |

Without a race: base → build → recovery cycles (3:1), no taper. If the athlete is already fit (load ratio ≥ 0.8,
recent quality work), base can be shortened.

## 3. Volume curve

- Week 1 = recent average (from profile), **not** the peak; never above the recent max.
- +5–10 %/week, recovery week every 3rd or 4th week at −20–30 %; after it resume from the pre-recovery level.
- Peak volume ≈ 1.2–1.4 × starting volume for an 8–12 week plan (less for short plans).
- Cap by the time budget: weekly planned minutes ≤ `weekly_minutes`.
- Taper: −20–30 % (week −2/−3), −40–60 % (race week); keep frequency and a short quality session.

## 4. Weekly template (K sessions)

| K | Template (Mon→Sun, adapt to availability) |
|---|---|
| 3 | Q1 · easy · long |
| 4 | easy · Q1 · easy · long |
| 5 | easy · Q1 · easy+strides · Q2 · long |
| 6 | easy · Q1 · easy · Q2 · easy · long |
| 7 | easy · Q1 · easy · medium-long · Q2 · recovery · long |

Rest or cross-training on the remaining days. Long run usually on the weekend day with most time. Never place a
quality session the day after the long run or after a hard cross-training day.

## 5. Session durations

- Long run: 20–30 % of weekly minutes, ≤ 150′ (≤ 180′ marathon/trail with base).
- Quality sessions: 45–75′ including WU/CD.
- Easy runs fill the remaining budget (30–60′ each).
- Intensity check: time above threshold (T/I/R portions only, not WU/CD) ≤ 15–20 % of weekly time.

## 6. Writing sessions into plan.yaml

For each session: `id` (`w<week>-<weekday>` e.g. `w3-tue`, unique), `date`, `sport`, `type`, `key` (long + quality),
`title` (athlete-facing), `planned.duration_min`, optional `planned.distance_km`, `planned.target`
(e.g. "4:37–5:10/km"), `planned.description`, and `course` (COROS JSON — required to push). Build course JSON with
absolute pace ranges from `plan.py zones`, following `docs/course-json.md` and the examples of the
`coros-workout` skill.

To keep `plan.yaml` readable, you may write the `course` only for the next 2 weeks and fill later weeks just before
pushing (validate warns, it does not fail).
