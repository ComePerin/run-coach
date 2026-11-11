import base64
import copy
import json
from datetime import date
from pathlib import Path

import fitworkout as F
import intervals as I
import plan as PL
import pytest
from test_plan import INTERVALS, make_plan

EXAMPLES = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "run-workout" / "examples"
RUN_SETTINGS = {"threshold_pace": 3.876, "max_hr": 195}


# ----------------------------------------------------------------------------- workout text

def test_course_to_text_intervals():
    text = I.course_to_text(INTERVALS, max_hr=195)
    assert text == (
        "Free warm-up, 4 x 1000 m at 4:05/km with 2 min rest, free cool-down.\n"
        "\n"
        "- Warm-up 10m Press lap\n"
        "\n"
        "4x\n"
        "- Run 1km 4:00-4:10/km Pace\n"
        "- Recover 2m\n"
        "\n"
        "- Cool-down 10m Press lap\n")


def test_course_to_text_traps_found_against_the_live_api():
    course = {"courseName": "x", "courseDescription": "- starts with a dash", "sportType": 1, "sections": [
        {"sectionType": 2, "targetType": 1, "targetValue": 400},          # "400m" would be 400 MINUTES
        {"sectionType": 3, "targetType": 2, "targetValue": 90, "intensityType": 1,
         "intensityValueStart": 117, "intensityValueEnd": 127},          # no absolute bpm syntax: % of max HR
        {"sectionType": 2, "targetType": 2, "targetValue": 3725},
    ]}
    lines = I.course_to_text(course, max_hr=195).splitlines()
    assert lines[0] == "starts with a dash"  # a note never becomes a step
    assert lines[2] == "- Run 0.4km"
    assert lines[3] == "- Recover 1m30s 60.0-65.1% HR"
    assert lines[4] == "- Run 1h2m5s"
    # cue text never contains digits (intervals.icu adds them to the duration)
    assert all(not any(c.isdigit() for c in ln.split()[1]) for ln in lines if ln.startswith("- "))


def test_course_to_text_bike_power_and_zones():
    course = json.loads((EXAMPLES / "bike-endurance-hr.json").read_text())
    text = I.course_to_text(course, max_hr=200)
    assert "- Ride 1h15m 60.0-70.0% HR" in text
    hills = json.loads((EXAMPLES / "hills-8x60s.json").read_text())
    assert "- Run 1m Z5 HR" in I.course_to_text(hills, max_hr=200)
    watts = {"sportType": 2, "sections": [{"sectionType": 2, "targetType": 2, "targetValue": 600,
                                           "intensityType": 4, "intensityValueStart": 200, "intensityValueEnd": 220}]}
    assert I.course_to_text(watts) == "- Ride 10m 200-220w\n"
    with pytest.raises(I.IntervalsError, match="max HR"):
        I.course_to_text(course, max_hr=None)


def test_preflight():
    assert I.preflight(INTERVALS, RUN_SETTINGS) == []
    missing = I.preflight(INTERVALS, {"max_hr": 195})
    assert len(missing) == 1 and "threshold pace for Run" in missing[0]
    hr_only = json.loads((EXAMPLES / "bike-endurance-hr.json").read_text())
    assert I.preflight(hr_only, {}) == ["set a max HR for Ride in https://intervals.icu/settings"]


def test_event_payload():
    ev = I.event_payload("2026-09-23", INTERVALS, 195, external_id="run-coach:demo:w1-wed")
    assert ev["category"] == "WORKOUT" and ev["type"] == "Run"
    assert ev["start_date_local"] == "2026-09-23T00:00:00"
    assert ev["name"] == INTERVALS["courseName"] and ev["description"] == I.course_to_text(INTERVALS, 195)
    assert "file_contents_base64" not in ev
    assert I.event_payload("2026-09-23", {**INTERVALS, "sportType": 5}, 195)["type"] == "TrailRun"


# ----------------------------------------------------------------------------- verification

