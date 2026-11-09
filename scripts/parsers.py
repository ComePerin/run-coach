"""Parse the human-readable text returned by COROS MCP tools into Python data.

COROS MCP tools answer with text formatted for LLMs (only lap tools return
JSON). These parsers are deliberately tolerant: unknown lines are ignored and
missing values become ``None``. Fixtures in ``tests/fixtures`` pin the formats.
"""

from __future__ import annotations

import re
from datetime import date, datetime

RUN_CODES = {100, 101, 103}
TRAIL_CODES = {102}
HIKE_CODES = {104, 105, 106}
BIKE_CODES = {200, 201, 202, 203, 204, 205, 299}
SWIM_CODES = {300, 301}


def sport_family(sport_type: int | None) -> str:
    """Map a COROS activity sport type code to a coarse family used for matching."""
    if sport_type in RUN_CODES:
        return "run"
    if sport_type in TRAIL_CODES:
        return "trail"
    if sport_type in HIKE_CODES:
        return "hike"
    if sport_type in BIKE_CODES:
        return "bike"
    if sport_type in SWIM_CODES:
        return "swim"
    return "other"


def hms_to_seconds(value: str) -> int:
    """'1:02:03' -> 3723, '42:18' -> 2538."""
    parts = [int(p) for p in value.strip().split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def pace_to_seconds(value: str) -> int:
    """'4:05' or '4:05 /km' -> 245."""
    return hms_to_seconds(value.replace("/km", "").strip())


def seconds_to_pace(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.replace(",", "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def parse_key_values(text: str) -> dict[str, str]:
    """Generic 'Key: value' extractor for summary tools (fitness, detail, recovery, user)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line or line.strip().startswith(("=", "-")):
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key and val and key not in out:
            out[key] = val
    return out


def parse_sport_records(text: str) -> list[dict]:
    """Parse ``querySportRecords`` output into a list of activities."""
    activities = []
    for block in re.split(r"\n\s*\n(?=\d+\. )", text):
        head = re.match(r"\s*(\d+)\. (.+?) — (\d{4}-\d{2}-\d{2})", block)
        if not head:
            continue

        def grab(pattern: str, blk: str = block) -> str | None:
            m = re.search(pattern, blk)
            return m.group(1) if m else None

        duration = grab(r"Duration: ([\d:]+)")
        pace = grab(r"Average Pace: ([\d:]+)")
        sport_type = grab(r"SportType: (\d+)")
        start_ts = grab(r"startTimestamp=(\d+)")
        end_ts = grab(r"endTimestamp=(\d+)")
        activities.append(
            {
                "sport": head.group(2).strip(),
                "date": head.group(3),
                "name": grab(r"Location: (.+)"),
                "start_ts": int(start_ts) if start_ts else None,
                "end_ts": int(end_ts) if end_ts else None,
                "duration_s": hms_to_seconds(duration) if duration else None,
                "distance_km": _num(grab(r"Distance: ([\d.]+) km")),
                "avg_pace_s": pace_to_seconds(pace) if pace else None,
                "avg_speed_kmh": _num(grab(r"Average Speed: ([\d.]+) km/h")),
                "avg_hr": int(grab(r"Avg HR: (\d+)")) if grab(r"Avg HR: (\d+)") else None,
                "calories": _num(grab(r"Calories: ([\d,]+) kcal")),
                "label_id": grab(r"LabelId: (\d+)"),
                "sport_type": int(sport_type) if sport_type else None,
            }
        )
    return activities


def parse_fitness(text: str) -> dict:
    """Parse ``queryFitnessAssessmentOverview``."""
    kv = parse_key_values(text)
    out: dict = {
        "vo2max": _num(kv.get("VO2max")),
        "running_level": _num(kv.get("Running Level")),
        "threshold_pace": kv.get("Threshold Pace", "").replace("/km", "").strip() or None,
        "predictions": {},
    }
    for label, key in (("5k", "5 km Prediction"), ("10k", "10 km Prediction"),
                       ("half", "Half Marathon Prediction"), ("marathon", "Marathon Prediction")):
        if kv.get(key):
            out["predictions"][label] = kv[key]
    return out


def parse_training_load(text: str) -> list[dict]:
    """Parse ``queryTrainingLoadAssessment`` (most recent first in the source; returned oldest first)."""
    rows = []
    pattern = (r"(\d{4}-\d{2}-\d{2})\s*\nComment: ([^\n]+)\nShort-Term Load: (\d+)\n"
               r"Long-Term Load: (\d+)\nLoad Ratio: ([\d.]+)")
    for m in re.finditer(pattern, text):
        rows.append({"date": m.group(1), "comment": m.group(2).strip(), "short_term": int(m.group(3)),
                     "long_term": int(m.group(4)), "ratio": float(m.group(5))})
    return sorted(rows, key=lambda r: r["date"])


def parse_sleep_hrv(text: str) -> list[dict]:
    """Parse the official assessment section of ``querySleepHrv`` (oldest first)."""
    rows = []
    pattern = (r"(\d{4}-\d{2}-\d{2}):\s*\n\s*HRV Avg: (\d+) ms — ([^\n]+)\n\s*Normal Range: (\d+) - (\d+) ms"
               r"\n\s*Baseline: (\d+)")
    for m in re.finditer(pattern, text):
        rows.append({"date": m.group(1), "hrv": int(m.group(2)), "status": m.group(3).strip(),
                     "low": int(m.group(4)), "high": int(m.group(5)), "baseline": int(m.group(6))})
    return sorted(rows, key=lambda r: r["date"])


def parse_resting_hr(text: str) -> list[dict]:
    """Parse ``queryRestingHeartRate`` (oldest first, ``None`` for days without data)."""
    rows = []
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2}): (?:(\d+) bpm|No data)", text):
        rows.append({"date": m.group(1), "rhr": int(m.group(2)) if m.group(2) else None})
    return sorted(rows, key=lambda r: r["date"])


def parse_sleep_overview(text: str) -> list[dict]:
    """Parse ``querySleepOverview`` (oldest first). Dates are wake-up days."""
    rows = []
    for block in re.split(r"\n(?=\d{4}-\d{2}-\d{2}\s*\n)", text):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\s*\nSleep Score: (\d+)", block.strip())
        if not m:
            continue
        sleep = re.search(r"Main Sleep \(asleep\): (?:(\d+)h )?(\d+)min", block)
        deep = re.search(r"Deep Sleep Ratio: (\d+)%", block)
        score = int(m.group(2))
        rows.append({
            "date": m.group(1),
            "score": score or None,
            "sleep_min": (int(sleep.group(1) or 0) * 60 + int(sleep.group(2))) if sleep else None,
            "deep_pct": int(deep.group(1)) if deep else None,
        })
    return sorted(rows, key=lambda r: r["date"])


def parse_recovery(text: str) -> dict:
    kv = parse_key_values(text)
    pct = kv.get("Recovery", "").rstrip("%").strip()
    return {"recovery_pct": _num(pct), "level": kv.get("Level"), "full_recovery": kv.get("Estimated Full Recovery")}


def parse_activity_detail(text: str) -> dict:
    """Parse ``getActivityDetail`` into a dict with a few normalised numeric fields."""
    kv = parse_key_values(text)
    out: dict = {"raw": kv}
    if "Training Load" in kv:
        out["training_load"] = _num(kv["Training Load"])
    if "Average Heart Rate" in kv:
        out["avg_hr"] = _num(kv["Average Heart Rate"].split()[0])
    if "Average Pace" in kv:
        out["avg_pace"] = kv["Average Pace"].replace("/km", "").strip()
    for key, name in (("Aerobic TE", "aerobic_te"), ("Anaerobic TE", "anaerobic_te")):
        if key in kv:
            out[name] = _num(kv[key])
    for key, name in (("Training Focus", "training_focus"), ("Perceived Effort", "rpe_label"),
                      ("Performance", "performance")):
        if key in kv:
            out[name] = kv[key]
    return out


def parse_created_id(text: str) -> str | None:
    """Extract ``idInPlan`` from createScheduledWorkout / updateScheduledWorkout output."""
    m = re.search(r"idInPlan: (\d+)", text)
    return m.group(1) if m else None


def parse_schedule(text: str) -> list[dict]:
    """Parse ``queryTrainingSchedule`` into entries (date, name, source, id_in_plan)."""
    entries = []
    for block in re.split(r"\n\s*\n", text):
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})\n([^\n]+)", block)
        if not m:
            continue
        idm = re.search(r"idInPlan: (\d+)", block)
        entries.append({
            "date": m.group(1),
            "name": m.group(2).strip(),
            "standalone": "Standalone" in block,
            "from_plan": "Plan ID" in block,
            "id_in_plan": idm.group(1) if idm else None,
        })
    return entries


def yyyymmdd(d: date | datetime | str) -> str:
    if isinstance(d, str):
        return d.replace("-", "")
    return d.strftime("%Y%m%d")
