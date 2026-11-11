"""Data provider layer: the same normalized data from COROS (MCP) or Garmin (Personal API).

    provider()                  -> "coros" | "garmin"
    activities(start, end)      -> [{date, sport, family, label_id, duration_s, distance_km, avg_pace_s, avg_hr, ...}]
    hrv(start, end)             -> [{date, hrv, status, low, high, baseline}]
    resting_hr(days)            -> [{date, rhr}]
    sleep(days)                 -> [{date, score, sleep_min, deep_pct}]
    recovery()                  -> {recovery_pct, level, ...}
    load(days)                  -> [{date, comment, short_term, long_term, ratio}]
    fitness()                   -> {vo2max, running_level, threshold_pace, predictions}
    user()                      -> {height_cm, weight_kg, age}

Provider choice: $COACH_PROVIDER, else ``provider:`` in athlete/profile.yaml, else auto-detect (COROS helper
installed → coros; Garmin key present → garmin; default coros).
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import parsers as P
import readiness as R

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = REPO_ROOT / "athlete" / "profile.yaml"
PROVIDERS = ("coros", "garmin")
LABEL = {"coros": "COROS", "garmin": "Garmin"}


def provider() -> str:
    env = os.environ.get("COACH_PROVIDER", "").strip().lower()
    if env:
        if env not in PROVIDERS:
            raise SystemExit(f"COACH_PROVIDER must be one of {', '.join(PROVIDERS)}")
        return env
    if PROFILE_PATH.exists():
        import yaml

        prof = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
        if str(prof.get("provider", "")).lower() in PROVIDERS:
            return str(prof["provider"]).lower()
    if (REPO_ROOT / ".vendor" / "COROS-MCP").exists():
        return "coros"
    import garmin

    return "garmin" if garmin.key_available() else "coros"


def label() -> str:
    return LABEL[provider()]


def today() -> date:
    return date.today()


# ----------------------------------------------------------------------------- activities

def activities(start: date, end: date) -> list[dict]:
    if provider() == "garmin":
        return _garmin_activities(start, end)
    return _coros_activities(start, end)


def _coros_activities(start: date, end: date) -> list[dict]:
    """Fetch all activities in [start, end], splitting the range when the 100-record cap is hit."""
    import coros

    args = {"startDate": P.yyyymmdd(start), "endDate": P.yyyymmdd(end), "sportTypeCodes": [65535],
            "minDistanceKm": None, "maxDistanceKm": None, "minDurationMinutes": None,
            "maxDurationMinutes": None, "maxAveragePace": None, "locationKeyword": None, "limit": 100}
    text = coros.call("querySportRecords", args)
    acts = P.parse_sport_records(text if isinstance(text, str) else "")
    if len(acts) >= 100 and start < end:
        mid = start + (end - start) / 2
        return _coros_activities(start, mid) + _coros_activities(mid + timedelta(days=1), end)
    return acts


def _garmin_activities(start: date, end: date) -> list[dict]:
    import garmin
    import garmin_parsers as G

    rows: list[dict] = []
    page = 100
    while True:
        batch = garmin.call("search_activities", {"start": len(rows), "limit": page,
                                                  "start_date": G.iso(start), "end_date": G.iso(end)})
        batch = batch if isinstance(batch, list) else (batch or {}).get("results") or []
        rows += batch
        if len(batch) < page:
            break
    return G.parse_activities(rows)


# ----------------------------------------------------------------------------- health

def hrv(start: date, end: date) -> list[dict]:
    if provider() == "garmin":
        import garmin
        import garmin_parsers as G

        return G.parse_hrv(garmin.call("get_daily_hrv_summaries", {"start_date": G.iso(start),
                                                                    "end_date": G.iso(end)}))
    import coros

    return P.parse_sleep_hrv(coros.call("querySleepHrv", {
        "startDate": P.yyyymmdd(start), "endDate": P.yyyymmdd(end), "days": (end - start).days + 1}))


def resting_hr(days: int) -> list[dict]:
    if provider() == "garmin":
        import garmin
        import garmin_parsers as G

        t = today()
        return G.parse_resting_hr(garmin.call("get_daily_summaries", {
            "start_date": G.iso(t - timedelta(days=days - 1)), "end_date": G.iso(t)}))
    import coros

    return P.parse_resting_hr(coros.call("queryRestingHeartRate", {"days": days}))


def sleep(days: int) -> list[dict]:
    if provider() == "garmin":
        import garmin
        import garmin_parsers as G

        t = today()
        return G.parse_sleep(garmin.call("get_daily_sleep_summaries", {
            "start_date": G.iso(t - timedelta(days=days - 1)), "end_date": G.iso(t)}))
    import coros

    return P.parse_sleep_overview(coros.call("querySleepOverview", {"days": days}))


def recovery() -> dict:
    if provider() == "garmin":
        import garmin
        import garmin_parsers as G

        t = today()
        return G.parse_body_battery(garmin.call("get_daily_body_battery", {
            "start_date": G.iso(t - timedelta(days=1)), "end_date": G.iso(t)}), t)
    import coros

    return P.parse_recovery(coros.call("queryRecoveryStatus", {}))


# ----------------------------------------------------------------------------- load & fitness

def load(days: int, acts: list[dict] | None = None) -> list[dict]:
    """Training load rows. Garmin: computed from the last ``days`` + 28 days of activities (pass them to reuse)."""
    if provider() == "garmin":
        t = today()
        if acts is None:
            acts = activities(t - timedelta(days=days + 28), t)
        return R.load_from_activities(acts, t, days)
    import coros

    return P.parse_training_load(coros.call("queryTrainingLoadAssessment", {"days": days}))


def fitness(acts: list[dict] | None = None) -> dict:
    """Fitness snapshot. Garmin: estimated from the best effort of the last 8 weeks (pass them to reuse)."""
    if provider() == "garmin":
        if acts is None:
            t = today()
            acts = activities(t - timedelta(weeks=8), t)
        return R.estimate_fitness(acts)
    import coros

    return P.parse_fitness(coros.call("queryFitnessAssessmentOverview", {}))


def user() -> dict:
    if provider() == "garmin":
        import garmin
        import garmin_parsers as G

        t = today()
        return G.parse_user(garmin.call("get_user_profile_settings"),
                            garmin.call("get_weight_measurements", {"start_date": G.iso(t - timedelta(days=90)),
                                                                     "end_date": G.iso(t)}))
    import coros

    kv = P.parse_key_values(coros.call("queryUserInfo", {}))
    return {
        "height_cm": P._num((kv.get("Height") or "").split()[0] if kv.get("Height") else None),
        "weight_kg": P._num((kv.get("Weight") or "").split()[0] if kv.get("Weight") else None),
        "age": int(kv["Birthday"].split("Age:")[1].strip(" )")) if "Age:" in kv.get("Birthday", "") else None,
    }
