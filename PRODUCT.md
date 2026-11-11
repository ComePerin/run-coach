# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
One self-coached endurance athlete (runner, trail, cyclist) using their own COROS or Garmin watch data through an AI
coach. Main reading scene for the session recap: on a phone, right after the run — sweaty, outdoors or in the car,
glancing rather than studying.

## Product Purpose
coros-coach turns an AI agent into an adaptive running / trail / cycling coach: it reads watch data (COROS MCP or
Garmin Personal API), creates structured workouts for the watch, builds a training plan and adapts it to what the
athlete actually ran. Success: the athlete knows how the session went and what changes next, without opening the
watch app.

## Positioning
The coach compares what was planned (its own structured workout, step by step) with what was run, and links the gap to
readiness (HRV, sleep, RHR) and the athlete's own words — then proposes plan changes that only apply on explicit OK.

## Operating Context
Claude Code or Claude chat. Outputs are generated markdown reports and local HTML pages built from deterministic Python
scripts (`scripts/plan.py`, `scripts/report.py`, `scripts/readiness.py`). Plans live in `plans/<slug>/`.

## Capabilities and Constraints
- Read-only on watch data; writes to the calendar or FIT exports always need the athlete's explicit OK (dry run first).
- Garmin values for load ratio and threshold are computed substitutes (TRIMP, Riegel) and should be marked as estimates.
- Session recap data shape: planned steps with target bands, laps, HR per rep, zones intended vs actual, RPE + free-text
  feel, readiness context, plan-impact proposals.

## Brand Commitments
- Coach voice speaks the athlete's language (French in current use); UI labels may stay in English.
- Unofficial project, not affiliated with COROS or Garmin: never use their branding.
- Training guidance, not medical advice.

## Evidence on Hand
Only mock data so far for the session recap. No real athlete data may be published.

## Product Principles
1. Verdict first: how it went and what changes next, before the detail.
2. Planned vs done is the core comparison; every view serves it.
3. Proposals, never silent changes.
4. Honest numbers: mark estimates, never invent precision.

## Accessibility & Inclusion
Readable in sunlight on a phone after effort: large key figures, high contrast, large tap targets.
