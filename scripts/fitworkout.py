"""Convert a workout ("course" JSON, docs/course-json.md) into a Garmin FIT workout file, and check it.

The Garmin Personal API cannot write workouts, so Garmin athletes get a ``.fit`` file to copy to the watch
(``GARMIN/NewFiles`` over USB, see docs/garmin-reference.md). The same course JSON as for COROS is used, so plans,
examples and ``plan.validate_course`` are shared; ``validate_for_garmin`` rejects what FIT cannot express.

Mapping
    sectionType 1/2/3/4        -> intensity warmup / active / rest / cooldown
    targetType 1/2/4           -> duration distance (m) / time (s) / open (lap button)
    intervalGroup              -> its steps, then a "repeat until steps complete" step
    intensityType 1 (HR)       -> custom HR range (bpm) or HR zone (sectionIntensity)
    intensityType 2 (pace)     -> custom speed range (pace s/km -> m/s); pace zones are rejected
    intensityType 4 (power)    -> custom power range (W) or power zone
    sportType 1/2/5            -> running / cycling / running + trail sub-sport
"""

from __future__ import annotations

import re
import time
import unicodedata

SPORTS = {1: ("RUNNING", "GENERIC"), 2: ("CYCLING", "GENERIC"), 5: ("RUNNING", "TRAIL")}
INTENSITY = {1: "WARMUP", 2: "ACTIVE", 3: "REST", 4: "COOLDOWN"}
STEP_NAME = {1: "Warm-up", 2: "Run", 3: "Recover", 4: "Cool-down"}
MAX_NAME = 50  # string size reserved in the FIT file


def validate_for_garmin(course: dict) -> list[str]:
    """Errors for course features that have no FIT equivalent (run after plan.validate_course)."""
    errs: list[str] = []

    def check(sec: dict, where: str) -> None:
        if sec.get("targetType") == 3:
            errs.append(f"{where}: climb targets (targetType 3) do not exist on Garmin; use time or distance")
        if sec.get("intensityType") == 3:
            errs.append(f"{where}: % effort pace (intensityType 3) is COROS-only; use pace, HR or power")
        if "intensityPercentStart" in sec or "intensityPercentEnd" in sec:
            errs.append(f"{where}: percent intensities depend on COROS thresholds; use absolute values")
        zone = sec.get("sectionIntensity")
        if zone and sec.get("intensityType") == 2:
            errs.append(f"{where}: pace zones are COROS zones; give an absolute pace range (plan.py zones)")
        if zone and sec.get("intensityType") == 1 and zone > 5:
            errs.append(f"{where}: Garmin has 5 heart-rate zones; zone {zone} does not exist")

    for i, sec in enumerate(course.get("sections") or []):
        if sec.get("intervalGroup"):
            for j, sub in enumerate(sec.get("sets") or []):
                check(sub, f"section {i + 1}.{j + 1}")
        else:
            check(sec, f"section {i + 1}")
    return errs