def test_verify_accepts_a_faithful_garmin_file():
    fit = F.course_to_fit(INTERVALS)
    assert I.verify({"workout_doc": {"steps": [{}]}}, INTERVALS, fit) == []


def test_verify_catches_what_went_wrong_live():
    # what intervals.icu built from our first attempt: pace target dropped, recovery doubled
    bad = copy.deepcopy(INTERVALS)
    rep = bad["sections"][1]["sets"]
    for k in ("intensityType", "intensityValueStart", "intensityValueEnd"):
        rep[0].pop(k)
    rep[1]["targetValue"] = 240
    problems = I.verify({"workout_doc": {"steps": [{}]}}, INTERVALS, F.course_to_fit(bad, check=False))
    assert any("target open instead of speed" in p for p in problems)
    assert any("duration_time 240.0 instead of 120" in p for p in problems)


def test_verify_hr_tolerance_and_upload_errors():
    course = {"sportType": 1, "sections": [{"sectionType": 2, "targetType": 2, "targetValue": 600,
                                            "intensityType": 1, "intensityValueStart": 140, "intensityValueEnd": 150}]}
    off_by_one = copy.deepcopy(course)
    off_by_one["sections"][0].update(intensityValueStart=141, intensityValueEnd=149)
    assert I.verify({"workout_doc": {"steps": [{}]}}, course, F.course_to_fit(off_by_one, check=False)) == []
    off_by_five = copy.deepcopy(course)
    off_by_five["sections"][0]["intensityValueStart"] = 135
    assert I.verify({"workout_doc": {"steps": [{}]}}, course, F.course_to_fit(off_by_five, check=False))
    errs = I.verify({"workout_doc": {"steps": [{}]}, "push_errors": ["Garmin: not linked"]}, course)
    assert errs == ["Garmin upload error: Garmin: not linked"]
    assert "did not read" in I.verify({"workout_doc": {}}, course)[0]


# ----------------------------------------------------------------------------- plan push

class FakeIntervals:
    """In-memory stand-in for the intervals.icu API. ``garmin_course`` is what its FIT export will contain."""

    def __init__(self):
        self.events: dict[int, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.next_id = 100
        self.push_errors = None
        self.settings = dict(RUN_SETTINGS)
        self.garmin_course = None  # None = faithful copy of the last course sent

    def __call__(self, method, path, body=None, params=None, raw=False):
        self.calls.append((method, path))
        if path.endswith("/sport-settings/Run"):
            return self.settings
        if method == "POST" and path.endswith("/events/bulk"):
            out = []
            for ev in body:
                self.next_id += 1
                self.events[self.next_id] = {**ev, "id": self.next_id, "workout_doc": {"steps": [{}]},
                                             "push_errors": self.push_errors}
                out.append(self.events[self.next_id])
            return out
        if method == "GET" and path.endswith("download.fit"):
            return F.course_to_fit(self.garmin_course or self.sent_course, check=False)
        if method == "PUT" and "/events/" in path:
            eid = int(path.rsplit("/", 1)[1])
            self.events[eid].update(body)
            return self.events[eid]
        if method == "GET" and "/events/" in path:
            return self.events[int(path.rsplit("/", 1)[1])]
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def fake(monkeypatch):
    api = FakeIntervals()
    monkeypatch.setattr(I, "_request", api)
    monkeypatch.setenv("COACH_PROVIDER", "garmin")
    monkeypatch.setenv("INTERVALS_API_KEY", "test-key")
    monkeypatch.setattr(PL, "today", lambda: date(2026, 9, 21))
    real_payload = I.event_payload

    def payload(day, course, max_hr=None, external_id=None):
        api.sent_course = course
        return real_payload(day, course, max_hr, external_id)

    monkeypatch.setattr(I, "event_payload", payload)
    return api


def plan_on_disk(tmp_path):
    plan = make_plan()
    plan["weeks"][1]["sessions"] = [s for s in plan["weeks"][1]["sessions"] if s["id"] != "w2-sun"]
    PL.save_plan(plan, tmp_path)
    return tmp_path


def sessions(path):
    return {s["id"]: s for _, s in PL.iter_sessions(PL.load_plan(path))}


def writes(api):
    return [c for c in api.calls if c[0] != "GET"]


def test_push_dry_run_writes_nothing(fake, tmp_path):
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=False) == 0
    assert writes(fake) == []
    assert sessions(path)["w1-wed"]["status"] == "planned"


