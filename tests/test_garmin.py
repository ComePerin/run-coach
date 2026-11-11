import io
import json
from datetime import date
from pathlib import Path

import fitdecode
import garmin_parsers as G
import plan as PL
import pytest
import readiness as R
from test_plan import INTERVALS, make_plan

FIX = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "coros-workout" / "examples"


def load(name):
    return json.loads((FIX / name).read_text())


# ----------------------------------------------------------------------------- parsers

def test_parse_activities():
    acts = G.parse_activities(load("garmin_activities.json"))
    assert len(acts) == 5  # the row without activityId is dropped
    first = acts[0]
    assert first["date"] == "2026-09-21" and first["label_id"] == "1001"
    assert first["family"] == "run" and first["sport"] == "Running"
    assert first["duration_s"] == 3005 and first["distance_km"] == 10.01
    assert first["avg_pace_s"] == 300 and first["avg_hr"] == 142
    assert first["hr_zone_s"] == [120, 1800, 1085, 0, 0]
    assert first["fastest_splits"]["10k"] == 2990
    fams = {a["name"]: a["family"] for a in acts}
    assert fams == {"Morning run": "run", "Intervals": "run", "Commute": "bike", "Pool": "swim",
                    "Hill trail": "trail"}
    bike = next(a for a in acts if a["family"] == "bike")
    assert bike["avg_pace_s"] is None and bike["avg_speed_kmh"] == 26.6


def test_family_mapping():
    assert G.family("treadmill_running") == "run"
    assert G.family("trail_running") == "trail"
    assert G.family("gravel_cycling") == "bike"
    assert G.family("open_water_swimming") == "swim"
    assert G.family("hiking") == "hike"
    assert G.family("strength_training") == "other"
    assert G.family(None) == "other"


def test_parse_hrv():
    rows = G.parse_hrv(load("garmin_hrv.json"))
    assert [r["hrv"] for r in rows] == [63, 49, 47]
    assert rows[-1] == {"date": "2026-09-28", "hrv": 47, "status": "Unbalanced", "low": 52, "high": 70,
                        "baseline": 58}
    assert R.score_hrv(rows)[0] == -2  # below range two nights in a row
    assert G.parse_hrv(None) == []


def test_parse_resting_hr_and_sleep():
    rhr = G.parse_resting_hr(load("garmin_daily_summaries.json"))
    assert rhr[-1] == {"date": "2026-09-28", "rhr": 57} and rhr[-2]["rhr"] is None
    assert R.score_rhr(rhr)[0] == -2  # +9 bpm vs 7-day mean
    sleep = G.parse_sleep(load("garmin_sleep.json"))
    assert [s["date"] for s in sleep] == ["2026-09-27", "2026-09-28"]  # zero-length night dropped
    assert sleep[0] == {"date": "2026-09-27", "score": 82, "sleep_min": 465, "deep_pct": 20}
    assert sleep[1]["score"] is None and sleep[1]["sleep_min"] == 350
    assert R.score_sleep(sleep)[0] == -2  # 5.8 h < 6 h


def test_parse_body_battery():
    rows = load("garmin_body_battery.json")
    rec = G.parse_body_battery(rows, date(2026, 9, 28))
    assert rec["recovery_pct"] == 62 and rec["level"] == "Body Battery"
    score, desc = R.score_recovery(rec)
    assert score == -1 and desc == "Body Battery 62/100"
    assert G.parse_body_battery(rows, "2026-09-27")["recovery_pct"] == 88
    empty = [{"date": "2026-09-28", "bodyBatteryValuesArray": [[1, None]]}]
    assert G.parse_body_battery(empty, "2026-09-28")["recovery_pct"] is None
    assert R.score_recovery({"recovery_pct": 80, "level": "Recovered"})[1] == "COROS recovery 80% (Recovered)"


def test_match_garmin_activities():
    plan = make_plan()
    acts = G.parse_activities(load("garmin_activities.json"))
    changes = PL.match_activities(plan, acts, until=date(2026, 9, 28))
    sessions = {s["id"]: s for _, s in PL.iter_sessions(plan)}
    assert sessions["w1-mon"]["status"] == "done"
    assert sessions["w1-mon"]["actual"]["label_id"] == "1001"
    assert sessions["w1-wed"]["actual"]["avg_pace"] == "5:00"
    assert "w1-mon" in changes["done"]
    # the ride and the swim are not run sessions: they show up as unplanned
    assert any("Road Biking" in u for u in changes["unplanned"])


