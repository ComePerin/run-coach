# coros-coach

Turn an AI agent into a running / trail / cycling coach that works from your **COROS** or **Garmin** watch data.
It reads everything through the official [COROS MCP](https://github.com/coroslab/COROS-MCP) or Garmin's official
[Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api), creates structured workouts
for your watch from one sentence, builds a training plan and adapts it to what you actually ran.

> **Garmin users**: everything works. Garmin's API is read-only, so planned workouts reach your Garmin Connect
> calendar through a free [intervals.icu](https://intervals.icu) account (or as `.fit` files you copy to the watch).
> Jump to [Use it with Garmin](#use-it-with-garmin).

```
"Create a session for today: free warm-up, 4×1000 at 4:05 with 2' rest, free cool-down"
"Build me a 10-week half-marathon plan, 5 sessions a week, max 6 h, race on 6 December"
"How did my week go? Adjust the plan."
"What should I do today?"
"Write me a report on where I am in my training plan"
```

> Unofficial project, not affiliated with COROS or Garmin. Training guidance, not medical advice.

## Features

The agent lists them at the start of every conversation (type `menu` to see them again).

| | Feature | Ask for example | Skill |
|---|---|---|---|
| 📊 | **Analyse** activities, laps, sleep, HRV, resting HR, training load | "How was my sleep this month?" | — |
| ⌚ | **Create a workout on the watch** (run, bike, trail), validated and read back | "Add a 45-minute easy ride tomorrow" | `coros-workout` |
| 🗓️ | **Build a training plan** from your COROS baseline, goal and time budget | "8-week 10K plan, 4 sessions a week" | `coros-coach` |
| 🔄 | **Review and adapt** the plan: planned vs done, missed sessions, fatigue | "Update my plan" | `coros-coach` |
| 🚦 | **What should I do today?** readiness from HRV, resting HR, sleep, recovery, load | "Should I do my intervals today?" | `coros-coach` |
| 📝 | **Training report**: progress, adherence, key sessions, load, fitness vs goal | "Give me a report on my last 4 weeks" | `coros-report` |

Writes to your COROS calendar (or FIT exports for Garmin) always need your explicit OK: the agent shows a dry run
first.

## Two ways to use it

| | Claude Code (recommended) | Claude chat (claude.ai, Claude desktop) |
|---|---|---|
| Setup | clone this repo, one login link | add a connector + a project, no install |
| COROS access | helper script (works in headless containers) | COROS connector |
| Plan engine (validation, guardrails, matching, readiness score) | deterministic Python scripts | Claude applies the same rules from the docs |
| Plan storage | `plans/<slug>/plan.yaml` + generated `plan.md` + journal | a `plan.md` you add to the project knowledge |
| Reports | generated markdown files | in the conversation |

---

## Use it with Claude Code

### 1. Get your own copy

Click **Use this template** on GitHub and create a **private** repository (recommended: your plans and reports
contain health data, see [Your data](#your-data)), then clone it. Or simply:

```bash
git clone https://github.com/Z3ZEL/coros-coach && cd coros-coach
```

### 2. Connect your COROS account

```bash
scripts/setup.sh                                   # fetches the official helper, creates .venv, prints a login link
.venv/bin/python scripts/coros.py login-finish     # after you signed in in the browser
.venv/bin/python scripts/coros.py status           # → "COROS MCP OK — logged in as …"
.venv/bin/python scripts/plan.py profile           # your baseline → athlete/profile.yaml
```

You can also skip this and just tell the agent *"set me up"*: it runs the setup and gives you the link. You never
give your COROS password to the agent; the login tokens are stored outside the repo
(`~/.coros-mcp-skill-gateway/`) and refresh themselves.

### 3. Talk to it

```bash
claude            # in the repo folder
```

Claude Code loads `CLAUDE.md` (which imports `AGENTS.md`) and the three skills in `.claude/skills/` automatically. Say *"hi"*: the agent
answers with the feature menu and the state of your setup (COROS connected? active plan?), then you ask in plain
language. Example of a first exchange:

```
> salut
Voici ce que je peux faire avec tes données COROS :
1. 📊 Analyser — activités, tours, sommeil, VFC, FC repos, charge
2. ⌚ Créer une séance sur ta montre
…
COROS : connecté · Plan actif : aucun
Qu'est-ce que tu veux faire ?
```

**Claude Code on the web** ([claude.ai/code](https://claude.ai/code)) works too: start a session on your copy of
the repo and say *"set me up"*. The container is ephemeral, so you will log in to COROS again when it is recycled;
its network access must allow `github.com` and the `*.coros.com` MCP hosts (`mcp.coros.com` and your region's
`mcpeu` / `mcpus` / `mcpcn`).

**Optional — native COROS connector in Claude Code**: `claude mcp add --transport http coros https://mcp.coros.com/mcp`
then `/mcp` to sign in. The agent can then call the COROS tools directly; the plan scripts still use the helper
login from step 2.

### Other agents

Codex and other agents read `AGENTS.md`. Without native skill support, they follow the relevant `SKILL.md` as
instructions.

---

## Use it in Claude chat

No install, but no scripts either: Claude calls the COROS tools itself and follows the same coaching rules from the
documentation. It relies on [custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
(claude.ai and Claude desktop).

1. **Add the COROS connector** — *Customize → Connectors → + Add → Add custom connector*, name `COROS`, URL
   `https://mcp.coros.com/mcp`, keep the detected OAuth sign-in, **Add**, and sign in with your COROS account.
   (Team / Enterprise: an owner adds it under *Organization settings → Connectors → Add → Custom → Web*, then
   each member clicks **Connect** in *Customize → Connectors*.)
2. **Create a project**, e.g. *COROS coach*.
3. **Instructions** — paste the content of [`claude-chat/project-instructions.md`](claude-chat/project-instructions.md)
   into the project's instructions.
4. **Knowledge** — upload these files to the project (or run `scripts/chat-bundle.sh` to collect them in
   `dist/claude-chat/`):
   `docs/mcp-reference.md`, `docs/garmin-reference.md` (Garmin users), `docs/course-json.md`, `docs/coaching-science.md`,
   `.claude/skills/coros-coach/references/{decision-process,periodization,session-library}.md`,
   `scripts/readiness.py` (readiness rules) and the workout examples in `.claude/skills/coros-workout/examples/`.
5. **Start a chat in the project**, make sure the COROS connector is enabled (**+** → *Connectors*) and say *"hi"*:
   Claude lists the features and checks the connection.

When Claude builds or updates a plan it gives you a `plan.md`: add it to the project knowledge (replace the old
one) so that the next conversations start from your current plan.

---

## Use it with Garmin

Same agent, same plans and reports; data comes from Garmin's official **Personal API** (read-only, Python ≥ 3.12).

| Feature | Garmin |
|---|---|
| 📊 Analyse activities, sleep, HRV, resting HR | ✅ |
| 🗓️ Build a plan · 🔄 review and adapt · 📝 report | ✅ |
| 🚦 What should I do today? | ✅ HRV, resting HR, sleep, **Body Battery** (instead of COROS recovery), **load ratio computed** from HR zones |
| Threshold pace, race predictions | ⚠️ **estimated** from your best recent efforts (no VO2max) |
| ⌚ Workout on the watch | ✅ via **intervals.icu** → Garmin Connect calendar (website, app, watch), next ~7 days · or ⚠️ `.fit` files copied over USB |

### Setup

1. **Create a Personal API key** in Garmin Connect: <https://connect.garmin.com/app/settings/personalApiToken>.
2. **Install and store the key** (the key is saved in `~/.config/garmin/`, outside the repo, readable only by you):
   ```bash
   git clone https://github.com/Z3ZEL/coros-coach && cd coros-coach
   scripts/setup.sh --garmin            # creates .venv, asks for the key (hidden input), checks it
   .venv/bin/python scripts/plan.py profile   # your baseline → athlete/profile.yaml (records provider: garmin)
   ```
3. **Workouts into Garmin Connect (recommended)**: create a free [intervals.icu](https://intervals.icu) account,
   then in its settings link Garmin and tick **"Upload planned workouts"**, set your Run **threshold pace** (needed
   for pace targets), and copy your API key (*Developer Settings*):
   ```bash
   scripts/setup.sh --intervals         # asks for the intervals.icu API key (hidden input), checks it
   ```
4. **Talk to it**: `claude` in the repo folder, then *"hi"*.

The provider is picked from `COACH_PROVIDER=garmin|coros`, else `provider:` in `athlete/profile.yaml`, else
auto-detected (COROS helper installed → COROS, Garmin key found → Garmin).

### Getting workouts on the watch

Garmin's API cannot write and Garmin Connect cannot import workout files (its *Import Data* page only takes
activities). Two ways around it:

```bash
# 1. intervals.icu (with an API key set up): dated workouts in the Garmin Connect calendar, app and watch
.venv/bin/python scripts/plan.py push plans/<slug> --days 7 --yes
# 2. files: exports/<date>-<name>.fit, to copy into GARMIN/NewFiles/ on the watch over USB
.venv/bin/python scripts/plan.py push plans/<slug> --days 7 --yes --files
```

intervals.icu uploads the next ~7 days of planned workouts to Garmin Connect; changed sessions are updated in place.
With files, the workouts appear under *Training → Workouts* on the watch, undated.
Each file is checked with Garmin's official FIT SDK before it is written (`scripts/fitworkout.py check FILE.fit`). Climb targets,
% effort and pace zones are COROS-only: the agent uses absolute paces, HR or power for Garmin.

Details, endpoints, limits and what is estimated: [`docs/garmin-reference.md`](docs/garmin-reference.md).

---

## How it works

```
             ┌──────────── COROS MCP (official, OAuth) ────────────┐
             │ activities · laps · FIT · sleep · HRV · RHR · load   │
             │ VO2max · threshold · calendar (create/update)        │
             └──────────────▲───────────────────────┬──────────────┘
                            │ scripts/coros.py       │
   ┌────────────────────────┴──────┐      ┌─────────▼──────────────────────────┐
   │ coros-workout skill           │      │ coros-coach skill                   │
   │ text → course JSON → validate │      │ profile → plan.yaml → validate      │
   │ → create → read back          │      │ → push 7 days → sync actuals        │
   └───────────────────────────────┘      │ → readiness → adapt → journal       │
                                          └─────────────────────────────────────┘
```

- **Scripts compute, the agent decides.** Matching activities to sessions, readiness scoring (HRV, resting HR, sleep,
  recovery, load ratio), pace zones and guardrails (volume progression, 80/20, long-run caps, hard days back-to-back)
  are deterministic Python. The agent applies explicit decision tables and explains its changes.
- **`plan.yaml` is the source of truth**, `plan.md` is a generated readable view (✅ ⚠️ ❌ planned vs actual,
  readiness, weekly totals), `journal.md` keeps the history of decisions.
- **Rolling push**: only the next ~7 days go to the watch, because the MCP cannot delete or move workouts.

## Your data

This repository is meant to be shared, your training data is not:

- `athlete/profile.yaml`, `plans/*/`, `reports/`, `exports/`, `.cache/` (raw COROS / Garmin responses) and FIT files are
  **git-ignored**. They stay on your machine. `athlete/profile.example.yaml` shows what a profile looks like.
- To keep them in git (e.g. with Claude Code on the web, whose containers are ephemeral), use a **private** copy of
  the repo and add them with `git add -f`. The agent only does it if you ask and after checking that the repo is
  private (`gh repo view --json visibility`).
- COROS login tokens live in `~/.coros-mcp-skill-gateway/`, outside the repo. FIT download URLs work without
  authentication: never paste them anywhere public.
- The intervals.icu API key lives in `~/.config/intervals/api-key` (or `$INTERVALS_API_KEY`). Workouts sent there
  are stored on intervals.icu (its [privacy policy](https://intervals.icu/privacy-policy.html) applies).
- The Garmin Personal API key lives in `~/.config/garmin/connect-personal-api-key` (or `$GARMIN_PERSONAL_API_KEY`),
  outside the repo. Anyone with it can read your Garmin data: revoke it in Garmin Connect if it leaks.
- The test fixtures in `tests/fixtures/` are synthetic: real COROS / Garmin output format, made-up values.

## CLI cheatsheet

```bash
# raw MCP
.venv/bin/python scripts/coros.py tools
.venv/bin/python scripts/coros.py call queryFitnessAssessmentOverview

# raw Garmin Personal API (read-only)
.venv/bin/python scripts/garmin.py status
.venv/bin/python scripts/garmin.py call search_activities '{"start_date": "2026-10-01", "end_date": "2026-10-31"}'

# one workout
.venv/bin/python scripts/workout.py create 2026-10-03 course.json        # COROS, dry run
.venv/bin/python scripts/workout.py create 2026-10-03 course.json --yes
.venv/bin/python scripts/workout.py send 2026-10-03 course.json --yes    # Garmin → intervals.icu → Garmin Connect
.venv/bin/python scripts/workout.py export 2026-10-03 course.json --yes  # Garmin → exports/*.fit

# plan
.venv/bin/python scripts/plan.py init 2026-12-half --title "Half sub 1:22" --start 2026-10-05 --weeks 9 \
    --goal-distance half --goal-date 2026-12-06 --sessions-per-week 5 --weekly-minutes 360
.venv/bin/python scripts/plan.py validate plans/2026-12-half
.venv/bin/python scripts/plan.py push plans/2026-12-half --days 7 [--yes]
.venv/bin/python scripts/plan.py sync plans/2026-12-half --details
.venv/bin/python scripts/plan.py readiness
.venv/bin/python scripts/plan.py zones

# report (read-only)
.venv/bin/python scripts/report.py plans/2026-12-half --weeks 4   # → plans/2026-12-half/reports/<date>.md
.venv/bin/python scripts/report.py --weeks 8                       # no plan → reports/<date>.md
```

## Repository layout

| Path | |
|---|---|
| `CLAUDE.md` | loads `AGENTS.md` for Claude Code |
| `AGENTS.md` | agent guide: session start menu, setup, MCP essentials, rules, data persistence |
| `.claude/skills/coros-workout/` | workout builder skill + validated examples |
| `.claude/skills/coros-coach/` | coach skill + references (decision process, session library, periodisation, plan schema) |
| `.claude/skills/coros-report/` | training-status report skill (read-only) |
| `claude-chat/` | project instructions for Claude chat |
| `docs/mcp-reference.md` | the 34 COROS MCP tools, formats, units, limits, quirks, sport codes |
| `docs/garmin-reference.md` | Garmin Personal API: endpoints used, computed substitutes, intervals.icu delivery, FIT export, limits |
| `docs/course-json.md` | workout JSON cheat sheet |
| `docs/coaching-science.md` | training rules and their sources |
| `scripts/` | `source.py` (provider switch), `coros.py` + `parsers.py` (COROS), `garmin.py` + `garmin_parsers.py` (Garmin), `fitworkout.py` (FIT export + checks), `intervals.py` (workouts → Garmin Connect via intervals.icu), `workout.py`, `plan.py`, `readiness.py`, `report.py`, `setup.sh`, `chat-bundle.sh` |
| `athlete/` | your `profile.yaml` (git-ignored) and an example |
| `plans/` | one folder per plan (git-ignored) |
| `tests/` | pytest on synthetic COROS and Garmin outputs |

## Development

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
```

CI (`.github/workflows/ci.yml`) runs both on Python 3.10 and 3.12 for every pull request. The tests generate every
exportable example workout as FIT, decode it with Garmin's official FIT SDK, validate it with fit-tool and compare it
step by step with its course JSON.

Issues and pull requests are welcome. Never include personal data (yours or anyone's) in fixtures, examples,
issues or PRs.

## Notes

- Built on the official [COROS MCP](https://github.com/coroslab/COROS-MCP); the helper script is downloaded at
  setup, not redistributed.
- Garmin data through Garmin's official [Personal API client](https://github.com/garmin/connect-personal-api-python)
  (Apache-2.0); FIT workouts written with [fit-tool](https://pypi.org/project/fit-tool/) (BSD-3-Clause).
- The coach gives training guidance, not medical advice. Pain or illness: see a professional.
