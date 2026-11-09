# coros-coach

Turn an AI agent into a running / trail / cycling coach that works from your **COROS** watch data.
It reads everything through the official [COROS MCP](https://github.com/coroslab/COROS-MCP), creates structured
workouts on your watch from one sentence, builds a training plan and adapts it to what you actually ran.

```
"Create a session for today: free warm-up, 4×1000 at 4:05 with 2' rest, free cool-down"
"Build me a 10-week half-marathon plan, 5 sessions a week, max 6 h, race on 6 December"
"How did my week go? Adjust the plan."
"What should I do today?"
"Write me a report on where I am in my training plan"
```

> Unofficial project, not affiliated with COROS. Training guidance, not medical advice.

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

Writes to your COROS calendar always need your explicit OK: the agent shows a dry run first.

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
   `docs/mcp-reference.md`, `docs/course-json.md`, `docs/coaching-science.md`,
   `.claude/skills/coros-coach/references/{decision-process,periodization,session-library}.md`,
   `scripts/readiness.py` (readiness rules) and the workout examples in `.claude/skills/coros-workout/examples/`.
5. **Start a chat in the project**, make sure the COROS connector is enabled (**+** → *Connectors*) and say *"hi"*:
   Claude lists the features and checks the connection.

When Claude builds or updates a plan it gives you a `plan.md`: add it to the project knowledge (replace the old
one) so that the next conversations start from your current plan.

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

- `athlete/profile.yaml`, `plans/*/`, `reports/`, `.cache/` (raw COROS responses) and FIT files are
  **git-ignored**. They stay on your machine. `athlete/profile.example.yaml` shows what a profile looks like.
- To keep them in git (e.g. with Claude Code on the web, whose containers are ephemeral), use a **private** copy of
  the repo and add them with `git add -f`. The agent only does it if you ask and after checking that the repo is
  private (`gh repo view --json visibility`).
- COROS login tokens live in `~/.coros-mcp-skill-gateway/`, outside the repo. FIT download URLs work without
  authentication: never paste them anywhere public.
- The test fixtures in `tests/fixtures/` are synthetic: real COROS output format, made-up values.

## CLI cheatsheet

```bash
# raw MCP
.venv/bin/python scripts/coros.py tools
.venv/bin/python scripts/coros.py call queryFitnessAssessmentOverview

# one workout
.venv/bin/python scripts/workout.py create 2026-10-03 course.json        # dry run
.venv/bin/python scripts/workout.py create 2026-10-03 course.json --yes

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
| `docs/course-json.md` | workout JSON cheat sheet |
| `docs/coaching-science.md` | training rules and their sources |
| `scripts/` | `coros.py`, `parsers.py`, `workout.py`, `plan.py`, `readiness.py`, `report.py`, `setup.sh`, `chat-bundle.sh` |
| `athlete/` | your `profile.yaml` (git-ignored) and an example |
| `plans/` | one folder per plan (git-ignored) |
| `tests/` | pytest on synthetic COROS outputs |

## Development

```bash
.venv/bin/ruff check . && .venv/bin/pytest -q
```

Issues and pull requests are welcome. Never include personal data (yours or anyone's) in fixtures, examples,
issues or PRs.

## Notes

- Built on the official [COROS MCP](https://github.com/coroslab/COROS-MCP); the helper script is downloaded at
  setup, not redistributed.
- The coach gives training guidance, not medical advice. Pain or illness: see a professional.
