"""Turn Garmin Personal API JSON into the same Python shapes as ``parsers.py`` produces for COROS.

The rest of the engine (``readiness.py``, ``plan.match_activities``, ``report.py``) only sees these normalized
dicts, so it does not care which watch brand the data came from. Parsers are tolerant: unknown or missing fields
become ``None``. Fixtures in ``tests/fixtures/garmin_*.json`` pin the formats (values are fictional).
"""

from __future__ import annotations

from datetime import date, datetime

RUN_KEYS = {"running", "street_running", "treadmill_running", "track_running", "indoor_running", "virtual_run",
            "obstacle_run"}
TRAIL_KEYS = {"trail_running", "ultra_run"}
HIKE_KEYS = {"hiking", "mountaineering"}
SPLITS = {"5k": ("fastestSplit_5000", 5000), "10k": ("fastestSplit_10000", 10000),
          "half": ("fastestSplit_21098", 21097.5), "marathon": ("fastestSplit_42195", 42195),
          "mile": ("fastestSplit_1609", 1609.34), "1k": ("fastestSplit_1000", 1000)}


def family(type_key: str | None) -> str:
    """Map a Garmin ``activityType.typeKey`` to the coarse family used for matching."""
    key = (type_key or "").lower()
    if key in TRAIL_KEYS:
        return "trail"
    if key in RUN_KEYS or key.endswith("_running"):
        return "run"
    if key in HIKE_KEYS:
        return "hike"
    if "cycling" in key or "biking" in key or key in ("virtual_ride", "e_bike_fitness", "e_bike_mountain"):
        return "bike"
    if "swimming" in key:
        return "swim"
    return "other"


def _f(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def parse_activities(rows: list[dict] | None) -> list[dict]:
    """``search_activities`` results → activity dicts (oldest first)."""
    out = []
    for a in rows or []:
        if a.get("activityId") is None or not a.get("startTimeLocal"):
            continue
        type_key = (a.get("activityType") or {}).get("typeKey")
        fam = family(type_key)
        speed = _f(a.get("averageSpeed"))
        dist = _f(a.get("distance"))
        hr = _f(a.get("averageHR"))
        zones = [_f(a.get(f"hrTimeInZone_{i}")) for i in range(1, 6)]
        splits = {k: round(a[f]) for k, (f, _) in SPLITS.items() if _f(a.get(f))}
        out.append({
            "sport": (type_key or "other").replace("_", " ").title(),
            "family": fam,
            "date": str(a["startTimeLocal"])[:10],
            "name": a.get("activityName"),
            "start_ts": int(a["beginTimestamp"] // 1000) if a.get("beginTimestamp") else None,
            "duration_s": round(_f(a.get("duration")) or 0) or None,
            "distance_km": round(dist / 1000, 2) if dist else None,
            "avg_pace_s": round(1000 / speed) if speed and fam in ("run", "trail", "hike") else None,
            "avg_speed_kmh": round(speed * 3.6, 1) if speed else None,
            "avg_hr": round(hr) if hr else None,
            "calories": _f(a.get("calories")),
            "label_id": str(a["activityId"]),
            "sport_type": None,
            "type_key": type_key,
            "aerobic_te": _f(a.get("aerobicTrainingEffect")),
            "hr_zone_s": [round(z or 0) for z in zones] if any(zones) else None,
            "fastest_splits": splits or None,
        })
    return sorted(out, key=lambda r: (r["date"], r["start_ts"] or 0))


def parse_hrv(payload: dict | None) -> list[dict]:
    """``get_daily_hrv_summaries`` → rows {date, hrv, status, low, high, baseline} (oldest first)."""
    rows = []
    for s in (payload or {}).get("hrvSummaries") or []:
        base = s.get("baseline") or {}
        hrv, low, high = _f(s.get("lastNightAvg")), _f(base.get("balancedLow")), _f(base.get("balancedUpper"))
        if hrv is None or low is None or high is None:
            continue
        rows.append({"date": s.get("calendarDate"), "hrv": round(hrv), "status": str(s.get("status") or "").title(),
                     "low": round(low), "high": round(high),
                     "baseline": round(_f(s.get("weeklyAvg")) or (low + high) / 2)})
    return sorted(rows, key=lambda r: r["date"] or "")


def parse_resting_hr(payload: dict | None) -> list[dict]:
    """``get_daily_summaries`` → rows {date, rhr} (oldest first, ``None`` when not measured)."""
    rows = []
    for d in (payload or {}).get("data") or []:
        rhr = _f((d.get("heartRate") or {}).get("restingValue"))
        rows.append({"date": d.get("calendarDate"), "rhr": round(rhr) if rhr else None})
    return sorted(rows, key=lambda r: r["date"] or "")


def parse_sleep(rows: list[dict] | None) -> list[dict]:
    """``get_daily_sleep_summaries`` → rows {date, score, sleep_min, deep_pct} (wake-up day, oldest first)."""
    out = []
    for s in rows or []:
        secs = _f(s.get("sleepTimeSeconds"))
        if not secs:
            continue
        score = _f((((s.get("sleepScores") or {}).get("overall")) or {}).get("value"))
        deep = _f(s.get("deepSleepSeconds"))
        out.append({"date": s.get("calendarDate"), "score": round(score) if score else None,
                    "sleep_min": round(secs / 60), "deep_pct": round(deep / secs * 100) if deep else None})
    return sorted(out, key=lambda r: r["date"] or "")


def parse_body_battery(rows: list[dict] | None, day: date | str | None = None) -> dict:
    """``get_daily_body_battery`` → the ``recovery`` dict used by readiness (peak Body Battery of the day).

    The day's peak is normally the wake-up value, i.e. how recharged the athlete is.
    """
    day_s = str(day) if day else None
    reports = [r for r in rows or [] if not day_s or r.get("date") == day_s] or list(rows or [])
    for r in sorted(reports, key=lambda r: r.get("date") or "", reverse=True):
        values = [_f(v[1]) for v in r.get("bodyBatteryValuesArray") or [] if isinstance(v, list) and len(v) > 1]
        values = [v for v in values if v is not None]
        if values:
            return {"recovery_pct": max(values), "level": "Body Battery", "full_recovery": None,
                    "date": r.get("date")}
    return {"recovery_pct": None, "level": "Body Battery", "full_recovery": None}


def parse_user(profile: dict | None, weights: dict | None = None) -> dict:
    """Profile settings (+ weight) → {height_cm, weight_kg, age} (the Personal API exposes no birthday)."""
    weight = None
    for w in reversed((weights or {}).get("dailyWeightSummaries") or []):
        latest = (w.get("latestWeight") or {}).get("weight") or w.get("weight")
        if latest:
            weight = round(_f(latest) / 1000, 1)  # grams
            break
    return {"height_cm": None, "weight_kg": weight, "age": None,
            "units": (profile or {}).get("measurementSystem")}


def iso(d: date | datetime | str) -> str:
    return d if isinstance(d, str) else d.strftime("%Y-%m-%d")