def test_push_stops_when_intervals_settings_are_missing(fake, tmp_path, capsys):
    fake.settings = {"max_hr": 195}
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 1
    assert "threshold pace for Run" in capsys.readouterr().err
    assert writes(fake) == []


def test_push_creates_then_updates_adjusted(fake, tmp_path):
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 0
    s = sessions(path)["w1-wed"]
    assert s["status"] == "pushed" and s["intervals"]["event_id"] == 101
    assert writes(fake) == [("POST", "/athlete/0/events/bulk")]
    assert fake.events[101]["description"].startswith(INTERVALS["courseDescription"])

    fake.calls.clear()
    assert PL.cmd_push(str(path), 7, yes=True) == 0  # nothing new
    assert writes(fake) == []

    plan = PL.load_plan(path)
    for _, sess in PL.iter_sessions(plan):
        if sess["id"] == "w1-wed":
            sess["course"] = copy.deepcopy(INTERVALS)
            sess["course"]["sections"][1]["repeats"] = 3
            sess["status"] = "adjusted"
    PL.save_plan(plan, path)
    assert PL.cmd_push(str(path), 7, yes=True) == 0
    assert writes(fake) == [("PUT", "/athlete/0/events/101")]
    assert "3x" in fake.events[101]["description"] and len(fake.events) == 1


def test_push_fails_when_the_garmin_version_differs(fake, tmp_path, capsys):
    bad = copy.deepcopy(INTERVALS)
    bad["sections"][1]["repeats"] = 2
    fake.garmin_course = bad
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 1
    assert "repeat does not match" in capsys.readouterr().out


def test_push_reports_garmin_upload_errors(fake, tmp_path):
    fake.push_errors = ["Garmin Connect is not linked"]
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 1


def test_push_falls_back_to_files_without_key(fake, tmp_path, monkeypatch):
    monkeypatch.delenv("INTERVALS_API_KEY")
    monkeypatch.setattr(I, "KEY_FILE", tmp_path / "missing")
    monkeypatch.setattr(PL, "REPO_ROOT", tmp_path)
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 0
    assert fake.calls == [] and (tmp_path / "exports").exists()


def test_push_refuses_courses_garmin_cannot_express(fake, tmp_path):
    path = plan_on_disk(tmp_path)
    plan = PL.load_plan(path)
    for _, sess in PL.iter_sessions(plan):
        if sess["id"] == "w1-wed":
            sess["course"]["sections"][1]["sets"][0].update(intensityType=2, sectionIntensity=4)
            for k in ("intensityValueStart", "intensityValueEnd"):
                sess["course"]["sections"][1]["sets"][0].pop(k)
    PL.save_plan(plan, path)
    assert PL.cmd_push(str(path), 7, yes=True) == 1
    assert writes(fake) == []


def test_request_sends_auth_and_a_non_default_user_agent(monkeypatch):
    """intervals.icu answers 403 to urllib's default 'Python-urllib' user agent."""
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"id": "i1"}'

    def fake_urlopen(req, timeout):
        seen.update({k.lower(): v for k, v in req.header_items()}, url=req.full_url)
        return Resp()

    monkeypatch.setenv("INTERVALS_API_KEY", "secret")
    monkeypatch.setattr(I.urllib.request, "urlopen", fake_urlopen)
    assert I._request("GET", "/athlete/0") == {"id": "i1"}
    assert seen["authorization"] == "Basic " + base64.b64encode(b"API_KEY:secret").decode()
    assert "python-urllib" not in seen["user-agent"].lower()
    assert seen["url"] == "https://intervals.icu/api/v1/athlete/0"
