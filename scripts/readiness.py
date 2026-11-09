"""Deterministic readiness scoring and pace zones.

The coach (LLM) must not invent thresholds: it reads the output of these
functions and applies the action table in
``.claude/skills/coros-coach/references/decision-process.md``.

Signals are scored -2..+2. Rules (see docs/coaching-science.md for sources):

* HRV (COROS sleep HRV assessment vs its normal range)
    below range today and the previous day -> -2; below today only -> -1;
    in range -> 0 (+1 if the 3-day mean is at/above baseline); above range -> 0 + flag
* Resting HR vs mean of the previous 7 days
    >= +8 bpm -> -2; >= +5 bpm -> -1; <= mean -> +1; else 0
* Sleep (last night)
    < 6 h or score < 60 -> -2; < 7 h or score < 70 -> -1; >= 7.5 h and score >= 85 -> +1
* COROS recovery %
    < 20 -> -2; < 70 -> -1; >= 90 -> +1
* COROS load ratio (short-term / long-term)
    >= 1.5 -> -2 ("Excessive"); >= 1.3 -> -1; else 0

Level: red if >= 2 of {hrv, rhr, sleep} are negative and at least one of them is -2,
or total <= -4; yellow if total <= -1, any physiological signal is negative, or any
signal is -2; else green.
Missing data lowers ``confidence``; it is never scored as bad.
"""

from __future__ import annotations

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
    desc = f"COROS recovery {pct:.0f}% ({recovery.get('level') or '?'})"
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
