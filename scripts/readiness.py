"""Deterministic readiness scoring and pace zones.

The coach (LLM) must not invent thresholds: it reads the output of these
functions and applies the action table in
``.claude/skills/run-coach/references/decision-process.md``.

Signals are scored -2..+2. Rules (see docs/coaching-science.md for sources):

* HRV (COROS sleep HRV assessment vs its normal range)
    below range today and the previous day -> -2; below today only -> -1;
    in range -> 0 (+1 if the 3-day mean is at/above baseline); above range -> 0 + flag
* Resting HR vs mean of the previous 7 days
    >= +8 bpm -> -2; >= +5 bpm -> -1; <= mean -> +1; else 0
* Sleep (last night)
    < 6 h or score < 60 -> -2; < 7 h or score < 70 -> -1; >= 7.5 h and score >= 85 -> +1
* Recovery % (COROS recovery, or the day's peak Garmin Body Battery)
    < 20 -> -2; < 70 -> -1; >= 90 -> +1
* Load ratio (short-term / long-term: COROS values, or computed by ``load_from_activities`` for Garmin)
    >= 1.5 -> -2 ("Excessive"); >= 1.3 -> -1; else 0

Level: red if >= 2 of {hrv, rhr, sleep} are negative and at least one of them is -2,
or total <= -4; yellow if total <= -1, any physiological signal is negative, or any
signal is -2; else green.
Missing data lowers ``confidence``; it is never scored as bad.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

SIGNALS = ("hrv", "rhr", "sleep", "recovery", "load")


def score_hrv(hrv_rows: list[dict]) -> tuple[int | None, str]:
    if not hrv_rows:
        return None, "no HRV data"
    today = hrv_rows[-1]
    below = today["hrv"] < today["low"]
    if below:
        prev_below = len(hrv_rows) >= 2 and hrv_rows[-2]["hrv"] < hrv_rows[-2]["low"]
        if prev_below:
            return -2, f"HRV {today['hrv']} ms below normal range ({today['low']}-{today['high']}) 2 nights in a row"
        return -1, f"HRV {today['hrv']} ms below normal range ({today['low']}-{today['high']})"
    if today["hrv"] > today["high"]:
        return 0, f"HRV {today['hrv']} ms above normal range (flag: watch for saturation/illness)"
    last3 = [r["hrv"] for r in hrv_rows[-3:]]
    if mean(last3) >= today["baseline"]:
        return 1, f"HRV {today['hrv']} ms in range, 3-day mean {mean(last3):.0f} >= baseline {today['baseline']}"
    return 0, f"HRV {today['hrv']} ms in normal range"


def score_rhr(rhr_rows: list[dict]) -> tuple[int | None, str]:
    values = [r for r in rhr_rows if r.get("rhr")]
    if len(values) < 4:
        return None, "not enough resting HR data"
    today = values[-1]["rhr"]
    ref = mean(r["rhr"] for r in values[-8:-1])
    delta = today - ref
    if delta >= 8:
        return -2, f"resting HR {today} bpm, +{delta:.0f} vs 7-day mean"
    if delta >= 5:
        return -1, f"resting HR {today} bpm, +{delta:.0f} vs 7-day mean"
    if delta <= 0:
        return 1, f"resting HR {today} bpm, at/below 7-day mean ({ref:.0f})"
    return 0, f"resting HR {today} bpm (+{delta:.0f} vs 7-day mean)"


def score_sleep(sleep_rows: list[dict]) -> tuple[int | None, str]:
    rows = [r for r in sleep_rows if r.get("sleep_min")]
    if not rows:
        return None, "no sleep data"
    last = rows[-1]
    hours = last["sleep_min"] / 60
    score = last.get("score") or 0
    desc = f"sleep {hours:.1f} h, score {score or '?'}"
    if hours < 6 or (score and score < 60):
        return -2, desc
    if hours < 7 or (score and score < 70):
        return -1, desc
    if hours >= 7.5 and score >= 85:
        return 1, desc
    return 0, desc


def score_recovery(recovery: dict | None) -> tuple[int | None, str]:
    if not recovery or recovery.get("recovery_pct") is None:
        return None, "no recovery data"
    pct = recovery["recovery_pct"]
    level = recovery.get("level") or "?"
    desc = (f"Body Battery {pct:.0f}/100" if level == "Body Battery"
            else f"COROS recovery {pct:.0f}% ({level})")
    if pct < 20:
        return -2, desc
    if pct < 70:
        return -1, desc
    if pct >= 90:
        return 1, desc
    return 0, desc


def score_load(load_rows: list[dict]) -> tuple[int | None, str]:
    if not load_rows:
        return None, "no training load data"
    last = load_rows[-1]
    desc = f"load ratio {last['ratio']:.2f} ({last['comment']}), short {last['short_term']} / long {last['long_term']}"
    if last["ratio"] >= 1.5:
        return -2, desc
    if last["ratio"] >= 1.3:
        return -1, desc
    return 0, desc


def compute(hrv: list[dict], rhr: list[dict], sleep: list[dict], recovery: dict | None,
            load: list[dict]) -> dict:
    """Combine all signals into a readiness snapshot (plain dict, YAML-friendly)."""
    scored = {
        "hrv": score_hrv(hrv),
        "rhr": score_rhr(rhr),
        "sleep": score_sleep(sleep),
        "recovery": score_recovery(recovery),
        "load": score_load(load),
    }
    available = {k: v for k, v in scored.items() if v[0] is not None}
    total = sum(v[0] for v in available.values())
    physio = [available[k][0] for k in ("hrv", "rhr", "sleep") if k in available]
    physio_neg = [v for v in physio if v < 0]
    if (len(physio_neg) >= 2 and min(physio_neg) == -2) or total <= -4:
        level = "red"
    elif total <= -1 or physio_neg or any(v[0] == -2 for v in available.values()):
        level = "yellow"
    else:
        level = "green"
    return {
        "level": level,
        "score": total,
        "confidence": round(len(available) / len(SIGNALS), 2),
        "signals": {k: {"score": v[0], "detail": v[1]} for k, v in scored.items()},
    }


# Pace zones relative to the COROS threshold pace (seconds per km; larger = slower).
# Ranges approximate Daniels VDOT relationships: see docs/coaching-science.md.
ZONE_FACTORS = {
    "recovery": (1.32, 1.45),
    "easy": (1.18, 1.32),
    "marathon": (1.05, 1.08),
    "threshold": (0.98, 1.02),
    "interval": (0.93, 0.96),
    "repetition": (0.86, 0.90),
}


def pace_zones(threshold_pace_s: int) -> dict[str, tuple[int, int]]:
    """Return {zone: (fast_s_per_km, slow_s_per_km)} from a threshold pace in s/km."""
    return {z: (round(threshold_pace_s * lo), round(threshold_pace_s * hi)) for z, (lo, hi) in ZONE_FACTORS.items()}


# ----------------------------------------------------------------------------- computed metrics (Garmin)
# The Garmin Personal API exposes no training load, VO2max or threshold pace. These functions compute
# transparent substitutes from the activity list. Sources in docs/coaching-science.md.

def trimp(activity: dict) -> float | None:
    """Edwards TRIMP: sum over HR zones 1-5 of minutes in zone x zone number (Edwards 1993)."""
    zones = activity.get("hr_zone_s")
    if not zones:
        return None
    return sum(secs / 60 * (i + 1) for i, secs in enumerate(zones))


def load_from_activities(activities: list[dict], until: date, days: int = 14) -> list[dict]:
    """Daily acute:chronic load rows in the shape of COROS ``queryTrainingLoadAssessment`` (oldest first).

    short_term = TRIMP of the last 7 days, long_term = TRIMP of the last 28 days / 4 (weekly mean),
    ratio = short / long (ACWR, Gabbett 2016). Activities without HR zones count with the median TRIMP
    per minute of the others, so a forgotten HR strap does not look like rest. Needs >= 28 days of history.
    """
    per_min = sorted(t / (a["duration_s"] / 60) for a in activities
                     if (t := trimp(a)) and a.get("duration_s"))
    fallback = per_min[len(per_min) // 2] if per_min else 0
    daily: dict[str, float] = {}
    for a in activities:
        t = trimp(a)
        if t is None:
            t = (a.get("duration_s") or 0) / 60 * fallback
        daily[a["date"]] = daily.get(a["date"], 0) + t

    def window(end: date, n: int) -> float:
        return sum(daily.get((end - timedelta(days=i)).isoformat(), 0) for i in range(n))

    rows = []
    for i in range(days - 1, -1, -1):
        d = until - timedelta(days=i)
        short, long_ = window(d, 7), window(d, 28) / 4
        if long_ <= 0:
            continue
        ratio = short / long_
        # same vocabulary as COROS so the decision tables apply unchanged
        comment = ("Excessive" if ratio >= 1.5 else "Optimized" if ratio >= 1.0 else
                   "Maintaining" if ratio >= 0.8 else "Performance" if ratio >= 0.5 else "Low")
        rows.append({"date": d.isoformat(), "comment": comment, "short_term": round(short),
                     "long_term": round(long_), "ratio": round(ratio, 2)})
    return rows


RIEGEL_EXPONENT = 1.06
RACE_DISTANCES = {"5k": 5000, "10k": 10000, "half": 21097.5, "marathon": 42195}


def riegel(time_s: float, dist_m: float, target_m: float) -> float:
    """Riegel (1981): T2 = T1 x (D2 / D1) ^ 1.06."""
    return time_s * (target_m / dist_m) ** RIEGEL_EXPONENT


def _hms(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{rem // 60}:{rem % 60:02d}"


def estimate_fitness(activities: list[dict]) -> dict:
    """Race predictions and threshold pace from the best recent effort (shape of ``parsers.parse_fitness``).

    Picks, over the given activities, the fastest split (5k, 10k, half, marathon) with the best Riegel-equivalent
    10k time. Threshold pace = pace of the predicted ~60-minute race (Daniels: threshold ~ 1-hour race pace).
    Efforts under 5 km are ignored (too anaerobic to extrapolate). ``vo2max`` stays None: no Garmin source.
    """
    from garmin_parsers import SPLITS

    best = None
    for a in activities:
        for key, secs in (a.get("fastest_splits") or {}).items():
            if key not in RACE_DISTANCES:
                continue
            eq10k = riegel(secs, SPLITS[key][1], 10000)
            if best is None or eq10k < best[0]:
                best = (eq10k, key, secs, a["date"])
    out: dict = {"vo2max": None, "running_level": None, "threshold_pace": None, "predictions": {},
                 "source": None}
    if not best:
        return out
    _, key, secs, day = best
    dist = SPLITS[key][1]
    out["predictions"] = {k: _hms(riegel(secs, dist, m)) for k, m in RACE_DISTANCES.items()}
    # distance covered in 60 min: solve T(D) = 3600 with Riegel
    d60 = dist * (3600 / secs) ** (1 / RIEGEL_EXPONENT)
    pace = round(3600 / (d60 / 1000))
    out["threshold_pace"] = f"{pace // 60}:{pace % 60:02d}"
    out["source"] = f"estimated from best {key} effort on {day} (Riegel)"
    return out
