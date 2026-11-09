from datetime import date
from pathlib import Path

import parsers as P
import plan as PL

FIX = Path(__file__).parent / "fixtures"

INTERVALS = {
    "courseName": "4 x 1000 m",
    "courseDescription": "Free warm-up, 4 x 1000 m at 4:05/km with 2 min rest, free cool-down.",
    "sportType": 1,
    "sections": [
        {"sectionType": 1, "targetType": 4},
        {"intervalGroup": True, "repeats": 4, "sets": [
            {"sectionType": 2, "targetType": 1, "targetValue": 1000, "intensityType": 2,
             "intensityValueStart": 245, "intensityValueEnd": 245},
            {"sectionType": 3, "targetType": 2, "targetValue": 120},
        ]},
        {"sectionType": 4, "targetType": 4},
    ],
}


def session(sid, day, sport="run", typ="easy", minutes=45, **extra):
    s = {"id": sid, "date": day, "sport": sport, "type": typ, "title": sid,
         "planned": {"duration_min": minutes}, "status": "planned"}
    s.update(extra)
    return s


def make_plan():
    return {
        "plan": {"id": "demo", "title": "Demo", "start": "2026-09-21", "weeks": 2, "weekly_minutes": 300,
                 "sessions_per_week": 5},
        "weeks": [
            {"n": 1, "phase": "base", "sessions": [
                session("w1-mon", "2026-09-21", minutes=60),
                session("w1-wed", "2026-09-23", typ="intervals", minutes=55, key=True, course=INTERVALS),
                session("w1-thu", "2026-09-24", minutes=40),
                session("w1-sat", "2026-09-26", typ="long", minutes=60, key=True),
            ]},
            {"n": 2, "phase": "base", "sessions": [
                session("w2-sun", "2026-09-27", minutes=35),  # wrong week on purpose in one test
            ]},
        ],
    }


def test_valid_course_passes():
    assert PL.validate_course(INTERVALS, "run") == []


def test_course_errors():
    bad = {"courseName": "x", "courseDescription": "", "sportType": 2, "sections": [
        {"sectionType": 2, "targetType": 4, "targetValue": 100},
        {"sectionType": 2, "targetType": 2, "targetValue": 600, "intensityValueStart": 150, "intensityValueEnd": 160},
        {"intervalGroup": True, "repeats": 30, "intensityType": 2, "sets": [{"sectionType": 1, "targetType": 1,
                                                                              "targetValue": 400}]},
    ]}
    errs = " | ".join(PL.validate_course(bad, "run"))
    assert "courseDescription is empty" in errs
    assert "does not match" in errs
    assert "free mode" in errs
    assert "require intensityType" in errs
    assert "repeats must be 1-20" in errs
    assert "must not have intensityType" in errs
    assert "sectionType must be one of (2, 3)" in errs


def test_validate_plan_week_bounds_and_guardrails():
    plan = make_plan()
    errors, warnings = PL.validate(plan)
    assert any("w2-sun" in e and "not in week 2" in e for e in errors)
    plan["weeks"][1]["sessions"][0]["date"] = "2026-09-28"
    errors, warnings = PL.validate(plan)
    assert errors == []
    assert any("no COROS course JSON" in w for w in warnings)


def test_hard_days_back_to_back_warning():
    plan = make_plan()
    plan["weeks"][1]["sessions"] = [
        session("a", "2026-09-29", typ="tempo", minutes=50),
        session("b", "2026-09-30", typ="intervals", minutes=50),
    ]
    _, warnings = PL.validate(plan)
    assert any("consecutive days" in w for w in warnings)


def test_match_activities_against_fixture():
    plan = make_plan()
    plan["weeks"][1]["sessions"][0]["date"] = "2026-09-28"
    acts = P.parse_sport_records((FIX / "sport_records.txt").read_text())
    changes = PL.match_activities(plan, acts, until=date(2026, 10, 2))
    by_id = {s["id"]: s for _, s in PL.iter_sessions(plan)}
    assert by_id["w1-mon"]["status"] == "done"                      # 1:02:19 run on 21/09
    assert by_id["w1-wed"]["actual"]["distance_km"] == 11.4          # 23/09 run
    assert by_id["w1-thu"]["status"] == "done"                       # no run on 24/09 -> matched 25/09 (+1 day)
    assert by_id["w1-thu"]["actual"]["matched_date"] == "2026-09-25"
    assert by_id["w1-sat"]["actual"]["compliance_pct"] == 102        # 1:00:58 for 60'
    assert by_id["w2-sun"]["status"] in ("done", "partial")
    assert "w1-mon" in changes["done"]
    assert any("Bouldering" in u for u in changes["unplanned"])
    # idempotent: a second pass changes nothing
    again = PL.match_activities(plan, acts, until=date(2026, 10, 2))
    assert again["done"] == [] and again["unplanned"] == []


def test_missed_session():
    plan = make_plan()
    plan["weeks"][1]["sessions"][0]["date"] = "2026-09-28"
    plan["weeks"][0]["sessions"].append(session("w1-fri", "2026-09-22", sport="bike", minutes=60))
    PL.match_activities(plan, [], until=date(2026, 10, 2))
    assert all(s["status"] == "missed" for _, s in PL.iter_sessions(plan))


def test_render_roundtrip(tmp_path):
    plan = make_plan()
    plan["weeks"][1]["sessions"][0]["date"] = "2026-09-28"
    PL.save_plan(plan, tmp_path)
    loaded = PL.load_plan(tmp_path)
    assert loaded == plan
    md = PL.render(loaded)
    assert md.startswith("# Demo")
    assert "| 1 | 21/09–27/09 | base |" in md
    assert "🔑" in md


def test_skill_examples_are_valid():
    import json

    examples = Path(__file__).parent.parent / ".claude" / "skills" / "coros-workout" / "examples"
    files = sorted(examples.glob("*.json"))
    assert len(files) >= 5
    for f in files:
        course = json.loads(f.read_text())
        sport = {1: "run", 2: "bike", 5: "trail"}[course["sportType"]]
        assert PL.validate_course(course, sport) == [], f.name


def test_example_plan_template_is_valid():
    example = Path(__file__).parent.parent / ".claude" / "skills" / "coros-coach" / "references" / "example-plan.yaml"
    errors, _ = PL.validate(PL.load_plan(example))
    assert errors == []
