#!/usr/bin/env python3
"""Put planned workouts into Garmin Connect through intervals.icu (official Garmin partner).

Garmin's Personal API is read-only and Garmin Connect cannot import workout files. intervals.icu can: when the
athlete links Garmin in https://intervals.icu/settings and ticks "Upload planned workouts", every workout on the
intervals.icu calendar for the next ~7 days is pushed to the Garmin Connect calendar (website + app), then to the
watch. This module creates those workouts through the documented intervals.icu API, written in intervals.icu's own
workout text (generated from the course JSON). After each write it downloads the FIT file intervals.icu builds for
Garmin and compares it step by step with the course.

API key (never printed): $INTERVALS_API_KEY, else ~/.config/intervals/api-key (scripts/setup.sh --intervals).
Athlete: $INTERVALS_ATHLETE_ID, else ~/.config/intervals/athlete-id, else "0" (= the key's own athlete).

Usage:
    python scripts/intervals.py status
    python scripts/intervals.py day YYYY-MM-DD          # planned workouts that day, with Garmin upload status
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://intervals.icu/api/v1"
CONFIG_DIR = Path("~/.config/intervals").expanduser()
KEY_FILE = CONFIG_DIR / "api-key"
ATHLETE_FILE = CONFIG_DIR / "athlete-id"
SETTINGS_PAGE = "https://intervals.icu/settings"
EVENT_TYPE = {1: "Run", 2: "Ride", 5: "TrailRun"}
USER_AGENT = "run-coach (+https://github.com/Z3ZEL/run-coach)"


class IntervalsError(RuntimeError):
    """Missing/rejected key or failed request."""


def _read(env: str, path: Path) -> str | None:
    value = os.environ.get(env, "").strip()
    if value:
        return value
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or None
    return None


def configured() -> bool:
    """True when an intervals.icu API key is available (not validated)."""
    return _read("INTERVALS_API_KEY", KEY_FILE) is not None


def athlete_id() -> str:
    return _read("INTERVALS_ATHLETE_ID", ATHLETE_FILE) or "0"


def _request(method: str, path: str, body: Any = None, params: dict | None = None, raw: bool = False) -> Any:
    key = _read("INTERVALS_API_KEY", KEY_FILE)
    if not key:
        raise IntervalsError(f"no intervals.icu API key. Create one in {SETTINGS_PAGE} (Developer Settings) and "
                             "run scripts/setup.sh --intervals (or set INTERVALS_API_KEY).")
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + "&".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in params.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"API_KEY:{key}".encode()).decode())
    req.add_header("Accept", "application/json")
    # intervals.icu answers 403 to urllib's default "Python-urllib/x.y" user agent
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code in (401, 403):
            raise IntervalsError(f"intervals.icu rejected the API key (HTTP {exc.code}). Check it in "
                                 f"{SETTINGS_PAGE}.") from exc
        raise IntervalsError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise IntervalsError(f"cannot reach intervals.icu: {exc.reason}") from exc
    if raw:
        return content
    return json.loads(content) if content else None


# ----------------------------------------------------------------------------- workout text

# intervals.icu's own workout syntax (https://forum.intervals.icu/t/workout-builder-syntax-quick-guide/123701).
# Traps found by testing against the live API: "400m" means 400 MINUTES (distances must be written in km), digits
# in a step's cue text are parsed as extra duration, absolute bpm is not supported (use % of max HR), and pace
# targets are dropped from the Garmin/FIT export when the athlete has no threshold pace for the sport.
CUE = {1: "Warm-up", 2: "Run", 3: "Recover", 4: "Cool-down"}
OPEN_ESTIMATE = {1: 600, 4: 600}  # seconds shown for lap-button steps (warm-up / cool-down), else 300


def _duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return "".join(f"{v}{u}" for v, u in ((h, "h"), (m, "m"), (s, "s")) if v) or "0s"


def _pace(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _step_line(sec: dict, sport_type: int, max_hr: float | None) -> str:
    kind = sec.get("sectionType", 2)
    cue = "Ride" if kind == 2 and sport_type == 2 else CUE.get(kind, "Step")
    tt, tv = sec.get("targetType"), sec.get("targetValue")
    if tt == 1:
        length = f"{tv / 1000:g}km"  # never "m": that is minutes in intervals.icu
    elif tt == 2:
        length = _duration(tv)
    else:
        length = f"{_duration(OPEN_ESTIMATE.get(kind, 300))} Press lap"
    it, zone = sec.get("intensityType"), sec.get("sectionIntensity")
    lo, hi = sec.get("intensityValueStart"), sec.get("intensityValueEnd")
    target = ""
    if it == 1:
        if zone:
            target = f"Z{zone} HR"
        else:
            if not max_hr:
                raise IntervalsError("heart-rate targets need a max HR in the intervals.icu sport settings")
            target = f"{lo / max_hr * 100:.1f}-{hi / max_hr * 100:.1f}% HR"
    elif it == 2:
        fast, slow = min(lo, hi), max(lo, hi)
        if fast == slow:  # same ±5 s/km window as the FIT export
            fast, slow = fast - 5, slow + 5
        target = f"{_pace(fast)}-{_pace(slow)}/km Pace"
    elif it == 4:
        if zone:
            raise IntervalsError("power zones are not supported for intervals.icu yet; use watts")
        target = f"{lo}-{hi}w"
    return f"- {cue} {length} {target}".rstrip()


def course_to_text(course: dict, max_hr: float | None = None) -> str:
    """Course JSON → intervals.icu workout text (the coaching description first, as a note)."""
    sport_type = course.get("sportType", 1)
    lines = []
    note = " ".join(str(course.get("courseDescription", "")).split())
    if note:
        lines += [note.lstrip("-"), ""]
    for sec in course.get("sections") or []:
        if sec.get("intervalGroup"):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"{int(sec.get('repeats', 1))}x")
            lines += [_step_line(sub, sport_type, max_hr) for sub in sec.get("sets") or []]
            lines.append("")
        else:
            lines.append(_step_line(sec, sport_type, max_hr))
    return "\n".join(lines).strip() + "\n"


def needs(course: dict) -> set[str]:
    """Athlete settings the course's targets depend on: {"threshold_pace", "max_hr"}."""
    out = set()
    for sec in course.get("sections") or []:
        for st in (sec.get("sets") or []) if sec.get("intervalGroup") else [sec]:
            if st.get("intensityType") == 2:
                out.add("threshold_pace")
            if st.get("intensityType") == 1 and not st.get("sectionIntensity"):
                out.add("max_hr")
    return out