def _step(sec: dict, index: int, sport_type: int):
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import Intensity, WorkoutStepDuration, WorkoutStepTarget

    st = WorkoutStepMessage()
    st.message_index = index
    kind = sec.get("sectionType", 2)
    st.intensity = getattr(Intensity, INTENSITY.get(kind, "ACTIVE"))
    label = STEP_NAME.get(kind, "Step") if sport_type != 2 or kind != 2 else "Ride"
    tt, tv = sec.get("targetType"), sec.get("targetValue")
    if tt == 1:
        st.duration_type = WorkoutStepDuration.DISTANCE
        st.duration_distance = float(tv)
        label += f" {tv / 1000:g} km" if tv >= 1000 else f" {tv} m"
    elif tt == 2:
        st.duration_type = WorkoutStepDuration.TIME
        st.duration_time = float(tv)
        label += f" {tv // 60}'" + (f"{tv % 60:02d}\"" if tv % 60 else "")
    else:
        st.duration_type = WorkoutStepDuration.OPEN
        st.duration_value = 0
        label += " (lap)"

    it = sec.get("intensityType")
    zone = sec.get("sectionIntensity")
    lo, hi = sec.get("intensityValueStart"), sec.get("intensityValueEnd")
    if it == 1:
        st.target_type = WorkoutStepTarget.HEART_RATE
        if zone:
            st.target_hr_zone = int(zone)
        else:
            st.target_value = 0
            st.custom_target_heart_rate_low = int(lo) + 100  # FIT: values > 100 are bpm + 100
            st.custom_target_heart_rate_high = int(hi) + 100
            label += f" @ {lo}-{hi} bpm" if lo != hi else f" @ {lo} bpm"
    elif it == 2:
        st.target_type = WorkoutStepTarget.SPEED  # pace zones are rejected by validate_for_garmin
        st.target_value = 0
        fast, slow = min(lo, hi), max(lo, hi)
        if fast == slow:  # a single pace: give the watch a small +/- 5 s/km window
            fast, slow = fast - 5, slow + 5
        st.custom_target_speed_low = round(1000 / slow, 3)  # m/s; slower pace = lower speed
        st.custom_target_speed_high = round(1000 / fast, 3)
        label += f" @ {_pace(lo)}" + (f"-{_pace(hi)}" if lo != hi else "")
    elif it == 4:
        st.target_type = WorkoutStepTarget.POWER
        if zone:
            st.target_power_zone = int(zone)
        else:
            st.target_value = 0
            st.custom_target_power_low = int(lo) + 1000  # FIT: values > 1000 are watts + 1000
            st.custom_target_power_high = int(hi) + 1000
            label += f" @ {lo}-{hi} W" if lo != hi else f" @ {lo} W"
    else:
        st.target_type = WorkoutStepTarget.OPEN
        st.target_value = 0
    if zone:
        label += f" zone {zone}"
    st.workout_step_name = label[:MAX_NAME]
    return st


