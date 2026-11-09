# Coaching science — condensed, with sources

The rules the coach applies, and why. Numbers here are encoded in `scripts/readiness.py`, `scripts/plan.py validate`
and the coach skill references. Evidence quality varies: treat each as a guideline and say so when it matters.

## 1. Intensity zones (relative to COROS threshold pace)

COROS gives a **threshold pace** (`queryFitnessAssessmentOverview`, ≈ lactate threshold / critical speed). Zones used
here approximate Jack Daniels' VDOT relationships ([Daniels' Running Formula](https://www.coachray.nz/2023/05/03/jack-daniels-running-intensity/)):

| Zone | Factor × threshold pace (s/km) | Daniels | Use | Weekly cap |
|---|---|---|---|---|
| Recovery | 1.32–1.45 | — | day after hard sessions | — |
| Easy (E) | 1.18–1.32 | 59–74 % VO2max, 65–79 % HRmax | most volume, long runs | ≥ 80 % of time |
| Marathon (M) | 1.05–1.08 | 75–84 % VO2max | marathon-specific | ≤ 15–20 % |
| Threshold (T) | 0.98–1.02 | 83–88 % VO2max | tempo, cruise intervals | ≤ 10 % of weekly volume |
| Interval (I) | 0.93–0.96 | 95–100 % VO2max | 3–5′ reps, VO2max | ≤ 8 % (and ≤ 10 km/session) |
| Repetition (R) | 0.86–0.90 | > VO2max | 200–400 m, economy | ≤ 5 % (and ≤ 8 km/session) |

`plan.py zones` prints these for the athlete. COROS' own six pace zones (Recovery, Aerobic Endurance, Aerobic Power,
Threshold ±2–5 %, Anaerobic Endurance 3–8′, Anaerobic Power < 3′) can also be targeted with `sectionIntensity` 1–6
([COROS pace zones](https://coros.com/stories/coros-metrics/c/evolab-updated-pace-zones)).

## 2. Intensity distribution — 80/20

Elite endurance athletes do ~80 % of sessions below the first lactate threshold and ~15–20 % above the second,
with little in between ([Seiler 2010](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4621419/)). Rule: **at most
2 quality sessions per week (3 for ≥ 6 sessions/week)**, never on consecutive days, plus one long run.

## 3. Periodisation (Pfitzinger / Daniels)

| Phase | Share of plan | Content |
|---|---|---|
| Base | 30–40 % | volume build, strides, hills, 1 light quality session (fartlek / tempo) |
| Build | 30–40 % | threshold + VO2max work, long run grows, medium-long run (marathon) |
| Peak / specific | 15–20 % | race-pace work, volume stable or slightly down, intensity kept |
| Taper | 1–3 weeks | volume −41–60 % (exponential), **keep intensity and frequency** ([Bosquet 2007](https://pubmed.ncbi.nlm.nih.gov/17762369/)) |

Taper length: 5K/10K 7–10 days · half 10–14 days · marathon ~3 weeks. Post-race: easy/rest ~1 day per 3–5 km raced.

## 4. Progression and recovery weeks

- Volume / COROS training load: **+5–10 % per week**; COROS recommends ~+10 % and a 3:1 build:recovery cycle
  ([COROS Training Load](https://coros.com/ca/stories/coros-metrics/c/training-load)).
- The "10 % rule" itself has weak evidence (10 % vs 24 % gave similar injury rates, [Buist 2008](https://bjsm.bmj.com/content/43/2/155)),
  but **> 30 % over 2 weeks** raised distance-related injuries ([Nielsen 2014](https://vbn.aau.dk/da/publications/excessive-progression-in-weekly-running-distance-and-risk-of-runn)) → hard stop.
- **Recovery week every 3rd–4th week**: volume −20–30 %, keep one short quality session.
- Long run ≤ min(25–30 % of weekly volume, 150 min); up to ~3 h for marathon/trail athletes with the base for it.

## 5. Load monitoring

- COROS **Load Ratio** = short-term (7-day) / long-term (42-day) load
  ([Intensity Trend](https://support.coros.com/hc/en-us/articles/26485283220884)):
  ≥ 1.5 *Excessive* · 1.0–1.49 *Optimized* (build) · 0.8–0.99 *Maintaining* · 0.5–0.79 *Performance* (race week).
- ACWR "sweet spot" 0.8–1.3 / danger > 1.5 ([Gabbett 2016](https://simplifaster.com/articles/train-more-without-injuries/))
  is **context, not an injury predictor** ([Impellizzeri 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC8138569/)).

## 6. Readiness signals

- **HRV-guided training** (Kiviniemi 2007; Plews & Buchheit): train hard when HRV is within the normal range,
  go easy when it drops below. One low night → keep plan / trim; 2–3 nights → swap quality for easy; ≥ 4 → recovery
  days. Persistently *high* HRV can mean saturation or illness — flag, don't reward
  ([guide](https://www.athletedata.health/guides/hrv-guided-training), [HRV4Training](https://www.hrv4training.com/blog2/redefining-hrv4trainings-daily-advice)).
- **Resting HR** > +5 bpm vs 7-day mean → negative signal; rising trend → illness/overreaching/travel.
- **Sleep** < 6 h strong negative, < 7 h mild negative.
- **COROS recovery %**: 0–19 exhausted, 20–69 fatigued, 70–89 normal, 90–100 fresh.
- **Missing data lowers confidence; it is never a bad signal.** When signals conflict, lean towards caution.

## 7. Session quality checks

- **Aerobic decoupling** (pace:HR drift first vs second half of a steady run, from FIT data): < 5 % good aerobic
  endurance, 5–10 % limited, > 10 % too hard or lacking endurance
  ([TrainingPeaks](https://www.trainingpeaks.com/learn/articles/aerobic-endurance-and-decoupling/)).
- Interval compliance: rep paces within ±2 % of target and consistent (last rep not > 3 % slower).
- Easy runs drifting into zone 3 (HR > ~85 % LTHR) repeatedly → remind and lower the target.

## 8. Missed sessions

Never stack a missed session onto another day. Move a missed key session only if ≥ 48 h separate it from the next
hard day; otherwise drop it. The long run has priority over secondary quality. After ≥ 2 missed weeks, repeat the
previous week before progressing.

## Sources of the agent design

Patterns borrowed from open-source coaching agents: markdown memory + weekly logs
([BorisBW/claude-fitness-cn](https://github.com/BorisBW/claude-fitness-cn)), decision priority order and readiness
table ([rbrands/intervals-icu-sync](https://github.com/rbrands/intervals-icu-sync)), "code computes, LLM decides"
and explicit state→action tables ([David-Eques/running-coach](https://github.com/David-Eques/running-coach)),
COROS library vs scheduled-copy taxonomy ([dholliday3/coros-training-mcp](https://github.com/dholliday3/coros-training-mcp)).
