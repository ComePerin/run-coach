#!/usr/bin/env python3
"""Validate, create and read back a single COROS scheduled workout.

    workout.py validate COURSE.json [--sport run|bike|trail]
    workout.py create YYYY-MM-DD COURSE.json [--yes]   # dry run without --yes
    workout.py update YYYY-MM-DD ID_IN_PLAN COURSE.json [--yes]
    workout.py show YYYY-MM-DD ID_IN_PLAN
    workout.py day YYYY-MM-DD                           # what is already scheduled that day
    workout.py export YYYY-MM-DD COURSE.json [--out DIR] [--yes]   # Garmin: write a FIT workout file
    workout.py send YYYY-MM-DD COURSE.json [--update EVENT_ID] [--yes]   # Garmin: intervals.icu → Garmin Connect

COROS: create/update/show/day use the COROS calendar. Garmin (read-only API): `send` puts the workout on the
intervals.icu calendar, which uploads it to Garmin Connect; or `export` a .fit file to copy to the watch
(GARMIN/NewFiles). `validate` checks both formats.

COURSE.json may be '-' to read from stdin. The course format is documented in docs/course-json.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coros  # noqa: E402
import fitworkout as F  # noqa: E402
import intervals as I  # noqa: E402
import parsers as P  # noqa: E402
from plan import validate_course  # noqa: E402

SPORT_BY_CODE = {1: "run", 2: "bike", 5: "trail"}


def load_course(path: str) -> dict:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def estimate(course: dict) -> str:
    """Rough human summary of a course: time/distance of preset sections, count of free sections."""
    secs = dist = free = 0

    def walk(sections, mult=1):
        nonlocal secs, dist, free
        for s in sections:
            if s.get("intervalGroup"):
                walk(s.get("sets") or [], mult * s.get("repeats", 1))
            elif s.get("targetType") == 2:
                secs += s["targetValue"] * mult
            elif s.get("targetType") == 1:
                dist += s["targetValue"] * mult
                if s.get("intensityType") == 2 and s.get("intensityValueStart"):
                    pace = (s["intensityValueStart"] + s["intensityValueEnd"]) / 2
                    secs += s["targetValue"] / 1000 * pace * mult
            elif s.get("targetType") == 4:
                free += mult

    walk(course.get("sections") or [])
    bits = []
    if secs:
        bits.append(f"~{secs / 60:.0f} min timed")
    if dist:
        bits.append(f"{dist / 1000:g} km by distance")
    if free:
        bits.append(f"{free} free section(s) (lap button)")
    return ", ".join(bits) or "no preset targets"


def day_schedule(day: str) -> str:
    return coros.call("queryTrainingSchedule", {"startDate": P.yyyymmdd(day), "endDate": P.yyyymmdd(day)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate")
    p.add_argument("course")
    p.add_argument("--sport", choices=["run", "bike", "trail"])
    p = sub.add_parser("create")
    p.add_argument("date")
    p.add_argument("course")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("update")
    p.add_argument("date")
    p.add_argument("id_in_plan")
    p.add_argument("course")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("show")
    p.add_argument("date")
    p.add_argument("id_in_plan")
    p = sub.add_parser("day")
    p.add_argument("date")
    p = sub.add_parser("send")
    p.add_argument("date")
    p.add_argument("course")
    p.add_argument("--update", metavar="EVENT_ID", help="replace this intervals.icu event instead of creating one")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("export")
    p.add_argument("date")
    p.add_argument("course")
    p.add_argument("--out", help="output folder (default: exports/)")
    p.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "send":
            course = load_course(a.course)
            sport = SPORT_BY_CODE.get(course.get("sportType"), "run")
            errors = validate_course(course, sport) + F.validate_for_garmin(course)
            if errors:
                print("INVALID course for Garmin:\n  " + "\n  ".join(errors))
                return 1
            print(f"valid {sport} course '{course['courseName']}': {estimate(course)}")
            settings = I.sport_settings(course)
            missing = I.preflight(course, settings)
            if missing:
                print("cannot send yet:\n  " + "\n  ".join(missing))
                return 1
            event = I.event_payload(a.date, course, settings.get("max_hr"))
            if not a.yes:
                verb = f"replace event {a.update}" if a.update else "add it to intervals.icu"
                print(f"DRY RUN — would {verb} on {a.date} as:\n\n{event['description']}")
                planned = I.day_events(a.date)
                print("Already planned that day: " + (", ".join(I.summary(ev) for ev in planned) or "nothing"))
                print("Re-run with --yes after the user confirms.")
                return 0
            if a.update:
                event_id = a.update
                I.update(event_id, event)
            else:
                event_id = I.create([event])[0]["id"]
            back = I.get(event_id)
            print(f"{'updated' if a.update else 'created'} on intervals.icu: {I.summary(back)}")
            problems = I.verify(back, course, I.download_fit(event_id))
            if not problems:
                print("✓ the FIT file intervals.icu builds for Garmin matches the workout step by step")
            for pr in problems:
                print(f"⚠ {pr}")
            print("intervals.icu uploads it to Garmin Connect if \"Upload planned workouts\" is ticked in its settings "
                  "(next ~7 days only). Then sync the watch from the Garmin Connect app.")
            return 1 if problems else 0
        if a.cmd == "export":
            course = load_course(a.course)
            sport = SPORT_BY_CODE.get(course.get("sportType"), "run")
            errors = validate_course(course, sport) + F.validate_for_garmin(course)
            if errors:
                print("INVALID course for Garmin:\n  " + "\n  ".join(errors))
                return 1
            folder = Path(a.out) if a.out else Path(__file__).resolve().parent.parent / "exports"
            target = folder / F.file_name(a.date, course)
            print(f"valid {sport} course '{course['courseName']}': {estimate(course)}")
            if not a.yes:
                print(f"DRY RUN — would write {target}. Re-run with --yes.")
                return 0
            folder.mkdir(parents=True, exist_ok=True)
            target.write_bytes(F.course_to_fit(course))
            print(f"wrote {target}\n\n{F.COPY_HELP}")
            return 0
        if a.cmd in ("validate", "create", "update"):
            course = load_course(a.course)
            sport = getattr(a, "sport", None) or SPORT_BY_CODE.get(course.get("sportType"), "run")
            errors = validate_course(course, sport)
            if errors:
                print("INVALID course:\n  " + "\n  ".join(errors))
                return 1
            print(f"valid {sport} course '{course['courseName']}': {estimate(course)}")
            if a.cmd == "validate":
                garmin_errors = F.validate_for_garmin(course)
                if garmin_errors:
                    print("note — not exportable to Garmin:\n  " + "\n  ".join(garmin_errors))
                return 0
            if not a.yes:
                print(f"DRY RUN — would {a.cmd} on {a.date}. Re-run with --yes after the user confirms.")
                print("Already scheduled that day:\n" + day_schedule(a.date))
                return 0
            args = {"date": P.yyyymmdd(a.date), "course": course}
            if a.cmd == "create":
                out = coros.call("createScheduledWorkout", args)
            else:
                args["idInPlan"] = str(a.id_in_plan)
                out = coros.call("updateScheduledWorkout", args)
            new_id = P.parse_created_id(out)
            print(out)
            if new_id:
                print("\n--- read back ---")
                print(coros.call("queryScheduledWorkoutDetails", {"date": P.yyyymmdd(a.date), "idInPlan": new_id}))
        elif a.cmd == "show":
            print(coros.call("queryScheduledWorkoutDetails", {"date": P.yyyymmdd(a.date), "idInPlan": str(a.id_in_plan)}))
        elif a.cmd == "day":
            print(day_schedule(a.date))
    except (coros.CorosError, I.IntervalsError, F.FitCheckError) as exc:
        print(f"error: {exc}\nIf this was a write that timed out, check `workout.py day DATE` (COROS) or "
              f"`intervals.py day DATE` before retrying.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
