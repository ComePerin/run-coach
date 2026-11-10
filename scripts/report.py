#!/usr/bin/env python3
"""Draft a "current state of training" report from COROS or Garmin data (and the active plan, if any).

    report.py [PLAN] [--weeks 4] [--no-sync] [--out FILE] [--stdout]

- With PLAN (plans/<slug>/ or its plan.yaml): syncs the plan first (unless --no-sync), then reports plan progress,
  adherence, key sessions, readiness, fitness vs goal and the next 7 days.
- Without PLAN: reports the last N weeks of training from the activity history.

All numbers are computed here. The report contains `<!-- COACH: ... -->` placeholders that the agent replaces with
its assessment (see .claude/skills/coros-report/SKILL.md). Default output: plans/<slug>/reports/YYYY-MM-DD.md, or
reports/YYYY-MM-DD.md without a plan.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parsers as P  # noqa: E402
import plan as PL  # noqa: E402
import readiness as R  # noqa: E402
import source as S  # noqa: E402

GOAL_TO_PREDICTION = {"5k": "5k", "10k": "10k", "half": "half", "half marathon": "half", "marathon": "marathon"}
LEVEL_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def fetch_inputs(weeks: int) -> dict:
    """Everything the report needs from the active provider, COROS or Garmin (read-only)."""
    t = PL.today()
    garmin = S.provider() == "garmin"
    start = t - timedelta(weeks=weeks, days=t.weekday())
    # Garmin computes load (28 days back) and fitness (8 weeks) from activities: fetch a longer window once
    acts = PL.fetch_activities(min(start, t - timedelta(weeks=8)) - timedelta(days=28) if garmin else start, t)
    since = start.isoformat()
    return {
        "source": S.label(),
        "fitness": S.fitness([a for a in acts if a["date"] >= (t - timedelta(weeks=8)).isoformat()]
                             if garmin else None),
        "load": S.load(28, acts if garmin else None),
        "hrv": S.hrv(t - timedelta(days=6), t),
        "rhr": S.resting_hr(28),
        "sleep": S.sleep(14),
        "recovery": S.recovery(),
        "activities": [a for a in acts if a["date"] >= since],
    }


# ----------------------------------------------------------------------------- sections

def weekly_volume(activities: list[dict], weeks: int, until: date) -> list[dict]:
    """Per ISO week (Mon-Sun): run km, run hours, total hours, sessions, hours by family."""
    start = until - timedelta(days=until.weekday()) - timedelta(weeks=weeks - 1)
    rows = []
    for i in range(weeks):
        ws = start + timedelta(weeks=i)
        we = ws + timedelta(days=6)
        acts = [a for a in activities if ws <= PL.d(a["date"]) <= we]
        fam: dict[str, float] = {}
        for a in acts:
            f = P.family(a)
            fam[f] = fam.get(f, 0) + (a.get("duration_s") or 0) / 3600
        run = [a for a in acts if P.family(a) in ("run", "trail")]
        rows.append({
            "week_start": ws.isoformat(),
            "run_km": round(sum(a.get("distance_km") or 0 for a in run), 1),
            "run_h": round(sum((a.get("duration_s") or 0) for a in run) / 3600, 1),
            "total_h": round(sum((a.get("duration_s") or 0) for a in acts) / 3600, 1),
            "sessions": len(acts),
            "by_family": {k: round(v, 1) for k, v in sorted(fam.items(), key=lambda x: -x[1])},
            "partial": we > until,
        })
    return rows


def plan_progress(plan: dict, until: date) -> dict:
    meta = plan["plan"]
    start = PL.d(meta["start"])
    n_weeks = int(meta["weeks"])
    week_idx = min(max((until - start).days // 7, 0), n_weeks - 1)
    sessions = [s for _, s in PL.iter_sessions(plan) if s.get("type") != "rest"]
    past = [s for s in sessions if PL.d(s["date"]) < until]
    counts = {k: sum(1 for s in past if s.get("status") == k) for k in ("done", "partial", "missed", "skipped")}
    key_past = [s for s in past if s.get("key")]
    compliance = [s["actual"]["compliance_pct"] for s in past
                  if s.get("status") in ("done", "partial") and (s.get("actual") or {}).get("compliance_pct")]
    goal = meta.get("goal") or {}
    days_to_goal = (PL.d(goal["date"]) - until).days if goal.get("date") else None
    weeks = []
    for i, week in enumerate(plan.get("weeks", [])):
        ws = start + timedelta(weeks=i)
        ss = [s for s in week.get("sessions") or [] if s.get("type") != "rest"]
        weeks.append({
            "n": week.get("n", i + 1), "start": ws.isoformat(), "phase": week.get("phase", ""),
            "planned_min": sum((s.get("planned") or {}).get("duration_min") or 0 for s in ss),
            "actual_min": round(sum((s.get("actual") or {}).get("duration_min") or 0 for s in ss)),
            "done": sum(1 for s in ss if s.get("status") in ("done", "partial")),
            "total": len(ss),
            "unplanned_min": round(sum(u.get("duration_min") or 0 for u in week.get("unplanned") or [])),
            "current": i == week_idx,
            "future": ws > until,
        })
    return {
        "week_n": week_idx + 1, "weeks": n_weeks,
        "phase": plan["weeks"][week_idx].get("phase", "") if plan.get("weeks") else "",
        "past_sessions": len(past), "counts": counts,
        "adherence_pct": round((counts["done"] + counts["partial"]) / len(past) * 100) if past else None,
        "key_done": sum(1 for s in key_past if s.get("status") in ("done", "partial")), "key_total": len(key_past),
        "avg_compliance": round(mean(compliance)) if compliance else None,
        "days_to_goal": days_to_goal, "weeks_table": weeks,
    }


def readiness_trend(hrv: list[dict], rhr: list[dict], sleep: list[dict]) -> dict:
    rhr_vals = [r["rhr"] for r in rhr if r.get("rhr")]
    sleep_vals = [s for s in sleep if s.get("sleep_min")]
    last7_sleep = sleep_vals[-7:]
    return {
        "hrv_days": [(h["date"], h["hrv"], h["low"], h["high"], h["status"]) for h in hrv],
        "hrv_below": sum(1 for h in hrv if h["hrv"] < h["low"]),
        "hrv_mean": round(mean(h["hrv"] for h in hrv)) if hrv else None,
        "hrv_baseline": hrv[-1]["baseline"] if hrv else None,
        "rhr_7d": round(mean(rhr_vals[-7:])) if rhr_vals else None,
        "rhr_prev": round(mean(rhr_vals[-28:-7])) if len(rhr_vals) > 10 else None,
        "sleep_avg_h": round(mean(s["sleep_min"] for s in last7_sleep) / 60, 1) if last7_sleep else None,
        "sleep_score_avg": round(mean(s["score"] for s in last7_sleep if s.get("score"))) if last7_sleep else None,
    }


# ----------------------------------------------------------------------------- render

def build_report(data: dict, plan: dict | None, weeks: int, until: date) -> str:
    fit, load = data["fitness"], data["load"]
    snap = R.compute(data["hrv"], data["rhr"], data["sleep"], data["recovery"], load)
    trend = readiness_trend(data["hrv"], data["rhr"], data["sleep"])
    vol = weekly_volume(data["activities"], weeks, until)
    out: list[str] = []
    title = plan["plan"]["title"] if plan else "Training"
    out += [f"# Training report — {title}", "", f"*{until:%A %d %B %Y}* · data: {data.get('source', 'COROS')}", ""]

    # --- headline
    out += ["## Summary", "", "<!-- COACH: 3-5 sentences: where the athlete stands, the main positive, the main "
            "concern, and the one thing to focus on next. Plain language, no internal IDs. -->", ""]

    # --- key numbers
    prog = plan_progress(plan, until) if plan else None
    lvl = snap["level"]
    tiles = []
    if prog:
        tiles.append(f"**Week** {prog['week_n']}/{prog['weeks']} ({prog['phase'] or '—'})")
        if prog["days_to_goal"] is not None:
            tiles.append(f"**Race in** {prog['days_to_goal']} days")
        if prog["adherence_pct"] is not None:
            tiles.append(f"**Adherence** {prog['adherence_pct']}%")
    tiles.append(f"**Readiness** {LEVEL_ICON[lvl]} {lvl}")
    if load:
        tiles.append(f"**Load ratio** {load[-1]['ratio']:.2f} ({load[-1]['comment']})")
    if fit.get("vo2max"):
        tiles.append(f"**VO2max** {fit['vo2max']:g}")
    if fit.get("threshold_pace"):
        tiles.append(f"**Threshold** {fit['threshold_pace']}/km")
    out += [" · ".join(tiles), ""]

    # --- plan progress
    if prog:
        meta = plan["plan"]
        goal = meta.get("goal") or {}
        c = prog["counts"]
        out += ["## Plan progress", ""]
        out.append(f"- Sessions so far: {prog['past_sessions']} — ✅ {c['done']} · ⚠️ {c['partial']} · ❌ {c['missed']}"
                   f" · ⏭️ {c['skipped']}")
        if prog["key_total"]:
            out.append(f"- Key sessions completed: {prog['key_done']}/{prog['key_total']}")
        if prog["avg_compliance"] is not None:
            out.append(f"- Average duration compliance: {prog['avg_compliance']}%")
        if goal:
            pred_key = GOAL_TO_PREDICTION.get(str(goal.get("distance", "")).lower())
            pred = fit.get("predictions", {}).get(pred_key) if pred_key else None
            line = f"- Goal: {goal.get('distance', '')} on {goal.get('date', '?')}"
            if goal.get("target_time"):
                line += f", target {goal['target_time']}"
            if pred:
                who = "estimated" if fit.get("source") else "COROS"
                line += f" · {who} prediction today: **{pred}**"
            out.append(line)
        out += ["", "| Week | Start | Phase | Planned | Done | Sessions | Unplanned |", "|---|---|---|---|---|---|---|"]
        for w in prog["weeks_table"]:
            marker = " ◀" if w["current"] else ""
            done = "—" if w["future"] else PL.fmt_min(w["actual_min"])
            sessions = "—" if w["future"] else f"{w['done']}/{w['total']}"
            unpl = PL.fmt_min(w["unplanned_min"]) if w["unplanned_min"] else ""
            out.append(f"| {w['n']}{marker} | {PL.d(w['start']):%d/%m} | {w['phase']} | {PL.fmt_min(w['planned_min'])} "
                       f"| {done} | {sessions} | {unpl} |")
        out.append("")
        key_done = [s for _, s in PL.iter_sessions(plan)
                    if s.get("key") and s.get("status") in ("done", "partial", "missed") and PL.d(s["date"]) < until]
        if key_done:
            out += ["### Key sessions", "", "| Date | Session | Target | Status | Actual |", "|---|---|---|---|---|"]
            for s in key_done[-8:]:
                out.append(f"| {PL.d(s['date']):%d/%m} | {s['title']} | {(s.get('planned') or {}).get('target', '')} "
                           f"| {PL.STATUS_ICON.get(s['status'])} | {PL.actual_summary(s)} |")
            out += ["", "<!-- COACH: comment on key-session quality (paces vs targets, HR, fading, compliance). "
                    "Use lap data if you fetched it. -->", ""]

    # --- volume
    out += [f"## Training volume — last {weeks} weeks", "",
            "| Week of | Run km | Run h | Total h | Sessions | Split (h) |", "|---|---|---|---|---|---|"]
    for w in vol:
        split = ", ".join(f"{k} {v:g}" for k, v in w["by_family"].items())
        tag = " (in progress)" if w["partial"] else ""
        out.append(f"| {PL.d(w['week_start']):%d/%m}{tag} | {w['run_km']:g} | {w['run_h']:g} | {w['total_h']:g} "
                   f"| {w['sessions']} | {split} |")
    full = [w for w in vol if not w["partial"]]
    if len(full) >= 2:
        change = (full[-1]["run_km"] / full[-2]["run_km"] - 1) * 100 if full[-2]["run_km"] else None
        avg_km = mean(w["run_km"] for w in full)
        line = f"\nAverage {avg_km:.1f} run km/week over {len(full)} full weeks"
        if change is not None:
            line += f"; last full week {change:+.0f}% vs the week before"
        out.append(line + ".")
    out.append("")

    # --- load
    if load:
        last = load[-1]
        peak = max(load, key=lambda r: r["ratio"])
        excessive = [r["date"] for r in load if r["ratio"] >= 1.5]
        out += ["## Training load", "",
                f"- Today: short-term {last['short_term']} / long-term {last['long_term']} → ratio "
                f"**{last['ratio']:.2f}** ({last['comment']})",
                f"- Last {len(load)} days: ratio range {min(r['ratio'] for r in load):.2f}–{peak['ratio']:.2f} "
                f"(peak {PL.d(peak['date']):%d/%m})"
                + (f"; *Excessive* on {', '.join(PL.d(x).strftime('%d/%m') for x in excessive)}" if excessive else ""),
                f"- Long-term load trend: {load[0]['long_term']} → {last['long_term']}", ""]

    # --- readiness
    out += [f"## Recovery & readiness — {LEVEL_ICON[lvl]} {lvl} (confidence {snap['confidence']})", ""]
    for name, sig in snap["signals"].items():
        sc = sig["score"]
        out.append(f"- **{name}** {'' if sc is None else f'({sc:+d}) '}{sig['detail']}")
    if trend["hrv_days"]:
        out.append(f"- HRV last {len(trend['hrv_days'])} nights: mean {trend['hrv_mean']} ms (baseline "
                   f"{trend['hrv_baseline']}), {trend['hrv_below']} night(s) below normal range")
    if trend["rhr_7d"]:
        prev = f" vs {trend['rhr_prev']} bpm the 3 weeks before" if trend["rhr_prev"] else ""
        out.append(f"- Resting HR 7-day mean {trend['rhr_7d']} bpm{prev}")
    if trend["sleep_avg_h"]:
        out.append(f"- Sleep last 7 nights: {trend['sleep_avg_h']} h average, score {trend['sleep_score_avg']}")
    out.append("")

    # --- fitness
    if fit.get("vo2max") or fit.get("predictions"):
        preds = " · ".join(f"{k} {v}" for k, v in fit.get("predictions", {}).items())
        if fit.get("source"):  # Garmin: computed locally, no VO2max
            first = f"- Threshold pace {fit.get('threshold_pace') or '?'}/km ({fit['source']})"
        else:
            first = (f"- VO2max {fit.get('vo2max') or 0:g} · running level {fit.get('running_level') or 0:g}"
                     f" · threshold pace {fit.get('threshold_pace') or '?'}/km")
        out += ["## Fitness", "", first, f"- Race predictions: {preds}", ""]

    # --- next 7 days
    if plan:
        nxt = [s for _, s in PL.iter_sessions(plan) if until <= PL.d(s["date"]) <= until + timedelta(days=6)]
        out += ["## Next 7 days", ""]
        if nxt:
            out += ["| Day | Session | Planned | Status |", "|---|---|---|---|"]
            for s in nxt:
                out.append(f"| {PL.d(s['date']):%a %d/%m} | {s['title']}{' 🔑' if s.get('key') else ''} "
                           f"| {PL.session_summary(s)} | {PL.STATUS_ICON.get(s.get('status', 'planned'))} |")
        else:
            out.append("No sessions planned.")
        out.append("")

    out += ["## Coach's assessment", "",
            "<!-- COACH: What's going well / What to watch / Recommended adjustments (each change with the rule from "
            "decision-process.md) / Questions for the athlete. Write changes into plan.yaml only if the athlete "
            "agrees. -->", ""]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--weeks", type=int, default=4, help="weeks of history for volume (default 4)")
    ap.add_argument("--no-sync", action="store_true", help="do not sync the plan before reporting")
    ap.add_argument("--out", help="output file")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    a = ap.parse_args(argv)

    plan = None
    if a.plan:
        if not a.no_sync:
            PL.cmd_sync(a.plan, details=True, with_readiness=True)
        plan = PL.load_plan(a.plan)
    until = PL.today()
    text = build_report(fetch_inputs(a.weeks), plan, a.weeks, until)
    if a.stdout:
        print(text)
        return 0
    if a.out:
        out = Path(a.out)
    elif a.plan:
        out = PL.plan_paths(a.plan)[0].parent / "reports" / f"{until.isoformat()}.md"
    else:
        out = PL.REPO_ROOT / "reports" / f"{until.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
