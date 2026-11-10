#!/usr/bin/env python3
"""Put planned workouts into Garmin Connect through intervals.icu (official Garmin partner).

Garmin's Personal API is read-only and Garmin Connect cannot import workout files. intervals.icu can: when the
athlete links Garmin in https://intervals.icu/settings and ticks "Upload planned workouts", every workout on the
intervals.icu calendar for the next ~7 days is pushed to the Garmin Connect calendar (website + app), then to the
watch. This module creates those workouts through the documented intervals.icu API, from the same FIT files as
``fitworkout.py`` produces (already checked by ``fitworkout.check_fit``).

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
USER_AGENT = "coros-coach (+https://github.com/Z3ZEL/coros-coach)"


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


def _request(method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
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
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code in (401, 403):
            raise IntervalsError(f"intervals.icu rejected the API key (HTTP {exc.code}). Check it in "
                                 f"{SETTINGS_PAGE}.") from exc
        raise IntervalsError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise IntervalsError(f"cannot reach intervals.icu: {exc.reason}") from exc
    return json.loads(raw) if raw else None


# ----------------------------------------------------------------------------- events

def event_payload(day: str, course: dict, fit_bytes: bytes, filename: str, external_id: str | None = None) -> dict:
    """One planned workout for ``POST /events/bulk`` (the FIT file carries the structure)."""
    event = {
        "category": "WORKOUT",
        "start_date_local": f"{day}T00:00:00",
        "type": EVENT_TYPE.get(course.get("sportType", 1), "Run"),
        "name": str(course.get("courseName", "Workout"))[:100],
        "description": str(course.get("courseDescription", "")),
        "filename": filename,
        "file_contents_base64": base64.b64encode(fit_bytes).decode(),
    }
    if external_id:
        event["external_id"] = external_id
    return event


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


def verify(event: dict, course: dict) -> list[str]:
    """Problems with a created event as read back from intervals.icu (empty = OK)."""
    problems = []
    doc = event.get("workout_doc") or {}
    steps = doc.get("steps") or []
    if not steps:
        problems.append("intervals.icu did not read any workout step from the FIT file")
    elif len(steps) != len(course.get("sections") or []):
        problems.append(f"intervals.icu shows {len(steps)} top-level steps, the course has "
                        f"{len(course.get('sections') or [])} sections")
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