def _pace(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def course_steps(course: dict) -> list:
    """FIT workout step messages for a course (repeat steps point back to the first step of their group)."""
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import Intensity, WorkoutStepDuration, WorkoutStepTarget

    steps: list = []
    sport_type = course.get("sportType", 1)
    for sec in course.get("sections") or []:
        if sec.get("intervalGroup"):
            first = len(steps)
            for sub in sec.get("sets") or []:
                steps.append(_step(sub, len(steps), sport_type))
            rep = WorkoutStepMessage()
            rep.message_index = len(steps)
            rep.intensity = Intensity.ACTIVE
            rep.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
            rep.duration_step = first
            rep.target_type = WorkoutStepTarget.OPEN  # required field; the repeat count lives in target_value
            rep.target_repeat_steps = int(sec.get("repeats", 1))
            steps.append(rep)
        else:
            steps.append(_step(sec, len(steps), sport_type))
    return steps


def course_to_fit(course: dict, *, check: bool = True) -> bytes:
    """Encode a course as a FIT workout file and return its bytes.

    With ``check`` (default) the bytes go through ``check_fit`` and a ``FitCheckError`` is raised on any problem,
    so a malformed file is never written to disk.
    """
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.profile_type import FileType, Manufacturer, Sport, SubSport

    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = round(time.time() * 1000)
    file_id.serial_number = int(time.time()) & 0xFFFFFFFF

    steps = course_steps(course)
    sport, sub = SPORTS.get(course.get("sportType", 1), ("RUNNING", "GENERIC"))
    wkt = WorkoutMessage()
    wkt.workout_name = str(course.get("courseName", "Workout"))[:MAX_NAME]
    wkt.sport = getattr(Sport, sport)
    wkt.sub_sport = getattr(SubSport, sub)
    wkt.num_valid_steps = len(steps)

    builder = FitFileBuilder(auto_define=True, min_string_size=MAX_NAME)
    builder.add(file_id)
    builder.add(wkt)
    builder.add_all(steps)
    data = builder.build().to_bytes()
    if check:
        problems = check_fit(data, course)
        if problems:
            raise FitCheckError("generated FIT workout failed its checks:\n  " + "\n  ".join(problems))
    return data


# ----------------------------------------------------------------------------- checking pipeline

class FitCheckError(ValueError):
    """A generated FIT workout did not pass ``check_fit``."""


# fit-tool rules we deliberately do not follow. Garmin's profile only says "number of valid steps"; we count every
# workout_step message, repeat steps included, which is what Garmin's own workout files do.
IGNORED_FIT_TOOL_RULES = ("num_valid_steps",)


def check_fit(data: bytes, course: dict | None = None) -> list[str]:
    """Check a FIT workout file; return a list of problems (empty = OK). Three independent layers:

    1. Garmin's official decoder (garmin-fit-sdk): FIT signature, header + CRC integrity, no decode errors.
    2. fit-tool conformance validator (wire, full profile, workout file-type rules).
    3. Structure, decoded back with the official SDK: file type, one workout, contiguous step indexes, repeat
       steps pointing backwards to a normal step, num_valid_steps, and — when ``course`` is given — the same
       number of steps, durations, targets and repeat counts as the source course JSON.
    """
    problems: list[str] = []

    # 1. official decoder
    from garmin_fit_sdk import Decoder, Stream

    decoder = Decoder(Stream.from_byte_array(bytearray(data)))
    if not decoder.is_fit():
        return ["not a FIT file (bad header signature)"]
    if not decoder.check_integrity():
        return ["FIT integrity check failed (header or CRC)"]
    decoder = Decoder(Stream.from_byte_array(bytearray(data)))
    messages, errors = decoder.read(convert_types_to_strings=True, expand_sub_fields=True,
                                    expand_components=True, merge_heart_rates=False)
    problems += [f"Garmin SDK decode error: {e}" for e in errors]

    # 2. fit-tool conformance
    from fit_tool.fit_file import FitFile
    from fit_tool.validation import validate_fit_file
    from fit_tool.validation.report import ProfileScope

    report = validate_fit_file(FitFile.from_bytes(data), profile_scope=ProfileScope.FULL)
    problems += [f"fit-tool: {f}" for f in report.errors
                 if not any(rule in f.message for rule in IGNORED_FIT_TOOL_RULES)]

    # 3. structure and round trip
    file_ids = messages.get("file_id_mesgs") or []
    workouts = messages.get("workout_mesgs") or []
    steps = messages.get("workout_step_mesgs") or []
    if len(file_ids) != 1 or file_ids[0].get("type") != "workout":
        problems.append("file_id must be a single message of type 'workout'")
    if len(workouts) != 1:
        return problems + [f"expected exactly one workout message, found {len(workouts)}"]
    if not steps:
        return problems + ["workout has no steps"]
    if workouts[0].get("num_valid_steps") != len(steps):
        problems.append(f"num_valid_steps is {workouts[0].get('num_valid_steps')}, file has {len(steps)} steps")
    if not workouts[0].get("wkt_name"):
        problems.append("workout name is empty")
    for i, st in enumerate(steps):
        if st.get("message_index") != i:
            problems.append(f"step {i}: message_index is {st.get('message_index')}")
        if st.get("duration_type") == "repeat_until_steps_cmplt":
            back = st.get("duration_value")
            if back is None or not 0 <= back < i:
                problems.append(f"step {i}: repeat must point to an earlier step, points to {back}")
            elif steps[back].get("duration_type", "").startswith("repeat"):
                problems.append(f"step {i}: repeat points to another repeat step (nesting is not supported)")
            if not st.get("target_value") or st["target_value"] < 1:
                problems.append(f"step {i}: repeat count must be >= 1")
    if course is not None:
        problems += _compare_with_course(steps, course)
    return problems


def _expected_steps(course: dict) -> list[dict]:
    out: list[dict] = []
    for sec in course.get("sections") or []:
        if sec.get("intervalGroup"):
            first = len(out)
            out += [dict(sub) for sub in sec.get("sets") or []]
            out.append({"repeat_from": first, "repeats": sec.get("repeats", 1)})
        else:
            out.append(dict(sec))
    return out


def _compare_with_course(steps: list[dict], course: dict, *, external: bool = False) -> list[str]:
    """Decoded steps must say the same thing as the course JSON they came from.

    ``external``: the file was built by another tool from the same course (intervals.icu). HR then goes through
    % of max HR (±1 bpm rounding), zones are resolved by that tool's own zone settings (only the target type is
    checked), and power may be lap-average power.
    """
    expected = _expected_steps(course)
    if len(expected) != len(steps):
        return [f"course has {len(expected)} steps, FIT file has {len(steps)}"]
    problems = []
    duration = {1: ("distance", "duration_distance"), 2: ("time", "duration_time"), 4: ("open", None)}
    for i, (exp, st) in enumerate(zip(expected, steps, strict=True)):
        where = f"step {i}"
        if "repeat_from" in exp:
            if (st.get("duration_type"), st.get("duration_value"), st.get("target_value")) != (
                    "repeat_until_steps_cmplt", exp["repeat_from"], exp["repeats"]):
                problems.append(f"{where}: repeat does not match the interval group")
            continue
        kind, field = duration.get(exp.get("targetType"), ("open", None))
        if st.get("duration_type") != kind:
            problems.append(f"{where}: duration type {st.get('duration_type')} instead of {kind}")
        elif field and abs((st.get(field) or 0) - exp["targetValue"]) > 0.01:
            problems.append(f"{where}: {field} {st.get(field)} instead of {exp['targetValue']}")
        it = exp.get("intensityType")
        want = {1: "heart_rate", 2: "speed", 4: "power"}.get(it, "open")
        if external and want == "power" and st.get("target_type") == "power_lap":
            pass
        elif st.get("target_type") != want:
            problems.append(f"{where}: target {st.get('target_type')} instead of {want}")
        elif it == 2:
            lo, hi = st.get("custom_target_speed_low"), st.get("custom_target_speed_high")
            slow, fast = max(exp["intensityValueStart"], exp["intensityValueEnd"]), \
                min(exp["intensityValueStart"], exp["intensityValueEnd"])
            if not (lo and hi and lo <= 1000 / slow + 0.01 and hi >= 1000 / fast - 0.01 and lo < hi):
                problems.append(f"{where}: speed range {lo}-{hi} m/s does not cover the pace target")
        elif it == 1 and not exp.get("sectionIntensity"):
            tol = 1 if external else 0
            got = (st.get("custom_target_heart_rate_low"), st.get("custom_target_heart_rate_high"))
            want_hr = (exp["intensityValueStart"] + 100, exp["intensityValueEnd"] + 100)
            if None in got or any(abs(g - w) > tol for g, w in zip(got, want_hr, strict=True)):
                problems.append(f"{where}: heart-rate range {got} does not match {want_hr} (bpm + 100)")
        elif it == 1 and not external and st.get("target_hr_zone") != exp["sectionIntensity"]:
            problems.append(f"{where}: heart-rate zone does not match")
    return problems


def file_name(day: str, course: dict) -> str:
    """'2026-11-12-intervals-4-x-1000-m.fit' (ASCII, filesystem-safe)."""
    name = unicodedata.normalize("NFKD", str(course.get("courseName", "workout"))).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "workout"
    return f"{day}-{slug}.fit"


COPY_HELP = """Copy the .fit file(s) to the watch:
  • USB: plug the watch in and copy into GARMIN/NewFiles/ (newer watches mount over MTP: use your file manager,
    or `gio copy FILE mtp://…/Internal Storage/GARMIN/NewFiles/` on Linux, Android File Transfer on macOS).
  • Unplug: the watch imports it and the workout appears under Training → Workouts.
  Workouts are not scheduled on a date: start it from the Workouts list on the planned day.
  ⚠ Garmin Connect's website "Import Data" does NOT accept workout files (only activities and courses): it answers
    "One of your files was not accepted by the system" even for valid workouts. Copy to the watch instead."""


def main(argv: list[str] | None = None) -> int:
    """`fitworkout.py check FILE.fit [...]`: run the checking pipeline on existing files."""
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Check FIT workout files (Garmin SDK decode, fit-tool, structure).")
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    bad = 0
    for f in a.files:
        problems = check_fit(Path(f).read_bytes())
        print(f"{'OK  ' if not problems else 'FAIL'} {f}")
        for pr in problems:
            print(f"     {pr}")
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