def sport_settings(course: dict) -> dict:
    return _request("GET", f"/athlete/{athlete_id()}/sport-settings/{EVENT_TYPE.get(course.get('sportType', 1), 'Run')}") or {}


def preflight(course: dict, settings: dict) -> list[str]:
    """What is missing in the intervals.icu settings for the targets of this course to reach Garmin."""
    sport = EVENT_TYPE.get(course.get("sportType", 1), "Run")
    missing = []
    if "threshold_pace" in needs(course) and not settings.get("threshold_pace"):
        missing.append(f"set a threshold pace for {sport} in {SETTINGS_PAGE} (without it intervals.icu drops pace "
                       "targets when it sends the workout to Garmin)")
    if "max_hr" in needs(course) and not settings.get("max_hr"):
        missing.append(f"set a max HR for {sport} in {SETTINGS_PAGE}")
    return missing


# ----------------------------------------------------------------------------- events

def event_payload(day: str, course: dict, max_hr: float | None = None, external_id: str | None = None) -> dict:
    """One planned workout for ``POST /events/bulk``, in intervals.icu's native workout text."""
    event = {
        "category": "WORKOUT",
        "start_date_local": f"{day}T00:00:00",
        "type": EVENT_TYPE.get(course.get("sportType", 1), "Run"),
        "name": str(course.get("courseName", "Workout"))[:100],
        "description": course_to_text(course, max_hr),
    }
    if external_id:
        event["external_id"] = external_id
    return event


def download_fit(event_id: int | str) -> bytes:
    """The FIT file intervals.icu builds for an event (what it sends towards Garmin)."""
    return _request("GET", f"/athlete/{athlete_id()}/events/{event_id}/download.fit", raw=True)


def create(events: list[dict]) -> list[dict]:
    return _request("POST", f"/athlete/{athlete_id()}/events/bulk", events) or []


def update(event_id: int | str, event: dict) -> dict:
    return _request("PUT", f"/athlete/{athlete_id()}/events/{event_id}", event) or {}


def get(event_id: int | str) -> dict:
    return _request("GET", f"/athlete/{athlete_id()}/events/{event_id}") or {}


def delete(event_ids: list[int | str]) -> int:
    out = _request("PUT", f"/athlete/{athlete_id()}/events/bulk-delete", [{"id": int(i)} for i in event_ids])
    return (out or {}).get("eventsDeleted", 0)


def day_events(day: str) -> list[dict]:
    return _request("GET", f"/athlete/{athlete_id()}/events",
                    params={"oldest": day, "newest": day, "category": "WORKOUT"}) or []


def verify(event: dict, course: dict, fit: bytes | None = None) -> list[str]:
    """Problems with a written event as read back from intervals.icu (empty = OK).

    ``fit``: the file from ``download_fit`` — decoded with Garmin's FIT SDK and compared step by step with the
    course (durations, distances, repeats, pace/HR/power targets), i.e. what Garmin will receive.
    """
    problems = []
    if not (event.get("workout_doc") or {}).get("steps"):
        problems.append("intervals.icu did not read any workout step")
    if fit is not None:
        import fitworkout as F
        from garmin_fit_sdk import Decoder, Stream

        messages, errors = Decoder(Stream.from_byte_array(bytearray(fit))).read(
            convert_types_to_strings=True, expand_sub_fields=True, expand_components=True)
        problems += [f"FIT decode error: {e}" for e in errors]
        steps = messages.get("workout_step_mesgs") or []
        problems += [f"Garmin version differs: {p}" for p in F._compare_with_course(steps, course, external=True)]
    for err in event.get("push_errors") or []:
        problems.append(f"Garmin upload error: {err}")
    return problems


def summary(event: dict) -> str:
    secs = event.get("moving_time") or (event.get("workout_doc") or {}).get("duration")
    dist = event.get("distance") or (event.get("workout_doc") or {}).get("distance")
    bits = [event.get("name", "?")]
    if secs:
        bits.append(f"~{round(secs / 60)} min")
    if dist:
        bits.append(f"{dist / 1000:.1f} km")
    return " · ".join(bits)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("day").add_argument("date")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "status":
            ath = _request("GET", f"/athlete/{athlete_id()}") or {}
            print(f"intervals.icu OK — athlete {ath.get('id', '?')}")
        elif a.cmd == "day":
            events = day_events(a.date)
            if not events:
                print("no planned workout that day")
            for ev in events:
                state = "Garmin upload error" if ev.get("push_errors") else "ok"
                print(f"- {summary(ev)} ({state})")
    except IntervalsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
