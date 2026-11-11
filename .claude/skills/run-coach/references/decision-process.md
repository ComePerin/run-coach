# Decision process — how the coach decides

"Code computes, coach decides and explains." Always run the scripts first (`plan.py sync`, `plan.py readiness`)
and decide from their output with the tables below. Do not invent thresholds; if you deviate, say why in the journal.

## Priority order (highest wins when rules conflict)

1. **Safety**: pain/injury/illness reported by the athlete, red readiness, load ratio ≥ 1.5.
2. **The goal race date and taper** (never move the race, protect the taper).
3. **Key sessions already planned** for the week (long run > main quality > secondary quality).
4. **Weekly structure** (hard/easy alternation, ≥ 48 h between hard sessions, rest day).
5. **Progression** (volume +5–10 %, recovery week every 3–4 weeks).
6. Athlete preferences (days, other sports, time budget).

## Readiness → today's action

`plan.py readiness` / `plan.py sync` give `level` (green/yellow/red), `score` and per-signal details.

| Readiness | Today's planned session is… | Action |
|---|---|---|
| 🟢 green | anything | Do as planned. |
| 🟡 yellow | easy / long | Do it; long run may be capped at the planned duration (no extension). |
| 🟡 yellow | quality (tempo/intervals/hills) | Keep it if only one mild signal and athlete feels good; otherwise reduce volume by ~25 % (fewer reps) and keep the pace, **or** swap with the next easy day if ≥ 48 h to the following hard day. |
| 🔴 red | anything hard | Replace by easy 30–45′ (recovery zone) or rest. Move the key session only if the 48 h rule allows, otherwise drop it. |
| 🔴 red 2+ days | — | Recovery days until signals return to green/yellow; consider illness; reduce the week's volume 20–30 %. |
| HRV **above** range for 3+ days | — | Flag (possible saturation/illness). Do not increase load because of it. |

Missing data lowers `confidence`; with confidence < 0.6, ask the athlete how they feel (RPE, legs, sleep) and weigh it.

## Load ratio (COROS short/long-term) → week adjustment

| Ratio | COROS label | During base/build | During taper/race week |
|---|---|---|---|
| ≥ 1.5 | Excessive | Cut next 3–4 days to easy; remove one quality session this week. | Cut further. |
| 1.3–1.49 | Optimized (high) | Hold volume, no further increase next week. | Too high — reduce. |
| 1.0–1.29 | Optimized | Normal progression. | Too high — reduce. |
| 0.8–0.99 | Maintaining | Fine for recovery weeks; otherwise progress next week. | OK early taper. |
| 0.5–0.79 | Performance | Too low for build unless recovery week/after illness: rebuild gradually (≤ +10 %/wk). | **Target for race week.** |

## Week review → next weeks

| Observation (from `plan.yaml` actuals) | Action |
|---|---|
| ≥ 90 % sessions done, compliance 90–110 %, readiness green/yellow | Progress as planned. |
| Quality reps consistently faster than target (≥ 2 %) with stable HR, and readiness good | Paces may be stale: refresh `plan.py profile` (threshold pace); update future targets. |
| Reps slower than target, HR high, or last reps fade > 3 % | Keep paces, reduce reps 1–2 next time, check sleep/load. |
| Easy runs above easy pace/HR zone repeatedly | Remind; widen recovery; lower easy targets in descriptions. |
| 1 key session missed | Do not stack. Move only if 48 h rule allows; else drop. |
| 2+ sessions missed in a week | Repeat the week's structure next week instead of progressing. |
| ≥ 2 weeks largely missed (illness/travel) | Step back 1–2 weeks of volume; shift phases; protect taper; tell the athlete if the goal time is now unrealistic. |
| Many unplanned activities (bouldering, padel, hikes) | Count them as load (COROS load includes them). Avoid hard running the day after hard cross-training. |
| Pain/injury reported | Stop running intensity, suggest seeing a professional, replace with cross-training if pain-free. Never coach through pain. |

## Writing changes

1. Edit the affected sessions in `plan.yaml` (keep `id`; set `status: adjusted` if the session was already pushed —
   `push` will update it on COROS; `planned` if not yet pushed). Add a short `notes:` explaining the change.
2. `plan.py validate` → must have 0 errors; read the warnings.
3. `plan.py render`.
4. Append a journal entry (see SKILL.md) with: date, readiness, what changed, why (cite the rule).
5. Ask before `plan.py push --yes`.
