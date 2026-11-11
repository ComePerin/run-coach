#!/usr/bin/env python3
"""Week board: the sessions of one plan week as a standalone HTML page, plus the weekly volume of recent weeks.

The page lists the week's sessions (no days: "Session 2 of 5"), each with duration, distance and difficulty; tapping
one unfolds its detail: the workout drawn step by step (bar height = intensity), every step with its pace range
(easy and recovery steps get the athlete's zone paces from the threshold) and repeats, and the coach's note. The volume chart shows km per week, planned (band) vs run (line).

The script computes, the template draws. Sessions come from plan.yaml (`planned:`, `course:`, `status:`, `actual:`,
`notes:`). Volume uses the provider's activities (COROS or Garmin) for the last weeks, or with --offline only what
`plan.py sync` stored in the plan.

    week.py build --plan PLAN [--week N | --date YYYY-MM-DD] [--history 12] [--offline] [--threshold M:SS]
                  [--out FILE] [--json]

Default week: the one containing today (first week before the plan starts, last week after it ends).
Output: plans/<slug>/weeks/week-<N>.html (git-ignored: it contains training data).
Send it with `scripts/telegram.py send FILE` when Telegram is configured.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plan as PL  # noqa: E402
import readiness as R  # noqa: E402
import recap as RC  # noqa: E402

EASY_PACE_S = 330            # s/km, only to size distance-based easy steps when nothing better is known
FREE_STEP_S = 600            # a lap-button step has no length: draw it as 10′
DIFFICULTY = {"recovery": 1, "easy": 1, "rest": 0, "cross": 1, "strength": 2, "strides": 2, "long": 2,
              "medium_long": 2, "fartlek": 3, "progression": 3, "hills": 3, "tempo": 3, "threshold": 4,
              "race_pace": 4, "intervals": 4, "repetition": 5, "race": 5}
TYPE_LABEL = {"medium_long": "Medium-long run", "race_pace": "Race pace", "long": "Long run", "easy": "Easy run"}
OUTCOME = {"done": ("Done", "ok"), "partial": ("Partial", "off"), "missed": ("Missed", "off"),
           "skipped": ("Skipped", "none")}


# ----------------------------------------------------------------------------- week selection

def plan_start(plan: dict) -> date:
    return PL.d(plan["plan"]["start"])


def week_count(plan: dict) -> int:
    return int(plan["plan"].get("weeks") or len(plan.get("weeks") or []) or 1)


def week_for(plan: dict, day: date) -> int:
    """Week number containing `day`, clamped to the plan."""
    n = (day - plan_start(plan)).days // 7 + 1
    return max(1, min(n, week_count(plan)))


def find_week(plan: dict, n: int) -> dict:
    for i, w in enumerate(plan.get("weeks") or []):
        if int(w.get("n") or i + 1) == n:
            return w
    return {"n": n, "sessions": []}


# ----------------------------------------------------------------------------- workout structure

def _zone(kind: str, band: list[int] | None, threshold_s: float | None) -> int:
    """Intensity 1–5 used for bar height and colour: easy steps 1, work steps from their pace vs threshold."""
    if kind != "rep":
        return 1
    if band and threshold_s:
        ratio = sum(band) / 2 / threshold_s       # > 1 = slower than threshold
        return 2 if ratio > 1.15 else 3 if ratio > 1.05 else 4 if ratio > 0.98 else 5
    return 4


def _pace_range(lo: float, hi: float) -> str:
    return f"{RC.pace(lo)}–{RC.pace(hi)}/km"


def zone_pace(kind: str, threshold_s: float | None) -> str:
    """Pace range for a step without its own target: easy zone, recovery zone for jogs (from the threshold)."""
    if not threshold_s:
        return ""
    lo, hi = R.pace_zones(round(threshold_s))["recovery" if kind == "jog" else "easy"]
    return _pace_range(lo, hi)


def _step(sec: dict, in_group: bool, threshold_s: float | None) -> dict:
    st, t, v = sec.get("sectionType"), sec.get("targetType"), sec.get("targetValue")
    band, hr = RC._pace_band(sec, threshold_s), RC._hr_band(sec)
    if st == 1:
        name, kind = "Warm-up", "easy"
    elif st == 4:
        name, kind = "Cool-down", "easy"
    elif st == 3:
        name, kind = "Recovery", "jog"
    elif in_group or band or hr:
        name, kind = "Work", "rep"
    else:
        name, kind = "Run", "easy"
    if t == 2 and v:
        secs, length = float(v), RC.short_dur(v)
    elif t == 1 and v:
        per_km = sum(band) / 2 if band else (threshold_s * 1.25 if threshold_s else EASY_PACE_S)
        secs, length = v / 1000 * per_km, RC.short_dist(v)
    else:
        secs, length = FREE_STEP_S, "until lap"
    if band:
        target = _pace_range(*band)
    elif hr:
        target = f"{hr[0]}–{hr[1]} bpm"
    else:
        target = zone_pace(kind, threshold_s)
    return {"name": name, "kind": kind, "s": round(secs), "zone": _zone(kind, band, threshold_s),
            "length": length, "target": target}


def blocks(session: dict, threshold_s: float | None) -> list[dict]:
    """The workout as the athlete reads it: [{repeats, steps: [...]}]; repeats > 1 for interval groups.
    Without a course: one block of the planned duration."""
    course = session.get("course") or {}
    out = []
    for sec in course.get("sections") or []:
        if sec.get("intervalGroup"):
            out.append({"repeats": int(sec.get("repeats") or 1),
                        "steps": [_step(s, True, threshold_s) for s in sec.get("sets") or []]})
        else:
            out.append({"repeats": 1, "steps": [_step(sec, False, threshold_s)]})
    if out:
        return out
    pl = session.get("planned") or {}
    if not pl.get("duration_min") or session.get("sport") == "rest":
        return []
    kind = "rep" if session.get("type") in PL.HARD_TYPES else "easy"
    if session.get("type") == "recovery":
        kind = "jog"
    target = str(pl.get("target") or "")
    if not re.search(r"\d:\d\d", target):            # "easy", "Z2"…: give the pace range anyway
        target = zone_pace(kind, threshold_s) if kind != "rep" else target
    return [{"repeats": 1, "steps": [{"name": {"rep": "Work", "jog": "Recovery run"}.get(kind, "Run"), "kind": kind,
                                      "s": round(pl["duration_min"] * 60), "zone": 3 if kind == "rep" else 1,
                                      "length": PL.fmt_min(pl["duration_min"]), "target": target}]}]


def total_seconds(bl: list[dict]) -> int:
    return sum(b["repeats"] * sum(s["s"] for s in b["steps"]) for b in bl)


# ----------------------------------------------------------------------------- sessions

def session_view(s: dict, i: int, of: int, threshold_s: float | None) -> dict:
    pl = s.get("planned") or {}
    a = s.get("actual") or {}
    bl = blocks(s, threshold_s)
    minutes = pl.get("duration_min") or (total_seconds(bl) / 60 if bl else None)
    typ = s.get("type") or ""
    word, level = OUTCOME.get(s.get("status") or "", ("", ""))
    return {
        "n": i, "of": of,
        "title": s.get("title") or TYPE_LABEL.get(typ, typ.replace("_", " ").capitalize()) or "Session",
        "type": TYPE_LABEL.get(typ, typ.replace("_", " ").capitalize()),
        "key": bool(s.get("key")),
        "difficulty": int(pl.get("difficulty") or DIFFICULTY.get(typ, 2)),
        "minutes": round(minutes) if minutes else None,
        "km": pl.get("distance_km"),
        "target": pl.get("target") or "",
        "description": pl.get("description") or "",
        "status_word": word,
        "status_level": level,
        "actual": PL.actual_summary(s) if a else "",
        "actual_min": a.get("duration_min"),
        "actual_km": a.get("distance_km"),
        "done": s.get("status") in ("done", "partial"),
        "notes": s.get("notes") or "",
        "feedback": s.get("feedback") or "",
        "blocks": bl,
    }


# ----------------------------------------------------------------------------- volume

def _families(plan: dict) -> set[str]:
    sports = {s.get("sport") for _, s in PL.iter_sessions(plan)}
    fam = set()
    if sports & {"run", "trail"} or not sports:
        fam |= {"run", "trail"}
    if "bike" in sports:
        fam.add("bike")
    return fam


def volume(plan: dict, n: int, history: int, activities: list[dict] | None) -> dict:
    """km per week for the `history` weeks ending with week n: planned (plan weeks only) and done."""
    import parsers as P

    start = plan_start(plan) + timedelta(weeks=n - 1)
    fam = _families(plan)
    rows = []
    for k in range(history - 1, -1, -1):
        ws = start - timedelta(weeks=k)
        pn = n - k                                   # plan week number, < 1 before the plan
        if pn < 1 and activities is None:
            continue                                 # nothing known before the plan without the provider
        planned = done = None
        if pn >= 1:
            sessions = find_week(plan, pn).get("sessions") or []
            planned = round(sum((s.get("planned") or {}).get("distance_km") or 0 for s in sessions), 1) or None
        if activities is not None:
            done = round(sum(a.get("distance_km") or 0 for a in activities
                             if ws <= PL.d(a["date"]) < ws + timedelta(days=7) and P.family(a) in fam), 1)
        elif pn >= 1:
            done = round(sum((s.get("actual") or {}).get("distance_km") or 0
                             for s in find_week(plan, pn).get("sessions") or []), 1)
        rows.append({"start": ws.isoformat(), "label": f"{ws.day} {ws:%b}", "week": pn if pn >= 1 else None,
                     "planned": planned, "done": done, "current": k == 0})
    full = [r["done"] for r in rows[:-1] if r["done"] is not None][-4:]
    avg = round(sum(full) / len(full), 1) if full else None
    return {"weeks": rows, "avg": avg, "avg_n": len(full),
            "source": "activities" if activities is not None else "plan"}


# ----------------------------------------------------------------------------- page data

def _range(start: date) -> str:
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day}–{end.day} {end:%b}"
    return f"{start.day} {start:%b} – {end.day} {end:%b}"


def build_data(plan: dict, n: int, threshold_s: float | None = None, activities: list[dict] | None = None,
               history: int = 12, mock: bool = False) -> dict:
    week = find_week(plan, n)
    start = plan_start(plan) + timedelta(weeks=n - 1)
    real = [s for s in sorted(week.get("sessions") or [], key=lambda s: str(s.get("date")))
            if s.get("sport") != "rest" and s.get("type") != "rest"]
    sessions = [session_view(s, i + 1, len(real), threshold_s) for i, s in enumerate(real)]

    done = [s for s in sessions if s["done"]]
    plan_min = sum(s["minutes"] or 0 for s in sessions)
    plan_km = round(sum(s["km"] or 0 for s in sessions), 1)
    overview = [
        {"label": "Sessions", "value": str(len(done)), "unit": "", "of": f"of {len(sessions)}"},
        {"label": "Distance", "value": f"{sum(s['actual_km'] or 0 for s in done):.1f}".replace(".0", ""),
         "unit": "km", "of": f"of {plan_km:g} km" if plan_km else ""},
        {"label": "Time", "value": PL.fmt_min(sum(s["actual_min"] or 0 for s in done)) if done else "0′",
         "unit": "", "of": f"of {PL.fmt_min(plan_min)}" if plan_min else ""},
    ]
    phase = str(week.get("phase") or "").capitalize()
    return {
        "title": week.get("focus") or (f"{phase} week" if phase else f"Week {n}"),
        "meta": " · ".join(x for x in (f"Week {n} of {week_count(plan)}", _range(start),
                                       f"{phase} phase" if phase else "") if x),
        "badge": "Mock data · draft for review" if mock else "",
        "overview": overview,
        "sessions": sessions,
        "volume": volume(plan, n, history, activities) if history else None,
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (Path(__file__).resolve().parent / "templates" / "week-board.html").read_text(encoding="utf-8")
    title = html.escape(f"{data['title']} · Week Board")
    return page.replace("__TITLE__", title).replace("__DATA__", payload)


# ----------------------------------------------------------------------------- CLI

def cmd_build(args) -> int:
    plan = PL.load_plan(args.plan)
    if args.week:
        n = args.week
        if not 1 <= n <= week_count(plan):
            raise SystemExit(f"week {n} is outside the plan (1–{week_count(plan)})")
    else:
        n = week_for(plan, PL.d(args.date) if args.date else PL.today())
    activities, warning = None, None
    if args.history and not args.offline:
        end = plan_start(plan) + timedelta(weeks=n, days=-1)
        try:
            activities = PL.fetch_activities(end - timedelta(weeks=args.history, days=-1), min(end, PL.today()))
        except (Exception, SystemExit) as e:  # noqa: BLE001 — no provider login: fall back to the plan
            warning = f"activities not fetched ({str(e)[:80]}): volume from plan.yaml only"
    threshold = RC.threshold_from_profile()
    if args.threshold:
        m, s = args.threshold.split(":")
        threshold = int(m) * 60 + int(s)
    data = build_data(plan, n, threshold, activities, args.history, mock=args.mock)
    if args.json:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return 0
    out = Path(args.out) if args.out else PL.plan_paths(args.plan)[0].parent / "weeks" / f"week-{n}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data), encoding="utf-8")
    print(json.dumps({"written": str(out), "week": n, "sessions": len(data["sessions"]),
                      "done": sum(1 for s in data["sessions"] if s["done"]),
                      "volume_source": (data["volume"] or {}).get("source"), "warning": warning}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the HTML board of one plan week")
    b.add_argument("--plan", required=True)
    g = b.add_mutually_exclusive_group()
    g.add_argument("--week", type=int, help="week number (default: the week containing today)")
    g.add_argument("--date", help="any day of the week to show (YYYY-MM-DD)")
    b.add_argument("--history", type=int, default=12, help="weeks in the volume chart (0 hides it)")
    b.add_argument("--offline", action="store_true", help="volume from plan.yaml only, no provider call")
    b.add_argument("--threshold", help="threshold pace M:SS for the pace ranges (default: athlete profile)")
    b.add_argument("--out")
    b.add_argument("--json", action="store_true", help="print the page data instead of writing HTML")
    b.add_argument("--mock", action="store_true", help="mark the page as mock data")
    args = parser.parse_args(argv)
    return cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