# ----------------------------------------------------------------------------- computed metrics

def test_trimp_and_load():
    acts = G.parse_activities(load("garmin_activities.json"))
    assert R.trimp(acts[0]) == pytest.approx((120 * 1 + 1800 * 2 + 1085 * 3) / 60)
    rows = R.load_from_activities(acts, date(2026, 9, 27), days=3)
    assert [r["date"] for r in rows] == ["2026-09-25", "2026-09-26", "2026-09-27"]
    last = rows[-1]
    # all activities are inside both windows: acute = chronic x 4 -> ratio 4.0
    assert last["ratio"] == 4.0 and last["comment"] == "Excessive"
    assert R.score_load(rows)[0] == -2
    # the trail run has no HR zones: it counts with the median TRIMP/min of the others
    assert last["short_term"] > round(R.trimp(acts[0]) + R.trimp(acts[1]))


def test_load_needs_history():
    assert R.load_from_activities([], date(2026, 9, 28)) == []


def test_estimate_fitness():
    acts = G.parse_activities(load("garmin_activities.json"))
    fit = R.estimate_fitness(acts)
    # best 10k-equivalent: the 5k in 21:30 on the interval day
    assert fit["predictions"]["5k"] == "21:30"
    assert fit["predictions"]["10k"] == R._hms(R.riegel(1290, 5000, 10000))
    assert fit["threshold_pace"] == "4:33"  # pace of the ~13.2 km Riegel predicts for 60 min
    assert "5k effort on 2026-09-23" in fit["source"]
    assert fit["vo2max"] is None
    assert R.estimate_fitness([])["threshold_pace"] is None


# ----------------------------------------------------------------------------- FIT workouts

def decode_steps(data: bytes) -> tuple[dict, list[dict]]:
    workout, steps = {}, []
    with fitdecode.FitReader(io.BytesIO(data)) as reader:
        for frame in reader:
            if isinstance(frame, fitdecode.FitDataMessage):
                values = {f.name: f.value for f in frame.fields if f.value is not None}
                if frame.name == "workout":
                    workout = values
                elif frame.name == "workout_step":
                    steps.append(values)
    return workout, steps


def test_course_to_fit_intervals():
    import fitworkout as F

    workout, steps = decode_steps(F.course_to_fit(INTERVALS))
    assert workout["sport"] == "running" and workout["num_valid_steps"] == 5
    assert [s["intensity"] for s in steps] == ["warmup", "active", "rest", "active", "cooldown"]
    assert steps[0]["duration_type"] == "open"
    rep = steps[1]
    assert rep["duration_type"] == "distance" and rep["duration_distance"] == 1000
    assert rep["target_type"] == "speed"
    # 4:05/km +/- 5 s -> 4:00-4:10/km
    assert rep["custom_target_speed_high"] == pytest.approx(1000 / 240, abs=1e-3)
    assert rep["custom_target_speed_low"] == pytest.approx(1000 / 250, abs=1e-3)
    assert steps[2]["duration_time"] == 120
    assert steps[3]["duration_type"] == "repeat_until_steps_cmplt"
    assert steps[3]["duration_step"] == 1 and steps[3]["repeat_steps"] == 4


def test_course_to_fit_hr_and_bike():
    import fitworkout as F

    course = json.loads((EXAMPLES / "bike-endurance-hr.json").read_text())
    workout, steps = decode_steps(F.course_to_fit(course))
    assert workout["sport"] == "cycling"
    sec = course["sections"][1]
    assert steps[1]["target_type"] == "heart_rate"
    assert steps[1]["custom_target_heart_rate_low"] == sec["intensityValueStart"] + 100
    assert steps[1]["custom_target_heart_rate_high"] == sec["intensityValueEnd"] + 100


