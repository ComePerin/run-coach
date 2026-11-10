"""Convert a workout ("course" JSON, docs/course-json.md) into a Garmin FIT workout file.

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
    from fit_tool.profile.profile_type import Intensity, WorkoutStepDuration

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
            rep.target_repeat_steps = int(sec.get("repeats", 1))
            steps.append(rep)
        else:
            steps.append(_step(sec, len(steps), sport_type))
    return steps


def course_to_fit(course: dict) -> bytes:
    """Encode a course as a FIT workout file and return its bytes."""
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
    return builder.build().to_bytes()


def file_name(day: str, course: dict) -> str:
    """'2026-11-12-intervals-4-x-1000-m.fit' (ASCII, filesystem-safe)."""
    name = unicodedata.normalize("NFKD", str(course.get("courseName", "workout"))).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "workout"
    return f"{day}-{slug}.fit"


COPY_HELP = """Copy the .fit file(s) to the watch:
  • USB: plug the watch in and copy into GARMIN/NewFiles/ (newer watches mount over MTP: use your file manager,
    or `gio copy FILE mtp://…/Internal Storage/GARMIN/NewFiles/` on Linux, Android File Transfer on macOS).
  • Unplug: the watch imports it and the workout appears under Training → Workouts.
  Workouts are not scheduled on a date: start it from the Workouts list on the planned day."""
