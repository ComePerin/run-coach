#!/usr/bin/env python3
"""Thin wrapper around Garmin's official Personal API client (garmin-connect-personal-api-python).

The Personal API is **read-only**: it exposes activities and wellness data, but no workout, calendar,
VO2max or training-load endpoint. Workouts reach the watch as FIT files (see scripts/fitworkout.py).

Key lookup (never printed): $GARMIN_PERSONAL_API_KEY, else ~/.config/garmin/connect-personal-api-key.
Create a key at https://connect.garmin.com/app/settings/personalApiToken (scripts/setup.sh --garmin).

Usage:
    python scripts/garmin.py status                       # check that the key works
    python scripts/garmin.py endpoints                    # names accepted by `call`
    python scripts/garmin.py call NAME ['{"json": "args"}']
    python scripts/garmin.py call search_activities '{"start_date": "2026-10-01", "end_date": "2026-10-31"}'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "garmin"
KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken"
KEY_FILE = Path("~/.config/garmin/connect-personal-api-key").expanduser()

# Methods of GarminPersonalApiClient that `call` may use (all read-only GETs).
ENDPOINTS = (
    "search_activities", "get_activity", "get_activity_workouts",
    "get_daily_summaries", "get_daily_hrv", "get_daily_hrv_summaries",
    "get_daily_sleep", "get_daily_sleep_summaries", "get_daily_body_battery",
    "get_daily_heart_rate", "get_daily_stress", "get_daily_steps", "get_heart_rate_zones",
    "get_user_profile_settings", "get_weight_measurements", "get_fitness_age", "get_daily_spo2",
    "get_wellness_activity_summaries",
)


class GarminError(RuntimeError):
    """Raised when the key is missing/rejected or a request fails."""


def _client_module():
    try:
        import garmin_personal_api as gpa
    except ImportError as exc:  # Python < 3.12 or extra not installed
        raise GarminError("garmin-connect-personal-api-python is not installed (needs Python >= 3.12). "
                          "Run: scripts/setup.sh --garmin") from exc
    return gpa


def key_available() -> bool:
    """True when a Personal API key can be found (env var or default key file). Does not validate it."""
    import os

    return bool(os.environ.get("GARMIN_PERSONAL_API_KEY", "").strip()) or KEY_FILE.exists()


def _token(gpa, auth, force: bool) -> str:
    try:
        key = gpa.resolve_api_key()
    except gpa.GarminPersonalApiError as exc:
        raise GarminError(f"no Garmin Personal API key found. Create one at {KEY_PAGE} and run "
                          f"scripts/setup.sh --garmin (or set GARMIN_PERSONAL_API_KEY).") from exc
    try:
        return auth.obtain_token(key, force_refresh=force).access_token
    except gpa.HttpError as exc:
        if exc.status_code in (400, 401, 403):
            raise GarminError(f"Garmin rejected the Personal API key (HTTP {exc.status_code}); it may have "
                              f"expired or been deleted. Create a new one at {KEY_PAGE}.") from exc
        raise GarminError(str(exc)) from exc


def call(name: str, arguments: dict[str, Any] | None = None, *, cache: bool = True) -> Any:
    """Call one read-only client method by name and return the decoded JSON."""
    if name not in ENDPOINTS:
        raise GarminError(f"unknown endpoint {name}; see `garmin.py endpoints`")
    arguments = arguments or {}
    gpa = _client_module()
    with gpa.PersonalApiAuthenticator() as auth:
        for force in (False, True):  # a revoked token gets one retry with a fresh one
            try:
                with gpa.GarminPersonalApiClient(_token(gpa, auth, force)) as client:
                    result = getattr(client, name)(**arguments)
                break
            except gpa.HttpError as exc:
                if exc.status_code != 401 or force:
                    raise GarminError(f"{name} failed: HTTP {exc.status_code}") from exc
            except gpa.GarminPersonalApiError as exc:
                raise GarminError(f"{name} failed: {exc}") from exc
    if cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        (CACHE_DIR / f"{stamp}-{name}.json").write_text(
            json.dumps({"arguments": arguments, "response": result}, default=str))
    return result


def download_fit(activity_id: str | int) -> bytes:
    """Return the original FIT file of an activity (read-only GET, unzipped). Not cached: it holds the GPS track."""
    import io
    import zipfile

    gpa = _client_module()
    with gpa.PersonalApiAuthenticator() as auth:
        for force in (False, True):
            try:
                with gpa.GarminPersonalApiClient(_token(gpa, auth, force)) as client:
                    raw = client.download_activity(activity_id)
                break
            except gpa.HttpError as exc:
                if exc.status_code != 401 or force:
                    raise GarminError(f"download_activity failed: HTTP {exc.status_code}") from exc
            except gpa.GarminPersonalApiError as exc:
                raise GarminError(f"download_activity failed: {exc}") from exc
    if raw[:2] != b"PK":
        return raw
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
        if not names:
            raise GarminError("the activity archive holds no .fit file")
        return zf.read(names[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="check that the saved key works")
    sub.add_parser("endpoints", help="list the read-only endpoints accepted by `call`")
    p_call = sub.add_parser("call", help="call an endpoint")
    p_call.add_argument("name")
    p_call.add_argument("arguments", nargs="?", default="{}", help="JSON object of keyword arguments")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "status":
            prof = call("get_user_profile_settings", cache=False) or {}
            print(f"Garmin Personal API OK — units {prof.get('measurementSystem', '?')}, "
                  f"time zone {prof.get('timeZone', '?')}")
        elif args.cmd == "endpoints":
            print("\n".join(ENDPOINTS))
        elif args.cmd == "call":
            print(json.dumps(call(args.name, json.loads(args.arguments)), indent=1, ensure_ascii=False, default=str))
    except GarminError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
