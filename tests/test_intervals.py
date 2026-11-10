import base64
import copy
from datetime import date

import fitworkout as F
import intervals as I
import plan as PL
import pytest
from test_plan import INTERVALS, make_plan


class FakeIntervals:
    """In-memory stand-in for the intervals.icu API (records every call)."""

    def __init__(self, push_errors=None):
        self.events: dict[int, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.next_id = 100
        self.push_errors = push_errors

    def __call__(self, method, path, body=None, params=None):
        self.calls.append((method, path))
        if method == "POST" and path.endswith("/events/bulk"):
            out = []
            for ev in body:
                self.next_id += 1
                stored = {**ev, "id": self.next_id, "workout_doc": self._doc(ev), "push_errors": self.push_errors}
                self.events[self.next_id] = stored
                out.append(stored)
            return out
        if method == "PUT" and "/events/" in path and not path.endswith("bulk-delete"):
            eid = int(path.rsplit("/", 1)[1])
            self.events[eid].update(body, workout_doc=self._doc(body))
            return self.events[eid]
        if method == "GET" and "/events/" in path:
            return self.events[int(path.rsplit("/", 1)[1])]
        if method == "PUT" and path.endswith("bulk-delete"):
            gone = [e["id"] for e in body if self.events.pop(e["id"], None)]
            return {"eventsDeleted": len(gone)}
        raise AssertionError(f"unexpected call {method} {path}")

    @staticmethod
    def _doc(ev):
        # pretend intervals.icu parsed one top-level step per FIT section (repeat groups folded)
        fit = base64.b64decode(ev["file_contents_base64"])
        assert F.check_fit(fit) == []  # what we send is always a valid FIT workout
        return {"steps": [{}] * ev.pop("_sections", 3)}


@pytest.fixture
def fake(monkeypatch):
    api = FakeIntervals()
    monkeypatch.setattr(I, "_request", api)
    monkeypatch.setenv("COACH_PROVIDER", "garmin")
    monkeypatch.setenv("INTERVALS_API_KEY", "test-key")
    monkeypatch.setattr(PL, "today", lambda: date(2026, 9, 21))
    return api


def test_event_payload():
    fit = F.course_to_fit(INTERVALS)
    ev = I.event_payload("2026-09-23", INTERVALS, fit, "x.fit", external_id="coros-coach:demo:w1-wed")
    assert ev["category"] == "WORKOUT" and ev["type"] == "Run"
    assert ev["start_date_local"] == "2026-09-23T00:00:00"
    assert ev["name"] == INTERVALS["courseName"] and ev["description"] == INTERVALS["courseDescription"]
    assert base64.b64decode(ev["file_contents_base64"]) == fit
    assert I.event_payload("2026-09-23", {**INTERVALS, "sportType": 5}, fit, "x.fit")["type"] == "TrailRun"


def test_verify_reports_parse_and_garmin_problems():
    assert I.verify({"workout_doc": {"steps": [{}, {}, {}]}}, INTERVALS) == []
    assert "did not read" in I.verify({"workout_doc": {}}, INTERVALS)[0]
    assert "2 top-level steps" in I.verify({"workout_doc": {"steps": [{}, {}]}}, INTERVALS)[0]
    errs = I.verify({"workout_doc": {"steps": [{}] * 3}, "push_errors": ["Garmin: not linked"]}, INTERVALS)
    assert errs == ["Garmin upload error: Garmin: not linked"]


def plan_on_disk(tmp_path):
    plan = make_plan()
    plan["weeks"][1]["sessions"] = [s for s in plan["weeks"][1]["sessions"] if s["id"] != "w2-sun"]
    PL.save_plan(plan, tmp_path)
    return tmp_path


def sessions(path):
    return {s["id"]: s for _, s in PL.iter_sessions(PL.load_plan(path))}


def test_push_dry_run_writes_nothing(fake, tmp_path):
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=False) == 0
    assert fake.calls == []
    assert sessions(path)["w1-wed"]["status"] == "planned"


def test_push_creates_then_updates_adjusted(fake, tmp_path):
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 0
    s = sessions(path)["w1-wed"]
    assert s["status"] == "pushed" and s["intervals"]["event_id"] == 101
    assert [c[0] for c in fake.calls] == ["POST", "GET"]
    assert fake.events[101]["external_id"] == "coros-coach:demo:w1-wed"

    # nothing new to push
    fake.calls.clear()
    assert PL.cmd_push(str(path), 7, yes=True) == 0
    assert fake.calls == []

    # the coach shortens the session → status adjusted → same event updated, no duplicate
    plan = PL.load_plan(path)
    for _, sess in PL.iter_sessions(plan):
        if sess["id"] == "w1-wed":
            sess["course"] = copy.deepcopy(INTERVALS)
            sess["course"]["sections"][1]["repeats"] = 3
            sess["status"] = "adjusted"
    PL.save_plan(plan, path)
    assert PL.cmd_push(str(path), 7, yes=True) == 0
    assert [c[0] for c in fake.calls] == ["PUT", "GET"]
    assert len(fake.events) == 1 and sessions(path)["w1-wed"]["status"] == "pushed"


def test_push_reports_garmin_upload_errors(fake, tmp_path):
    fake.push_errors = ["Garmin Connect is not linked"]
    path = plan_on_disk(tmp_path)
    assert PL.cmd_push(str(path), 7, yes=True) == 1  # non-zero so the agent notices


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
    assert fake.calls == []
