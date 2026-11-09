# plan.yaml schema

`plans/<slug>/plan.yaml` is the single source of truth. `plan.md` is generated (`plan.py render`) and
`journal.md` is an append-only log. Create a skeleton with
`plan.py init <slug> --title ... --start YYYY-MM-DD --weeks N [--goal-distance half --goal-date ... --sessions-per-week K --weekly-minutes M]`.
Start dates should be Mondays (weeks are 7-day blocks from `start`).

```yaml
plan:
  id: 2026-12-half                 # = folder name
  title: Autumn Half — sub 1:22
  start: '2026-10-05'              # Monday
  weeks: 9
  goal: {distance: half, date: '2026-12-06', target_time: '1:22:00'}
  sessions_per_week: 5
  weekly_minutes: 360              # time budget (optional)
  summary: |                       # 3–5 lines: approach, key ideas, constraints
    Base 3 wk → build 3 wk → peak 2 wk → taper 1 wk. Bouldering Tue/Thu kept, no hard run the day after.
  last_sync: '2026-10-12 08:30'    # set by plan.py sync
readiness: {...}                   # set by plan.py sync (latest snapshot)
weeks:
- n: 1
  phase: base                      # base | build | peak | taper | recovery
  focus: Rebuild volume, strides
  recovery: false                  # true for down weeks (relaxes progression warnings)
  review: ''                       # coach's end-of-week summary (shown in plan.md)
  sessions:
  - id: w1-tue                     # stable, unique; never rename once pushed
    date: '2026-10-06'
    sport: run                     # run | trail | bike | swim | strength | other | rest
    type: intervals                # easy recovery long medium_long strides fartlek progression tempo threshold
                                   # intervals repetition hills race_pace race cross strength rest
    key: true
    title: 5 x 1000 m at I pace
    planned:
      duration_min: 55
      distance_km: 11
      target: 3:39–3:46/km
      description: 15′ easy + 4 strides, 5 × 1000 m at 3:39–3:46/km with 2′30 jog, 10′ easy.
    course: {courseName: ..., courseDescription: ..., sportType: 1, sections: [...]}   # COROS JSON
    status: planned                # planned | pushed | adjusted | done | partial | missed | skipped
    coros: {id_in_plan: '11', pushed_at: '2026-10-05 20:00'}   # set by plan.py push — internal, never show
    actual:                        # set by plan.py sync
      label_id: '…'                # internal, never show
      matched_date: '2026-10-06'
      duration_min: 54.2
      distance_km: 11.1
      avg_pace: '4:52'
      avg_hr: 151
      compliance_pct: 99           # actual / planned duration
      training_load: 98            # with --details (key sessions)
      aerobic_te: 3.1
      anaerobic_te: 2.4
    feedback: ''                   # athlete's words (RPE, pain, feelings) — fill from conversation
    notes: ''                      # coach's notes, e.g. why it was adjusted
  unplanned:                       # activities not matching a session (set by sync)
  - {date: '2026-10-07', sport: Bouldering, duration_min: 95}
```

## Status lifecycle

```
planned ──push──▶ pushed ──sync──▶ done | partial | missed
   │                 │
   └─edit─▶ planned  └─edit─▶ adjusted ──push──▶ pushed (updateScheduledWorkout)
skipped: set by the coach when a session is intentionally dropped (with a note)
```

- `sync` marks a past open session `missed` if no compatible activity exists on its date (±1 day).
- `partial`: compliance < 80 %.
- Edit freely sessions in `planned`. For `pushed` sessions, edit then set `adjusted`.
- A pushed session that must disappear: the MCP cannot delete. Either turn it into the replacement session
  (`adjusted`) or ask the athlete to delete it in the COROS app, then set `skipped`.

## Journal entry format (`journal.md`, append at the bottom)

```markdown
## 2026-10-12 — week 1 review
- Readiness: 🟡 yellow (HRV 49 < 56–80; sleep 6.8 h) · load ratio 0.92
- Done 4/5 (missed Thu easy run). Intervals: 5×1000 avg 3:43, HR 172 last rep — on target.
- Changes: w2-tue intervals → 4 × 1000 (yellow readiness); w2-sat long run 80′ → 75′.
- Why: decision-process "yellow + quality"; volume +12 % would exceed guideline.
- Next: push w2 (Mon–Sun) after athlete OK.
```