def test_validate_for_garmin():
    import fitworkout as F

    assert F.validate_for_garmin(INTERVALS) == []
    trail = json.loads((EXAMPLES / "trail-climb.json").read_text())
    errs = F.validate_for_garmin(trail)
    assert any("climb" in e for e in errs) and any("effort" in e for e in errs)
    pace_zone = {"sections": [{"sectionType": 2, "targetType": 2, "targetValue": 600, "intensityType": 2,
                               "sectionIntensity": 3}]}
    assert "pace zones" in F.validate_for_garmin(pace_zone)[0]
    hr6 = {"sections": [{"sectionType": 2, "targetType": 2, "targetValue": 60, "intensityType": 1,
                         "sectionIntensity": 6}]}
    assert "5 heart-rate zones" in F.validate_for_garmin(hr6)[0]
    pct = {"sections": [{"sectionType": 2, "targetType": 2, "targetValue": 60, "intensityType": 1,
                         "intensityPercentStart": 80, "intensityPercentEnd": 85}]}
    assert "percent" in F.validate_for_garmin(pct)[0]


def test_file_name():
    import fitworkout as F

    assert F.file_name("2026-11-12", {"courseName": "Fractionné 4 × 1000 m"}) == "2026-11-12-fractionne-4-1000-m.fit"
    assert F.file_name("2026-11-12", {}) == "2026-11-12-workout.fit"


def test_export_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_PROVIDER", "garmin")
    monkeypatch.setattr(PL, "today", lambda: date(2026, 9, 21))
    plan = make_plan()
    plan["weeks"][1]["sessions"] = [s for s in plan["weeks"][1]["sessions"] if s["id"] != "w2-sun"]
    PL.save_plan(plan, tmp_path)
    out = tmp_path / "exports"
    assert PL.cmd_export(str(tmp_path), 7, yes=False, out_dir=out) == 0
    assert not out.exists()  # dry run writes nothing
    assert PL.cmd_export(str(tmp_path), 7, yes=True, out_dir=out) == 0
    files = sorted(p.name for p in out.iterdir())
    assert files == ["2026-09-23-4-x-1000-m.fit"]
    saved = {s["id"]: s for _, s in PL.iter_sessions(PL.load_plan(tmp_path))}
    assert saved["w1-wed"]["status"] == "pushed"
    assert saved["w1-wed"]["garmin"]["file"] == files[0]
    assert (tmp_path / "plan.md").exists()


# ----------------------------------------------------------------------------- FIT checking pipeline

def exportable_examples():
    import fitworkout as F

    out = []
    for path in sorted(EXAMPLES.glob("*.json")):
        course = json.loads(path.read_text())
        if not F.validate_for_garmin(course):
            out.append(pytest.param(course, id=path.stem))
    return out


@pytest.mark.parametrize("course", exportable_examples() + [pytest.param(INTERVALS, id="test-intervals")])
def test_every_export_passes_the_checks(course):
    import fitworkout as F

    assert F.check_fit(F.course_to_fit(course, check=False), course) == []


def test_repeat_step_has_a_target_type():
    import fitworkout as F

    _, steps = decode_steps(F.course_to_fit(INTERVALS))
    assert steps[3]["target_type"] == "open"


def test_check_detects_corruption():
    import fitworkout as F

    data = bytearray(F.course_to_fit(INTERVALS))
    data[40] ^= 0xFF  # flip one byte in the data records
    assert "integrity" in F.check_fit(bytes(data))[0]
    assert F.check_fit(b"not a fit file at all") == ["not a FIT file (bad header signature)"]


def test_check_detects_a_file_that_does_not_match_its_course():
    import copy

    import fitworkout as F

    data = F.course_to_fit(INTERVALS)
    other = copy.deepcopy(INTERVALS)
    other["sections"][1]["repeats"] = 5
    other["sections"][1]["sets"][0]["targetValue"] = 800
    problems = F.check_fit(data, other)
    assert any("repeat does not match" in p for p in problems)
    assert any("duration_distance" in p for p in problems)


def test_export_refuses_a_file_that_fails_the_checks(monkeypatch):
    import fitworkout as F

    monkeypatch.setattr(F, "check_fit", lambda data, course=None: ["simulated problem"])
    with pytest.raises(F.FitCheckError, match="simulated problem"):
        F.course_to_fit(INTERVALS)
