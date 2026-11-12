#!/usr/bin/env python3
"""Session recap: one planned session (or one activity) → a standalone HTML page.

The script computes; the coach writes. Laps, paces, HR, zones and readiness come from the watch data. The
verdict, how it felt and the plan impact come from the session's ``recap:`` block in plan.yaml (written by the
coach, see .claude/skills/run-coach/references/plan-schema.md); missing parts render as "Not written yet".

    recap.py build --plan PLAN --session ID [--fit FILE] [--out FILE] [--json]
    recap.py build --date YYYY-MM-DD [--fit FILE] [--out FILE] [--json]     # no plan: laps only, no targets

PLAN = plans/<slug>/ or its plan.yaml. Laps are read from the activity's FIT file (downloaded from Garmin or
COROS, never cached because it holds the GPS track), or from --fit. Output: plans/<slug>/recaps/<date>-<id>.html,
or reports/recaps/<date>-<name>.html without a plan (both git-ignored: they contain health data).
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "templates" / "session-recap.html"
MIN_LAP_S = 5          # laps shorter than this are button noise
ZONE_NAMES = ("Z1", "Z2", "Z3", "Z4", "Z5")


# ----------------------------------------------------------------------------- formatting

def pace(s: float | None) -> str:
    if s is None:
        return "—"
    s = round(s)
    return f"{s // 60}:{s % 60:02d}"


def hms(seconds: float | None) -> str:
    if not seconds:
        return "—"
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def short_dur(seconds: float) -> str:
    """150 → 2′30, 120 → 2′, 45 → 45″."""
    s = round(seconds)
    if s < 60:
        return f"{s}″"
    return f"{s // 60}′{s % 60:02d}" if s % 60 else f"{s // 60}′"


def short_dist(m: float) -> str:
    return f"{m / 1000:g} km" if m >= 1000 and m % 100 == 0 else f"{m:g} m"


# ----------------------------------------------------------------------------- planned steps

def _pace_band(sec: dict, threshold_s: float | None) -> list[int] | None:
    if sec.get("intensityType") != 2:
        return None
    lo, hi = sec.get("intensityValueStart"), sec.get("intensityValueEnd")
    if lo and hi:
        return sorted([int(lo), int(hi)])
    plo, phi = sec.get("intensityPercentStart"), sec.get("intensityPercentEnd")
    if plo and phi and threshold_s:
        # % of threshold pace: 100 % = threshold, a higher % is faster (shorter s/km)
        return sorted([round(threshold_s * 100 / plo), round(threshold_s * 100 / phi)])
    return None


def _hr_band(sec: dict) -> list[int] | None:
    if sec.get("intensityType") == 1 and sec.get("intensityValueStart") and sec.get("intensityValueEnd"):
        return sorted([int(sec["intensityValueStart"]), int(sec["intensityValueEnd"])])
    return None


def expand_course(course: dict | None, threshold_s: float | None = None) -> list[dict]:
    """COROS course JSON → the flat list of steps the watch executes, in order."""
    out: list[dict] = []
    if not course:
        return out
    counters = {"rep": 0, "jog": 0, "block": 0}

    def add(sec: dict, in_group: bool) -> None:
        st = sec.get("sectionType")
        band, hr = _pace_band(sec, threshold_s), _hr_band(sec)
        step = {"section_type": st, "band": band, "hr_band": hr,
                "target_type": sec.get("targetType"), "target_value": sec.get("targetValue")}
        if st == 1:
            step.update(name="Warm-up", kind="easy")
        elif st == 4:
            step.update(name="Cool-down", kind="easy")
        elif st == 3:
            counters["jog"] += 1
            step.update(name=f"Recovery {counters['jog']}" if in_group else "Recovery", kind="jog")
        elif in_group or band or hr:
            counters["rep"] += 1
            step.update(name=f"Rep {counters['rep']}", kind="rep")
        else:
            counters["block"] += 1
            step.update(name="Run", kind="easy")
        out.append(step)

    for sec in course.get("sections") or []:
        if sec.get("intervalGroup"):
            for _ in range(int(sec.get("repeats") or 1)):
                for s in sec.get("sets") or []:
                    add(s, True)
        else:
            add(sec, False)
    # name recoveries "Jog n" like the athlete says it, numbered by the rep they follow
    for s in out:
        if s["kind"] == "jog" and s["name"].startswith("Recovery "):
            s["name"] = s["name"].replace("Recovery", "Jog")
    return out


def rep_sub(steps: list[dict]) -> str:
    """'Target 3:39–3:46/km, 2′30 jog between reps.'"""
    rep = next((s for s in steps if s["kind"] == "rep" and s.get("band")), None)
    if not rep:
        return ""
    bits = [f"Target {pace(rep['band'][0])}–{pace(rep['band'][1])}/km"]
    jog = next((s for s in steps if s["kind"] == "jog"), None)
    if jog and jog.get("target_type") == 2 and jog.get("target_value"):
        bits.append(f"{short_dur(jog['target_value'])} jog between reps")
    elif jog and jog.get("target_type") == 1 and jog.get("target_value"):
        bits.append(f"{short_dist(jog['target_value'])} jog between reps")
    return ", ".join(bits) + "."


# ----------------------------------------------------------------------------- FIT

def read_fit(data: bytes) -> dict:
    """FIT bytes → {laps: [{dur, dist_km, pace_s, hr, hr_max, intensity}], hr: [(elapsed_s, bpm)]}."""
    import fitdecode

    laps: list[dict] = []
    hr: list[tuple[float, int]] = []
    t0 = None
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.DISABLED) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue

            def g(name, _f=frame):
                return _f.get_value(name, fallback=None) if _f.has_field(name) else None

            if frame.name == "record":
                ts, bpm = g("timestamp"), g("heart_rate")
                if ts is not None and t0 is None:
                    t0 = ts
                if ts is not None and bpm:
                    hr.append(((ts - t0).total_seconds(), int(bpm)))
            elif frame.name == "lap":
                dur = g("total_timer_time") or g("total_elapsed_time") or 0
                dist = g("total_distance")
                speed = g("enhanced_avg_speed") or g("avg_speed")
                if not speed and dist and dur:
                    speed = dist / dur
                laps.append({
                    "dur": round(float(dur), 1),
                    "dist_km": round(dist / 1000, 3) if dist else None,
                    "pace_s": round(1000 / speed) if speed else None,
                    "hr": int(g("avg_heart_rate")) if g("avg_heart_rate") else None,
                    "hr_max": int(g("max_heart_rate")) if g("max_heart_rate") else None,
                    "intensity": str(g("intensity")) if g("intensity") is not None else None,
                })
    return {"laps": laps, "hr": hr}


# ----------------------------------------------------------------------------- alignment

def _actual(step: dict, lap: dict | None) -> dict:
    out = dict(step)
    if lap:
        out.update(dur=lap["dur"], dist=lap["dist_km"], pace=lap["pace_s"], hr=lap["hr"], hrMax=lap["hr_max"])
    else:
        planned = step.get("target_value") if step.get("target_type") == 2 else None
        out.update(dur=planned or 0, dist=None, pace=None, hr=None, hrMax=None)
    return out


def align(planned: list[dict], laps: list[dict]) -> tuple[list[dict], list[str]]:
    """Pair laps with planned steps in order (one lap per workout step). Returns (steps, warnings)."""
    laps = [lap for lap in laps if lap["dur"] >= MIN_LAP_S]
    warnings: list[str] = []
    if not planned:
        return laps_as_steps(laps), warnings
    if len(laps) != len(planned):
        warnings.append(f"{len(laps)} laps for {len(planned)} planned steps: paired in order"
                        + (", extra laps shown as 'Extra'" if len(laps) > len(planned) else
                           ", steps without a lap have no actual"))
    steps = [_actual(s, laps[i] if i < len(laps) else None) for i, s in enumerate(planned)]
    for j, lap in enumerate(laps[len(planned):], 1):
        steps.append(_actual({"name": f"Extra {j}", "kind": "easy", "band": None}, lap))
    return [s for s in steps if s["dur"]], warnings


def laps_as_steps(laps: list[dict]) -> list[dict]:
    """No plan: name laps from the FIT intensity field; active laps between rest laps are reps."""
    kinds = []
    has_rest = any(lap.get("intensity") in ("rest", "recovery") for lap in laps)
    for lap in laps:
        it = lap.get("intensity")
        if it in ("warmup", "cooldown"):
            kinds.append("easy")
        elif it in ("rest", "recovery"):
            kinds.append("jog")
        else:
            kinds.append("rep" if has_rest else "easy")
    out, n_rep, n_jog = [], 0, 0
    for lap, kind in zip(laps, kinds, strict=True):
        if lap.get("intensity") == "warmup":
            name = "Warm-up"
        elif lap.get("intensity") == "cooldown":
            name = "Cool-down"
        elif kind == "rep":
            n_rep += 1
            name = f"Rep {n_rep}"
        elif kind == "jog":
            n_jog += 1
            name = f"Jog {n_jog}"
        else:
            name = f"Lap {len(out) + 1}"
        out.append(_actual({"name": name, "kind": kind, "band": None}, lap))
    return out


def status_of(step: dict) -> int | None:
    """Seconds slower than the band (0 = in target or faster); None when not measurable."""
    if step.get("kind") != "rep" or not step.get("band") or step.get("pace") is None:
        return None
    return max(0, step["pace"] - step["band"][1])


# ----------------------------------------------------------------------------- zones

def intended_zone(step: dict, threshold_s: float | None) -> int:
    """Estimated HR zone index (0..4) a planned step aims at."""
    if step["kind"] == "jog":
        return 0
    if step["kind"] != "rep":
        return 1
    if step.get("band") and threshold_s:
        mid = sum(step["band"]) / 2 / threshold_s
        return 4 if mid <= 0.97 else 3 if mid <= 1.03 else 2 if mid <= 1.10 else 1
    return 3


def zones_block(steps: list[dict], actual_zone_s: list[float] | None, threshold_s: float | None,
                has_plan: bool) -> list[dict] | None:
    intended = [0.0] * 5
    if has_plan:
        for s in steps:
            if not s["name"].startswith("Extra"):
                intended[intended_zone(s, threshold_s)] += s["dur"] / 60
    if not actual_zone_s and not has_plan:
        return None
    return [{"z": ZONE_NAMES[i],
             "intended": round(intended[i], 1) if has_plan else None,
             "actual": round(actual_zone_s[i] / 60, 1) if actual_zone_s else None} for i in range(5)]


def zones_from_hr(hr: list[tuple[float, int]], bounds: list[int]) -> list[float] | None:
    """Seconds per zone from HR samples; ``bounds`` = upper limits of Z1..Z4 (bpm)."""
    if len(hr) < 2 or len(bounds) != 4:
        return None
    out = [0.0] * 5
    for (t, bpm), (t2, _) in zip(hr, hr[1:], strict=False):
        dt = min(t2 - t, 10)
        out[sum(bpm > b for b in bounds)] += dt
    return out


# ----------------------------------------------------------------------------- context

def _split_detail(detail: str) -> tuple[str, str]:
    m = re.search(r"(\d+(?:\.\d+)?\s?(?:ms|bpm|h|%|/100)?)", detail or "")
    if not m:
        return detail, ""
    rest = (detail[:m.start()] + detail[m.end():]).strip(" ,")
    return m.group(1), rest


def context_block(readiness: dict | None, actual: dict, session_date: str) -> list[dict]:
    out: list[dict] = []
    if readiness and str(readiness.get("date", ""))[:10] == session_date:
        out.append({"label": "Readiness", "value": str(readiness.get("level", "?")).capitalize(),
                    "level": readiness.get("level"), "sub": f"score {readiness.get('score')}"})
        labels = {"hrv": "HRV (night)", "sleep": "Sleep", "rhr": "Resting HR", "recovery": "Recovery"}
        for key, label in labels.items():
            sig = (readiness.get("signals") or {}).get(key) or {}
            if sig.get("score") is not None:
                value, sub = _split_detail(sig.get("detail", ""))
                out.append({"label": label, "value": value, "sub": sub})
    if actual.get("training_load") is not None:
        load = ((readiness or {}).get("signals") or {}).get("load") or {}
        out.append({"label": "Training load", "value": f"{actual['training_load']:g}",
                    "sub": (load.get("detail") or "").split(",")[0]})
    if actual.get("aerobic_te") is not None:
        sub = f"{actual['anaerobic_te']:g} anaerobic" if actual.get("anaerobic_te") is not None else ""
        out.append({"label": "Training effect", "value": f"{actual['aerobic_te']:g} aerobic", "sub": sub})
    return out


# ----------------------------------------------------------------------------- build

def week_of(plan: dict, session_id: str) -> tuple[dict, dict, int]:
    for i, week in enumerate(plan.get("weeks") or []):
        for s in week.get("sessions") or []:
            if s.get("id") == session_id:
                return week, s, i + 1
    raise SystemExit(f"session {session_id} not found in the plan")


def build_data(*, steps: list[dict], title: str, meta: str, session: dict | None = None,
               activity: dict | None = None, zones: list[dict] | None = None, context: list[dict] | None = None,
               threshold_s: float | None = None, planned: dict | None = None, mock: bool = False,
               warnings: list[str] | None = None, in_plan: bool = True) -> dict:
    session = session or {}
    activity = activity or {}
    planned = planned or {}
    actual = session.get("actual") or {}
    recap = session.get("recap") or {}
    reps = [s for s in steps if s["kind"] == "rep"]
    measured = [s for s in reps if status_of(s) is not None]
    hits = [s for s in measured if status_of(s) == 0]

    if measured:
        level = "ok" if len(hits) == len(measured) else "mostly" if len(hits) * 2 >= len(measured) else "off"
        label = {"ok": "On target", "mostly": "Mostly on target", "off": "Off target"}[level]
        bits = [f"{len(hits)} of {len(measured)} reps in target"]
    else:
        level, label, bits = "none", ("Done" if steps else "No lap data"), []
    if actual.get("compliance_pct"):
        bits.append(f"Compliance {actual['compliance_pct']} %")

    total_s = activity.get("duration_s") or sum(s["dur"] for s in steps)
    dist = activity.get("distance_km") or round(sum(s.get("dist") or 0 for s in steps), 2) or None
    tiles = [{"label": "Duration", "value": hms(total_s), "plan":
              f"planned {hms((planned.get('duration_min') or 0) * 60)}" if planned.get("duration_min") else "",
              "delta": _delta_time(total_s, (planned.get("duration_min") or 0) * 60)}]
    if dist:
        tiles.append({"label": "Distance", "value": f"{dist:.1f} km",
                      "plan": f"planned {planned['distance_km']:g} km" if planned.get("distance_km") else "",
                      "delta": f"{dist - planned['distance_km']:+.1f} km" if planned.get("distance_km") else ""})
    rep_paces = [(s["pace"], s["dur"]) for s in reps if s.get("pace")]
    if rep_paces:
        avg = sum(p * d for p, d in rep_paces) / sum(d for _, d in rep_paces)
        band = next((s["band"] for s in reps if s.get("band")), None)
        tile = {"label": "Avg rep pace", "value": f"{pace(avg)}/km", "plan": "", "delta": ""}
        if band:
            slow = max(0, round(avg) - band[1])
            tile.update(plan=f"target {pace(band[0])}–{pace(band[1])}", delta="in target" if not slow else f"+{slow} s",
                        good=not slow)
        tiles.append(tile)
    avg_hr = activity.get("avg_hr") or _weighted([(s.get("hr"), s["dur"]) for s in steps])
    if avg_hr:
        rep_hr = _weighted([(s.get("hr"), s["dur"]) for s in reps])
        hr_max = max((s.get("hrMax") or 0 for s in steps), default=0)
        tiles.append({"label": "Avg HR", "value": f"{round(avg_hr)} bpm",
                      "plan": f"reps {round(rep_hr)} bpm" if rep_hr else "",
                      "delta": f"max {hr_max}" if hr_max else ""})

    hr_reps = [s for s in reps if s.get("hr")]
    hr_sub = "Average HR per rep."
    if len(hr_reps) >= 2:
        drift = hr_reps[-1]["hr"] - hr_reps[0]["hr"]
        paces = [s["pace"] for s in hr_reps if s.get("pace")]
        similar = paces and max(paces) - min(paces) <= 10
        hr_sub = (f"Average HR per rep. {drift:+d} bpm from rep 1 to rep {len(hr_reps)}"
                  + (" at similar pace = cardiac drift." if similar and drift >= 5 else "."))

    band = next((s["band"] for s in reps if s.get("band")), None)
    feel = {k: recap.get(k) for k in ("rpe", "rpe_expected", "quote", "tags", "lang") if recap.get(k) is not None}
    if not feel.get("quote") and session.get("feedback"):
        feel["quote"] = session["feedback"]
    return {
        "title": title,
        "meta": meta,
        "in_plan": in_plan,
        "badge": "Mock data · draft for review" if mock else "",
        "status": {"level": level, "label": label},
        "status_bits": bits,
        "verdict": {"text": recap.get("verdict"), "lang": recap.get("lang")} if recap.get("verdict") else None,
        "tiles": tiles,
        "steps": [{k: s.get(k) for k in ("name", "kind", "band", "dur", "dist", "pace", "hr", "hrMax")} for s in steps],
        "rep_target_label": f"{pace(band[0])}–{pace(band[1])}/km" if band else None,
        "rep_sub": rep_sub(steps),
        "hr_sub": hr_sub,
        "pace_aria": _pace_aria(reps),
        "zones": zones,
        "zones_sub": ("Intended minutes are estimated from each step's target; actual from your heart rate."
                      if zones and zones[0].get("intended") is not None else "Minutes per heart-rate zone."),
        "feel": feel or None,
        "context": context or [],
        "impact": recap.get("impact") or [],
        "impact_lang": recap.get("lang"),
        "warnings": warnings or [],
        "footer": f"Generated by run-coach on {date.today():%d %b %Y} · local file, contains health data",
    }


def _weighted(pairs: list[tuple[float | None, float]]) -> float | None:
    pairs = [(v, w) for v, w in pairs if v and w]
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs) if pairs else None


def _delta_time(actual_s: float, planned_s: float) -> str:
    if not planned_s or not actual_s:
        return ""
    diff = round(actual_s - planned_s)
    sign = "+" if diff >= 0 else "−"
    return f"{sign}{hms(abs(diff)) if abs(diff) >= 60 else f'0:{abs(diff):02d}'}"


def _pace_aria(reps: list[dict]) -> str:
    st = [(i + 1, status_of(s)) for i, s in enumerate(reps)]
    st = [(n, g) for n, g in st if g is not None]
    if not st:
        return "Pace per step."
    ok = [n for n, g in st if g == 0]
    slow = [f"rep {n} +{g} s" for n, g in st if g]
    return f"Pace per step against planned targets. {len(ok)} of {len(st)} reps in target" + (
        f"; slow: {', '.join(slow)}." if slow else ".")


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(f"{data['title']} · Session Recap")).replace("__DATA__", payload)


# ----------------------------------------------------------------------------- provider fetch

def fetch_fit(activity: dict) -> bytes:
    import source as S

    if S.provider() == "garmin":
        import garmin

        return garmin.download_fit(activity["label_id"])
    import urllib.request

    import coros
    import parsers as P

    day = P.yyyymmdd(activity["date"])
    text = coros.call("queryActivityFitFileDownloadUrls", {
        "startDate": day, "endDate": day, "sportType": activity.get("sport_type"),
        "labelId": activity["label_id"], "limit": 1}, cache=False)
    m = re.search(r"https://\S+", text if isinstance(text, str) else json.dumps(text))
    if not m:
        raise SystemExit("COROS returned no FIT download URL for this activity")
    with urllib.request.urlopen(m.group(0).rstrip('",)'), timeout=60) as resp:  # noqa: S310 (COROS S3 URL)
        return resp.read()


def find_activity(day: str, label_id: str | None = None) -> dict | None:
    import source as S

    acts = S.activities(date.fromisoformat(day), date.fromisoformat(day))
    if label_id:
        return next((a for a in acts if a.get("label_id") == str(label_id)), None)
    runs = [a for a in acts if a.get("family") in ("run", "trail", "bike")]
    return max(runs, key=lambda a: a.get("duration_s") or 0) if runs else None


# ----------------------------------------------------------------------------- CLI

def threshold_from_profile() -> float | None:
    path = REPO_ROOT / "athlete" / "profile.yaml"
    if not path.exists():
        return None
    import yaml

    prof = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tp = ((prof.get("baseline") or {}).get("threshold_pace") or "")
    m = re.match(r"(\d+):(\d{2})", str(tp))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def hr_bounds_from_profile() -> list[int] | None:
    path = REPO_ROOT / "athlete" / "profile.yaml"
    if not path.exists():
        return None
    import yaml

    prof = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    b = (prof.get("baseline") or {}).get("hr_zone_bounds")
    return [int(x) for x in b] if isinstance(b, list) and len(b) == 4 else None


def cmd_build(args) -> int:
    import plan as PL

    threshold = threshold_from_profile()
    fit_bytes = Path(args.fit).read_bytes() if args.fit else None
    if args.plan:
        plan = PL.load_plan(args.plan)
        week, session, wn = week_of(plan, args.session)
        actual = session.get("actual") or {}
        day = actual.get("matched_date") or str(session["date"])[:10]
        activity = None
        if not fit_bytes or actual.get("label_id"):
            activity = find_activity(day, actual.get("label_id")) if actual.get("label_id") else None
        if not fit_bytes:
            if not activity:
                raise SystemExit(f"no activity matched to {args.session} yet: run `plan.py sync` first, or pass --fit")
            fit_bytes = fetch_fit(activity)
        fit = read_fit(fit_bytes)
        planned_steps = expand_course(session.get("course"), threshold)
        steps, warnings = align(planned_steps, fit["laps"])
        zone_s = (activity or {}).get("hr_zone_s") or zones_from_hr(fit["hr"], hr_bounds_from_profile() or [])
        weeks = plan["plan"].get("weeks")
        meta_bits = [datetime.fromisoformat(str(session["date"])[:10]).strftime("%a %d %b %Y"),
                     f"Week {wn} of {weeks}" if weeks else f"Week {wn}"]
        if week.get("phase"):
            meta_bits.append(f"{str(week['phase']).capitalize()} phase")
        if session.get("key"):
            meta_bits.append("Key session")
        data = build_data(steps=steps, title=session.get("title") or session["id"], meta=" · ".join(meta_bits),
                          session=session, activity=activity, planned=session.get("planned"),
                          zones=zones_block(steps, zone_s, threshold, bool(planned_steps)),
                          context=context_block(plan.get("readiness"), actual, day), threshold_s=threshold,
                          warnings=warnings)
        out = Path(args.out) if args.out else PL.plan_paths(args.plan)[0].parent / "recaps" / f"{day}-{session['id']}.html"
    else:
        if not args.date:
            raise SystemExit("give --plan PLAN --session ID, or --date YYYY-MM-DD")
        activity = None if args.fit else find_activity(args.date)
        if not fit_bytes:
            if not activity:
                raise SystemExit(f"no run or ride found on {args.date}")
            fit_bytes = fetch_fit(activity)
        fit = read_fit(fit_bytes)
        steps, warnings = align([], fit["laps"])
        zone_s = (activity or {}).get("hr_zone_s") or zones_from_hr(fit["hr"], hr_bounds_from_profile() or [])
        title = (activity or {}).get("name") or "Session"
        data = build_data(steps=steps, title=title, activity=activity,
                          meta=datetime.fromisoformat(args.date).strftime("%a %d %b %Y") + " · Not in a plan",
                          zones=zones_block(steps, zone_s, threshold, False), warnings=warnings,
                          in_plan=False)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "session"
        out = Path(args.out) if args.out else REPO_ROOT / "reports" / "recaps" / f"{args.date}-{slug}.html"

    if args.json:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data), encoding="utf-8")
    missing = [k for k, v in (("verdict", data["verdict"]), ("feel", data["feel"]), ("impact", data["impact"])) if not v]
    if not data["in_plan"]:
        missing = [k for k in missing if k == "feel"]
    print(json.dumps({"written": str(out), "steps": len(steps), "status": data["status"]["label"],
                      "status_bits": data["status_bits"], "coach_fields_missing": missing,
                      "warnings": data["warnings"]}, indent=1, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the HTML recap of one session")
    b.add_argument("--plan")
    b.add_argument("--session")
    b.add_argument("--date", help="without a plan: the day of the activity")
    b.add_argument("--fit", help="read laps from this FIT file instead of downloading it")
    b.add_argument("--out")
    b.add_argument("--json", action="store_true", help="print the page data instead of writing HTML")
    args = parser.parse_args(argv)
    if args.plan and not args.session:
        parser.error("--plan needs --session")
    return cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
