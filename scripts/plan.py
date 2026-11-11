#!/usr/bin/env python3
"""Training plan engine: plan.yaml is the source of truth, plan.md is generated.

Commands (PLAN = path to plans/<slug>/ or to its plan.yaml):
    plan.py init SLUG --title T --start YYYY-MM-DD --weeks N [--goal-date D] [--sessions-per-week K] [--weekly-minutes M]
    plan.py validate PLAN           # schema, COROS course JSON, load/intensity guardrails
    plan.py render PLAN             # regenerate plan.md
    plan.py status PLAN             # current week + next sessions (terminal)
    plan.py push PLAN [--days 7] [--yes] [--files]   # COROS: create/update on the calendar
                                             # Garmin: send to intervals.icu → Garmin Connect calendar, or with
                                             # --files (or no intervals.icu key) export FIT files (dry run without --yes)
    plan.py sync PLAN [--details] [--no-readiness]  # fetch activities + readiness, match, render
    plan.py profile                 # refresh athlete/profile.yaml baseline from COROS or Garmin
    plan.py readiness               # readiness snapshot only (no plan needed)
    plan.py zones [--threshold 3:55] # pace zones from threshold pace (defaults to athlete profile)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parsers as P  # noqa: E402
import readiness as R  # noqa: E402
import source as S  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = REPO_ROOT / "athlete" / "profile.yaml"

STATUSES = ("planned", "pushed", "adjusted", "done", "partial", "missed", "skipped")
SPORTS = ("run", "trail", "bike", "strength", "swim", "other", "rest")
COURSE_SPORT = {"run": 1, "bike": 2, "trail": 5}
SESSION_TYPES = ("easy", "recovery", "long", "medium_long", "strides", "fartlek", "progression", "tempo",
                 "threshold", "intervals", "repetition", "hills", "race_pace", "race", "cross", "strength", "rest")
HARD_TYPES = {"fartlek", "progression", "tempo", "threshold", "intervals", "repetition", "hills", "race_pace", "race"}
STATUS_ICON = {"planned": "⬜", "pushed": "📲", "adjusted": "✏️", "done": "✅", "partial": "⚠️",
               "missed": "❌", "skipped": "⏭️"}
OPEN_STATUSES = {"planned", "pushed", "adjusted"}


# ----------------------------------------------------------------------------- io

def plan_paths(path: str | Path) -> tuple[Path, Path]:
    p = Path(path)
    if p.is_dir():
        p = p / "plan.yaml"
    return p, p.with_name("plan.md")


def _norm_dates(obj):
    if isinstance(obj, dict):
        return {k: _norm_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_norm_dates(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def load_plan(path: str | Path) -> dict:
    yaml_path, _ = plan_paths(path)
    with open(yaml_path, encoding="utf-8") as fh:
        return _norm_dates(yaml.safe_load(fh))


def save_plan(plan: dict, path: str | Path) -> None:
    yaml_path, _ = plan_paths(path)
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(plan, fh, sort_keys=False, allow_unicode=True, width=110)


def iter_sessions(plan: dict):
    for week in plan.get("weeks", []):
        for s in week.get("sessions", []) or []:
            yield week, s


def today() -> date:
    return date.today()


def d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def fmt_min(minutes: float | None) -> str:
    if not minutes:
        return "—"
    minutes = int(round(minutes))
    return f"{minutes // 60}h{minutes % 60:02d}" if minutes >= 60 else f"{minutes}′"


# ----------------------------------------------------------------------------- validation

def validate_course(course: dict, sport: str) -> list[str]:
    """Validate a COROS course JSON against the createScheduledWorkout rules (subset)."""
    errs: list[str] = []
    if not str(course.get("courseName", "")).strip():
        errs.append("courseName is empty")
    elif len(course["courseName"]) > 100:
        errs.append("courseName longer than 100 characters")
    if not str(course.get("courseDescription", "")).strip():
        errs.append("courseDescription is empty (COROS rejects edits of workouts without description)")
    expected = COURSE_SPORT.get(sport)
    if course.get("sportType") not in (1, 2, 5):
        errs.append("sportType must be 1 (run), 2 (bike) or 5 (trail)")
    elif expected and course["sportType"] != expected:
        errs.append(f"sportType {course['sportType']} does not match session sport '{sport}'")
    if "dayNo" in course:
        errs.append("do not set dayNo on scheduled workouts")
    sections = course.get("sections") or []
    if not sections:
        errs.append("sections must not be empty")

    def check_plain(sec: dict, where: str, in_set: bool) -> None:
        st = sec.get("sectionType")
        allowed = (2, 3) if in_set else (1, 2, 3, 4)
        if st not in allowed:
            errs.append(f"{where}: sectionType must be one of {allowed}")
        tt = sec.get("targetType")
        if tt not in (1, 2, 3, 4):
            errs.append(f"{where}: targetType required (1 distance m, 2 time s, 3 climb m, 4 free)")
        elif tt == 4:
            if sec.get("targetValue") not in (None, 0):
                errs.append(f"{where}: free mode (targetType 4) must not have targetValue")
        else:
            tv = sec.get("targetValue")
            if not isinstance(tv, int) or tv <= 0:
                errs.append(f"{where}: targetValue must be a positive integer")
            if tt == 3 and sport != "trail":
                errs.append(f"{where}: climb target only for trail")
            if tt == 2 and sport == "trail":
                errs.append(f"{where}: trail running does not support time targets")
        fmt_fields = {
            "zone": ["sectionIntensity"],
            "percent": ["intensityPercentStart", "intensityPercentEnd"],
            "absolute": ["intensityValueStart", "intensityValueEnd"],
        }
        present = [k for k, fields in fmt_fields.items() if any(f in sec for f in fields)]
        it = sec.get("intensityType")
        if it is None and present:
            errs.append(f"{where}: intensity fields require intensityType")
        if it is not None:
            if len(present) != 1:
                errs.append(f"{where}: intensityType needs exactly one format (zone, percent or absolute)")
            if sport == "run" and it not in (1, 2, 4):
                errs.append(f"{where}: running allows intensityType 1/2/4")
            if sport == "bike" and it not in (1, 4):
                errs.append(f"{where}: cycling allows intensityType 1/4")
            if "percent" in present:
                s, e = sec.get("intensityPercentStart"), sec.get("intensityPercentEnd")
                if not (isinstance(s, int) and isinstance(e, int) and s < e):
                    errs.append(f"{where}: percent range needs integers with start < end")
                if it == 4:
                    errs.append(f"{where}: power cannot use percent ranges")
            if "absolute" in present:
                s, e = sec.get("intensityValueStart"), sec.get("intensityValueEnd")
                if not (isinstance(s, int) and isinstance(e, int)):
                    errs.append(f"{where}: absolute range needs both integer endpoints")
                elif it == 2 and not (120 <= min(s, e) and max(s, e) <= 1499):
                    errs.append(f"{where}: pace must be 120-1499 s/km")
                elif it == 1 and not (30 <= min(s, e) and max(s, e) <= 240):
                    errs.append(f"{where}: heart rate must be 30-240 bpm")
            if "zone" in present and it == 4 and sport in ("run", "trail"):
                errs.append(f"{where}: running power accepts absolute watts only")
            for f in ("sectionIntensity", "intensityPercentStart", "intensityPercentEnd",
                      "intensityValueStart", "intensityValueEnd"):
                if sec.get(f) == 0:
                    errs.append(f"{where}: {f}=0 is invalid (omit the field for no intensity)")

    for i, sec in enumerate(sections):
        where = f"section {i + 1}"
        if sec.get("intervalGroup"):
            for f in ("intensityType", "targetType", "targetValue", "sectionIntensity"):
                if f in sec:
                    errs.append(f"{where}: interval group container must not have {f}")
            reps = sec.get("repeats")
            if not isinstance(reps, int) or not 1 <= reps <= 20:
                errs.append(f"{where}: repeats must be 1-20")
            sets = sec.get("sets") or []
            if not sets:
                errs.append(f"{where}: interval group needs sets")
            for j, member in enumerate(sets):
                if member.get("intervalGroup"):
                    errs.append(f"{where}.{j + 1}: interval groups cannot be nested")
                else:
                    check_plain(member, f"{where}.{j + 1}", in_set=True)
        else:
            check_plain(sec, where, in_set=False)
    return errs


def validate(plan: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    meta = plan.get("plan") or {}
    for key in ("id", "title", "start", "weeks"):
        if key not in meta:
            errors.append(f"plan.{key} is required")
    if errors:
        return errors, warnings
    start = d(meta["start"])
    end = start + timedelta(weeks=int(meta["weeks"])) - timedelta(days=1)
    budget = meta.get("weekly_minutes")
    per_week = meta.get("sessions_per_week")
    goal = (meta.get("goal") or {}).get("distance", "")
    long_cap = 180 if str(goal).lower() in ("marathon", "ultra", "trail") else 150
    ids: set[str] = set()
    prev_minutes: list[float] = []
    weeks = plan.get("weeks") or []
    if len(weeks) != int(meta["weeks"]):
        warnings.append(f"plan.weeks={meta['weeks']} but {len(weeks)} week blocks are defined")

    for w_index, week in enumerate(weeks):
        wn = week.get("n", w_index + 1)
        w_start = start + timedelta(weeks=w_index)
        w_end = w_start + timedelta(days=6)
        sessions = week.get("sessions") or []
        minutes = 0.0
        hard_days: list[date] = []
        long_min = 0.0
        n_sessions = 0
        for s in sessions:
            sid = s.get("id", "?")
            label = f"week {wn} / {sid}"
            for key in ("id", "date", "sport", "type", "title"):
                if key not in s:
                    errors.append(f"{label}: missing '{key}'")
            if sid in ids:
                errors.append(f"{label}: duplicate session id")
            ids.add(sid)
            if s.get("status", "planned") not in STATUSES:
                errors.append(f"{label}: invalid status {s.get('status')}")
            if s.get("sport") not in SPORTS:
                errors.append(f"{label}: sport must be one of {SPORTS}")
            if s.get("type") not in SESSION_TYPES:
                errors.append(f"{label}: type must be one of {SESSION_TYPES}")
            if "date" in s:
                sd = d(s["date"])
                if not start <= sd <= end:
                    errors.append(f"{label}: date {sd} outside plan ({start} → {end})")
                elif not w_start <= sd <= w_end:
                    errors.append(f"{label}: date {sd} not in week {wn} ({w_start} → {w_end})")
            dur = (s.get("planned") or {}).get("duration_min")
            if s.get("type") != "rest":
                n_sessions += 1
                if not dur:
                    errors.append(f"{label}: planned.duration_min is required")
                minutes += dur or 0
            if s.get("type") in HARD_TYPES and "date" in s:
                hard_days.append(d(s["date"]))
            if s.get("type") == "long":
                long_min = max(long_min, dur or 0)
            course = s.get("course")
            if course:
                errors.extend(f"{label}: {e}" for e in validate_course(course, s.get("sport", "")))
            elif s.get("sport") in COURSE_SPORT and s.get("type") != "rest":
                warnings.append(f"{label}: no COROS course JSON, it cannot be pushed to the watch")
        # guardrails
        if budget and minutes > budget * 1.1:
            warnings.append(f"week {wn}: {minutes:.0f} min planned > weekly budget {budget} min (+10%)")
        if per_week and n_sessions > per_week:
            warnings.append(f"week {wn}: {n_sessions} sessions > sessions_per_week {per_week}")
        recovery_week = week.get("phase") in ("recovery", "taper") or week.get("recovery", False)
        if prev_minutes and not recovery_week:
            ref = max(prev_minutes[-2:]) if len(prev_minutes) >= 2 else prev_minutes[-1]
            if ref and minutes > ref * 1.10:
                warnings.append(f"week {wn}: volume +{(minutes / ref - 1) * 100:.0f}% vs recent weeks (guideline ≤10%)")
            if len(prev_minutes) >= 2 and prev_minutes[-2] and minutes > prev_minutes[-2] * 1.30:
                warnings.append(f"week {wn}: >30% increase over 2 weeks (injury risk, Nielsen 2014)")
        prev_minutes.append(minutes)
        if minutes and len(hard_days) > max(2, round(n_sessions / 3)):
            warnings.append(f"week {wn}: {len(hard_days)} hard sessions — breaks ~80/20 easy/hard distribution")
        hard_days.sort()
        for a, b in zip(hard_days, hard_days[1:], strict=False):
            if (b - a).days < 2 and a != b:
                warnings.append(f"week {wn}: hard sessions on consecutive days ({a} and {b})")
        if long_min and minutes and long_min > max(0.35 * minutes, long_cap):
            warnings.append(f"week {wn}: long run {long_min:.0f} min exceeds min(30% weekly, {long_cap} min) guideline")
    return errors, warnings


# ----------------------------------------------------------------------------- render

def session_summary(s: dict) -> str:
    pl = s.get("planned") or {}
    bits = []
    if pl.get("duration_min"):
        bits.append(fmt_min(pl["duration_min"]))
    if pl.get("distance_km"):
        bits.append(f"{pl['distance_km']:g} km")
    if pl.get("target"):
        bits.append(str(pl["target"]))
    return " · ".join(bits)


def actual_summary(s: dict) -> str:
    a = s.get("actual") or {}
    if not a:
        return ""
    bits = []
    if a.get("duration_min"):
        bits.append(fmt_min(a["duration_min"]))
    if a.get("distance_km"):
        bits.append(f"{a['distance_km']:g} km")
    if a.get("avg_pace"):
        bits.append(f"{a['avg_pace']}/km")
    if a.get("avg_hr"):
        bits.append(f"{a['avg_hr']} bpm")
    if a.get("training_load"):
        bits.append(f"TL {a['training_load']:g}")
    if a.get("compliance_pct"):
        bits.append(f"{a['compliance_pct']}%")
    if a.get("matched_date") and a["matched_date"] != s.get("date"):
        bits.append(f"done {a['matched_date'][5:]}")
    return " · ".join(bits)


def render(plan: dict) -> str:
    meta = plan["plan"]
    goal = meta.get("goal") or {}
    lines = [f"# {meta['title']}", ""]
    lines.append("> Generated from `plan.yaml` by `scripts/plan.py render` — do not edit by hand.")
    lines.append("")
    info = [f"**Start** {meta['start']}", f"**Weeks** {meta['weeks']}"]
    if goal:
        g = " ".join(str(goal.get(k)) for k in ("distance", "date", "target_time") if goal.get(k))
        info.append(f"**Goal** {g}")
    if meta.get("sessions_per_week"):
        info.append(f"**Sessions/week** {meta['sessions_per_week']}")
    if meta.get("weekly_minutes"):
        info.append(f"**Budget** {fmt_min(meta['weekly_minutes'])}/week")
    if meta.get("last_sync"):
        info.append(f"**Last sync** {meta['last_sync']}")
    lines.append(" · ".join(info))
    lines.append("")
    if meta.get("summary"):
        lines += [meta["summary"].strip(), ""]

    rd = plan.get("readiness")
    if rd:
        icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(rd.get("level"), "")
        lines.append(f"## Readiness — {rd.get('date', '')} {icon} {rd.get('level', '')} "
                     f"(score {rd.get('score')}, confidence {rd.get('confidence')})")
        lines.append("")
        for name, sig in (rd.get("signals") or {}).items():
            sc = sig.get("score")
            lines.append(f"- **{name}** {'' if sc is None else f'({sc:+d})'} {sig.get('detail', '')}")
        lines.append("")

    # overview
    lines += ["## Overview", "", "| Week | Dates | Phase | Focus | Planned | Done | Sessions |",
              "|---|---|---|---|---|---|---|"]
    start = d(meta["start"])
    for i, week in enumerate(plan.get("weeks", [])):
        ws = start + timedelta(weeks=i)
        sessions = [s for s in week.get("sessions") or [] if s.get("type") != "rest"]
        planned = sum((s.get("planned") or {}).get("duration_min") or 0 for s in sessions)
        done = sum((s.get("actual") or {}).get("duration_min") or 0 for s in sessions)
        n_done = sum(1 for s in sessions if s.get("status") in ("done", "partial"))
        lines.append(f"| {week.get('n', i + 1)} | {ws:%d/%m}–{ws + timedelta(days=6):%d/%m} | "
                     f"{week.get('phase', '')} | {week.get('focus', '')} | {fmt_min(planned)} | "
                     f"{fmt_min(done) if done else '—'} | {n_done}/{len(sessions)} |")
    lines.append("")
    lines.append("Legend: ⬜ planned · 📲 on watch · ✏️ adjusted · ✅ done · ⚠️ partial · ❌ missed · ⏭️ skipped")
    lines.append("")

    for i, week in enumerate(plan.get("weeks", [])):
        ws = start + timedelta(weeks=i)
        lines.append(f"## Week {week.get('n', i + 1)} — {ws:%d %b} · {week.get('phase', '')}")
        if week.get("focus"):
            lines.append(f"*{week['focus']}*")
        lines += ["", "| Day | Session | Planned | Status | Actual |", "|---|---|---|---|---|"]
        for s in sorted(week.get("sessions") or [], key=lambda x: x.get("date", "")):
            sd = d(s["date"])
            key = " 🔑" if s.get("key") else ""
            lines.append(f"| {sd:%a %d/%m} | {s.get('title', '')}{key} | {session_summary(s)} | "
                         f"{STATUS_ICON.get(s.get('status', 'planned'), '')} | {actual_summary(s)} |")
        lines.append("")
        details = [s for s in week.get("sessions") or []
                   if (s.get("planned") or {}).get("description") or s.get("notes") or s.get("feedback")]
        if details:
            lines.append("<details><summary>Session details</summary>\n")
            for s in details:
                desc = ((s.get("planned") or {}).get("description") or "").strip()
                lines.append(f"- **{s['date']} {s['title']}**" + (f" — {desc}" if desc else ""))
                if s.get("feedback"):
                    lines.append(f"  - _Athlete:_ {s['feedback'].strip()}")
                if s.get("notes"):
                    lines.append(f"  - _Coach:_ {s['notes'].strip()}")
            lines.append("\n</details>\n")
        if week.get("unplanned"):
            lines.append("Unplanned activities: " + "; ".join(
                f"{u['date'][5:]} {u['sport']} {fmt_min(u.get('duration_min'))}" for u in week["unplanned"]))
            lines.append("")
        if week.get("review"):
            lines += [f"**Review:** {week['review'].strip()}", ""]
    return "\n".join(lines).rstrip() + "\n"


def cmd_render(path: str) -> None:
    plan = load_plan(path)
    _, md_path = plan_paths(path)
    md_path.write_text(render(plan), encoding="utf-8")
    print(f"rendered {md_path}")


# ----------------------------------------------------------------------------- matching

def match_activities(plan: dict, activities: list[dict], until: date) -> dict:
    """Match activities to open sessions. Mutates the plan; returns a change summary."""
    used: set[str] = set()
    for _, s in iter_sessions(plan):
        lid = (s.get("actual") or {}).get("label_id")
        if lid:
            used.add(lid)
    by_date: dict[str, list[dict]] = {}
    for a in activities:
        by_date.setdefault(a["date"], []).append(a)

    def compatible(session_sport: str, act: dict) -> bool:
        fam = P.family(act)
        if session_sport in ("run", "trail"):
            return fam in ("run", "trail")
        if session_sport == "bike":
            return fam == "bike"
        if session_sport == "swim":
            return fam == "swim"
        return fam == "other"

    def pick(s: dict, day: str) -> dict | None:
        cands = [a for a in by_date.get(day, []) if a.get("label_id") not in used and compatible(s["sport"], a)]
        if not cands:
            return None
        target = ((s.get("planned") or {}).get("duration_min") or 0) * 60
        return min(cands, key=lambda a: abs((a.get("duration_s") or 0) - target))

    changes = {"done": [], "partial": [], "missed": [], "unplanned": []}
    open_sessions = [s for _, s in iter_sessions(plan)
                     if s.get("status", "planned") in OPEN_STATUSES and s.get("type") != "rest" and d(s["date"]) <= until]
    # pass 1: same day, pass 2: +/- 1 day
    for offset_pass in (0, 1):
        for s in open_sessions:
            if s.get("status") in ("done", "partial"):
                continue
            sd = d(s["date"])
            days = [sd] if offset_pass == 0 else [sd + timedelta(days=1), sd - timedelta(days=1)]
            act = None
            for day in days:
                act = pick(s, day.isoformat())
                if act:
                    break
            if not act:
                continue
            used.add(act["label_id"])
            planned = (s.get("planned") or {}).get("duration_min") or 0
            dur_min = round((act.get("duration_s") or 0) / 60, 1)
            compliance = round(dur_min / planned * 100) if planned else None
            s["actual"] = {
                "label_id": act["label_id"],
                "sport_type": act.get("sport_type"),
                "name": act.get("name"),
                "matched_date": act["date"],
                "duration_min": dur_min,
                "distance_km": act.get("distance_km"),
                "avg_pace": P.seconds_to_pace(act["avg_pace_s"]) if act.get("avg_pace_s") else None,
                "avg_hr": act.get("avg_hr"),
                "compliance_pct": compliance,
            }
            s["actual"] = {k: v for k, v in s["actual"].items() if v is not None}
            s["status"] = "done" if compliance is None or compliance >= 80 else "partial"
            changes[s["status"]].append(s["id"])
    for s in open_sessions:
        if s.get("status", "planned") in OPEN_STATUSES and d(s["date"]) < until:
            s["status"] = "missed"
            changes["missed"].append(s["id"])

    # unplanned activities within the plan range
    meta = plan["plan"]
    start = d(meta["start"])
    for a in activities:
        if a.get("label_id") in used:
            continue
        ad = d(a["date"])
        idx = (ad - start).days // 7
        if 0 <= idx < len(plan.get("weeks", [])):
            week = plan["weeks"][idx]
            existing = {u.get("label_id") for u in week.get("unplanned") or []}
            if a["label_id"] not in existing:
                week.setdefault("unplanned", []).append({
                    "date": a["date"], "sport": a["sport"], "label_id": a["label_id"],
                    "duration_min": round((a.get("duration_s") or 0) / 60, 1),
                    "distance_km": a.get("distance_km"), "avg_hr": a.get("avg_hr"),
                })
                changes["unplanned"].append(f"{a['date']} {a['sport']}")
    return changes


# ----------------------------------------------------------------------------- provider-backed commands

def fetch_activities(start: date, end: date) -> list[dict]:
    """All activities in [start, end] from the active provider (see scripts/source.py)."""
    return S.activities(start, end)


def fetch_readiness() -> dict:
    t = today()
    hrv = S.hrv(t - timedelta(days=6), t)
    rhr = S.resting_hr(14)
    sleep = S.sleep(7)
    recovery = S.recovery()
    load = S.load(14)
    snap = R.compute(hrv, rhr, sleep, recovery, load)
    snap["date"] = t.isoformat()
    snap["source"] = S.label()
    return snap


def cmd_sync(path: str, details: bool, with_readiness: bool) -> None:
    plan = load_plan(path)
    meta = plan["plan"]
    start = d(meta["start"])
    end = min(today(), start + timedelta(weeks=int(meta["weeks"])) - timedelta(days=1))
    if end < start:
        print(json.dumps({"info": "plan has not started yet"}))
        return
    acts = fetch_activities(start, end)
    changes = match_activities(plan, acts, until=today())
    if details and S.provider() == "coros":
        import coros

        for _, s in iter_sessions(plan):
            a = s.get("actual") or {}
            if s.get("key") and a.get("label_id") and "training_load" not in a:
                det = P.parse_activity_detail(coros.call("getActivityDetail", {
                    "labelId": a["label_id"], "sportType": a["sport_type"]}))
                for k in ("training_load", "aerobic_te", "anaerobic_te", "training_focus", "rpe_label"):
                    if det.get(k) is not None:
                        a[k] = det[k]
    if with_readiness:
        plan["readiness"] = fetch_readiness()
    meta["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_plan(plan, path)
    _, md_path = plan_paths(path)
    md_path.write_text(render(plan), encoding="utf-8")
    upcoming = [{"id": s["id"], "date": s["date"], "title": s["title"], "status": s.get("status", "planned")}
                for _, s in iter_sessions(plan)
                if today() <= d(s["date"]) <= today() + timedelta(days=7)]
    print(json.dumps({"activities_fetched": len(acts), "changes": changes,
                      "readiness": plan.get("readiness"), "next_7_days": upcoming}, indent=1, ensure_ascii=False))


def cmd_push(path: str, days: int, yes: bool, files: bool = False) -> int:
    if S.provider() == "garmin":
        import intervals

        if intervals.configured() and not files:
            return cmd_push_intervals(path, days, yes)
        return cmd_export(path, days, yes)
    import coros

    plan = load_plan(path)
    errors, _ = validate(plan)
    if errors:
        print("plan has validation errors, fix them first:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    horizon = today() + timedelta(days=days)
    todo = []
    for _, s in iter_sessions(plan):
        status = s.get("status", "planned")
        if not s.get("course") or not today() <= d(s["date"]) <= horizon:
            continue
        ref = (s.get("coros") or {}).get("id_in_plan")
        if status == "planned" and not ref:
            todo.append(("create", s))
        elif status == "adjusted" and ref:
            todo.append(("update", s))
        elif status == "adjusted":
            todo.append(("create", s))
    if not todo:
        print("nothing to push")
        return 0
    for action, s in todo:
        print(f"{'DRY-RUN ' if not yes else ''}{action:6} {s['date']} {s['title']}")
    if not yes:
        print("\nRe-run with --yes to write these to the COROS calendar.")
        return 0
    for action, s in todo:
        args = {"date": P.yyyymmdd(s["date"]), "course": s["course"]}
        try:
            if action == "create":
                out = coros.call("createScheduledWorkout", args)
            else:
                args["idInPlan"] = str(s["coros"]["id_in_plan"])
                out = coros.call("updateScheduledWorkout", args)
        except Exception as exc:  # noqa: BLE001 - surface any failure, never retry blindly
            save_plan(plan, path)
            print(f"FAILED {action} {s['id']}: {exc}\nDo not retry before checking the COROS calendar "
                  f"(queryTrainingSchedule) — the write may have been saved.", file=sys.stderr)
            return 1
        new_id = P.parse_created_id(out)
        s["coros"] = {"id_in_plan": new_id, "pushed_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        s["status"] = "pushed"
        others = [ln.strip("- ").strip() for ln in out.splitlines() if ln.startswith("- ")]
        print(f"OK {action} {s['date']} {s['title']}" + (f" (also that day: {', '.join(others)})" if others else ""))
        save_plan(plan, path)
    cmd_render(path)
    return 0


def cmd_export(path: str, days: int, yes: bool, out_dir: str | Path | None = None) -> int:
    """Garmin: write the next sessions as FIT workout files (the Personal API cannot write to the calendar)."""
    import fitworkout as F

    plan = load_plan(path)
    errors, _ = validate(plan)
    horizon = today() + timedelta(days=days)
    todo = [s for _, s in iter_sessions(plan)
            if s.get("course") and today() <= d(s["date"]) <= horizon
            and s.get("status", "planned") in ("planned", "adjusted")]
    for s in todo:
        errors += [f"{s['id']}: {e}" for e in F.validate_for_garmin(s["course"])]
    if errors:
        print("plan has validation errors, fix them first:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    if not todo:
        print("nothing to export")
        return 0
    folder = Path(out_dir) if out_dir else REPO_ROOT / "exports"
    for s in todo:
        print(f"{'DRY-RUN ' if not yes else ''}export {s['date']} {s['title']} → "
              f"{folder.name}/{F.file_name(s['date'], s['course'])}")
    if not yes:
        print("\nRe-run with --yes to write the FIT workout files.")
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    for s in todo:
        name = F.file_name(s["date"], s["course"])
        (folder / name).write_bytes(F.course_to_fit(s["course"]))
        s["garmin"] = {"file": name, "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        s["status"] = "pushed"
        save_plan(plan, path)
        print(f"OK export {s['date']} {s['title']} → {folder / name}")
    print("\n" + F.COPY_HELP)
    cmd_render(path)
    return 0


def cmd_push_intervals(path: str, days: int, yes: bool) -> int:
    """Garmin: create/update the next sessions on intervals.icu, which uploads them to the Garmin Connect calendar."""
    import fitworkout as F
    import intervals as I

    plan = load_plan(path)
    errors, _ = validate(plan)
    horizon = today() + timedelta(days=days)
    todo = []
    for _, s in iter_sessions(plan):
        status = s.get("status", "planned")
        if not s.get("course") or not today() <= d(s["date"]) <= horizon:
            continue
        ref = (s.get("intervals") or {}).get("event_id")
        if status == "planned" and not ref:
            todo.append(("create", s))
        elif status == "adjusted":
            todo.append(("update" if ref else "create", s))
    for _, s in todo:
        errors += [f"{s['id']}: {e}" for e in F.validate_for_garmin(s["course"])]
    if not todo and not errors:
        print("nothing to push")
        return 0
    settings: dict[str, dict] = {}
    try:
        for _, s in todo:
            sport = I.EVENT_TYPE.get(s["course"].get("sportType", 1), "Run")
            if sport not in settings:
                settings[sport] = I.sport_settings(s["course"])
            errors += [f"{s['id']}: {e}" for e in I.preflight(s["course"], settings[sport])]
    except I.IntervalsError as exc:
        errors.append(str(exc))
    errors = list(dict.fromkeys(errors))
    if errors:
        print("cannot push, fix these first:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    for action, s in todo:
        print(f"{'DRY-RUN ' if not yes else ''}{action:6} {s['date']} {s['title']} → intervals.icu → Garmin Connect")
    if not yes:
        print("\nRe-run with --yes to write these to intervals.icu (it uploads the next ~7 days to Garmin Connect).")
        return 0
    slug = plan["plan"].get("id", "plan")
    failed = False
    for action, s in todo:
        sport = I.EVENT_TYPE.get(s["course"].get("sportType", 1), "Run")
        ev = I.event_payload(s["date"], s["course"], settings[sport].get("max_hr"),
                             external_id=f"run-coach:{slug}:{s['id']}")
        try:
            if action == "create":
                created = I.create([ev])
                event_id = created[0]["id"]
            else:
                event_id = s["intervals"]["event_id"]
                I.update(event_id, ev)
            back = I.get(event_id)
            fit = I.download_fit(event_id)
        except I.IntervalsError as exc:
            save_plan(plan, path)
            print(f"FAILED {action} {s['id']}: {exc}\nCheck `intervals.py day {s['date']}` before retrying.",
                  file=sys.stderr)
            return 1
        problems = I.verify(back, s["course"], fit)
        s["intervals"] = {"event_id": event_id, "pushed_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        s["status"] = "pushed"
        save_plan(plan, path)
        print(f"OK {action} {s['date']} {I.summary(back)}")
        for pr in problems:
            failed = True
            print(f"   ⚠ {pr}")
    print("\nintervals.icu uploads planned workouts to Garmin Connect (next ~7 days) when \"Upload planned workouts\" "
          "is ticked in https://intervals.icu/settings. Sync the watch from the Garmin Connect app.")
    cmd_render(path)
    return 1 if failed else 0


def cmd_profile() -> None:
    profile = {}
    if PROFILE_PATH.exists():
        profile = _norm_dates(yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {})
    since = today() - timedelta(weeks=8)
    acts = fetch_activities(since, today())
    fit = S.fitness(acts)
    load = S.load(7, fetch_activities(today() - timedelta(days=35), today()) if S.provider() == "garmin" else None)
    rhr = [r["rhr"] for r in S.resting_hr(14) if r["rhr"]]
    weekly: dict[str, dict] = {}
    for a in acts:
        wk = (d(a["date"]) - timedelta(days=d(a["date"]).weekday())).isoformat()
        w = weekly.setdefault(wk, {"run_km": 0.0, "minutes": 0.0, "sessions": 0})
        w["minutes"] += (a.get("duration_s") or 0) / 60
        w["sessions"] += 1
        if P.family(a) in ("run", "trail"):
            w["run_km"] += a.get("distance_km") or 0
    weeks_sorted = [weekly[k] for k in sorted(weekly)]
    baseline = {
        "updated": today().isoformat(),
        "vo2max": fit["vo2max"],
        "running_level": fit["running_level"],
        "threshold_pace": fit["threshold_pace"],
        "race_predictions": fit["predictions"],
        **({"fitness_source": fit["source"]} if fit.get("source") else {}),
        "resting_hr_14d": round(sum(rhr) / len(rhr)) if rhr else None,
        "load_ratio": load[-1]["ratio"] if load else None,
        "last_8_weeks": {
            "avg_run_km": round(sum(w["run_km"] for w in weeks_sorted) / max(len(weeks_sorted), 1), 1),
            "avg_minutes": round(sum(w["minutes"] for w in weeks_sorted) / max(len(weeks_sorted), 1)),
            "avg_sessions": round(sum(w["sessions"] for w in weeks_sorted) / max(len(weeks_sorted), 1), 1),
            "max_run_km": round(max((w["run_km"] for w in weeks_sorted), default=0), 1),
        },
    }
    if fit["threshold_pace"]:
        zones = R.pace_zones(P.pace_to_seconds(fit["threshold_pace"]))
        baseline["pace_zones"] = {z: f"{P.seconds_to_pace(a)}-{P.seconds_to_pace(b)}" for z, (a, b) in zones.items()}
    user = S.user()
    athlete = profile.get("athlete") or {}
    # keep hand-entered values when the provider has none (the Garmin Personal API exposes no height/age)
    profile["athlete"] = {k: user.get(k) if user.get(k) is not None else athlete.get(k)
                          for k in ("height_cm", "weight_kg", "age")}
    profile["provider"] = S.provider()
    profile["baseline"] = baseline
    profile.setdefault("preferences", {
        "availability": "TODO: days/times available, e.g. Mon-Fri 60 min, Sat 120 min, Sun 90 min",
        "sports": ["run"],
        "other_activities": "TODO: e.g. bouldering Tue/Thu, padel",
        "injuries": "TODO",
        "notes": "",
    })
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True))


def cmd_init(slug: str, title: str, start: str, weeks: int, goal_date: str | None, goal_distance: str | None,
             per_week: int | None, minutes: int | None) -> None:
    folder = REPO_ROOT / "plans" / slug
    if (folder / "plan.yaml").exists():
        raise SystemExit(f"{folder}/plan.yaml already exists")
    st = d(start)
    if st.weekday() != 0:
        print(f"note: {st} is not a Monday; weeks will run {st:%A} → {st + timedelta(days=6):%A}")
    plan = {
        "plan": {"id": slug, "title": title, "start": st.isoformat(), "weeks": weeks,
                 "goal": {k: v for k, v in {"distance": goal_distance, "date": goal_date}.items() if v},
                 "sessions_per_week": per_week, "weekly_minutes": minutes, "summary": "", "last_sync": None},
        "weeks": [{"n": i + 1, "phase": "", "focus": "", "sessions": []} for i in range(weeks)],
    }
    folder.mkdir(parents=True, exist_ok=True)
    save_plan(plan, folder)
    (folder / "journal.md").write_text(f"# Journal — {title}\n\nAppend-only coaching log (newest at the bottom).\n",
                                       encoding="utf-8")
    print(f"created {folder}/plan.yaml and journal.md")


def cmd_status(path: str) -> None:
    plan = load_plan(path)
    t = today()
    print(f"{plan['plan']['title']} — today {t}")
    for _, s in iter_sessions(plan):
        sd = d(s["date"])
        if t - timedelta(days=3) <= sd <= t + timedelta(days=7):
            marker = "→" if sd == t else " "
            print(f"{marker} {sd:%a %d/%m} {STATUS_ICON.get(s.get('status', 'planned'))} {s['title']:<40} "
                  f"{session_summary(s):<25} {actual_summary(s)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("slug")
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--weeks", type=int, required=True)
    p.add_argument("--goal-date")
    p.add_argument("--goal-distance")
    p.add_argument("--sessions-per-week", type=int)
    p.add_argument("--weekly-minutes", type=int)
    for name in ("validate", "render", "status"):
        sub.add_parser(name).add_argument("plan")
    p = sub.add_parser("push")
    p.add_argument("plan")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--files", action="store_true", help="Garmin: export FIT files instead of using intervals.icu")
    p = sub.add_parser("sync")
    p.add_argument("plan")
    p.add_argument("--details", action="store_true", help="fetch getActivityDetail for key sessions")
    p.add_argument("--no-readiness", action="store_true")
    sub.add_parser("profile")
    sub.add_parser("readiness")
    p = sub.add_parser("zones")
    p.add_argument("--threshold", help="threshold pace m:ss (default: athlete profile)")
    a = ap.parse_args(argv)

    if a.cmd == "init":
        cmd_init(a.slug, a.title, a.start, a.weeks, a.goal_date, a.goal_distance, a.sessions_per_week,
                 a.weekly_minutes)
    elif a.cmd == "validate":
        errors, warnings = validate(load_plan(a.plan))
        for w in warnings:
            print(f"WARN  {w}")
        for e in errors:
            print(f"ERROR {e}")
        print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1 if errors else 0
    elif a.cmd == "render":
        cmd_render(a.plan)
    elif a.cmd == "status":
        cmd_status(a.plan)
    elif a.cmd == "push":
        return cmd_push(a.plan, a.days, a.yes, a.files)
    elif a.cmd == "sync":
        cmd_sync(a.plan, a.details, not a.no_readiness)
    elif a.cmd == "profile":
        cmd_profile()
    elif a.cmd == "readiness":
        print(json.dumps(fetch_readiness(), indent=1, ensure_ascii=False))
    elif a.cmd == "zones":
        thr = a.threshold
        if not thr and PROFILE_PATH.exists():
            thr = (yaml.safe_load(PROFILE_PATH.read_text()) or {}).get("baseline", {}).get("threshold_pace")
        if not thr:
            print("give --threshold m:ss or run `plan.py profile` first", file=sys.stderr)
            return 1
        for zone, (fast, slow) in R.pace_zones(P.pace_to_seconds(thr)).items():
            print(f"{zone:<11} {P.seconds_to_pace(fast)}-{P.seconds_to_pace(slow)} /km  ({fast}-{slow} s/km)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
