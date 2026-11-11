import json
import re
from datetime import datetime, timezone

import pytest
import recap as RC

# The mock session of docs/mockups/session-recap.html: 5 x 1000 m at 3:39–3:46/km, 2'30 jog.
COURSE = {
    "courseName": "5 x 1000 m at I pace",
    "courseDescription": "15' easy, 5 x 1000 m at 3:39-3:46/km with 2'30 jog, 10' easy.",
    "sportType": 1,
    "sections": [
        {"sectionType": 1, "targetType": 2, "targetValue": 900},
        {"intervalGroup": True, "repeats": 4, "sets": [
            {"sectionType": 2, "targetType": 1, "targetValue": 1000, "intensityType": 2,
             "intensityValueStart": 219, "intensityValueEnd": 226},
            {"sectionType": 3, "targetType": 2, "targetValue": 150},
        ]},
        {"sectionType": 2, "targetType": 1, "targetValue": 1000, "intensityType": 2,
         "intensityValueStart": 219, "intensityValueEnd": 226},
        {"sectionType": 4, "targetType": 2, "targetValue": 600},
    ],
}

# (duration s, distance km, avg HR, max HR, FIT intensity)
LAPS = [
    (900, 3.0, 132, 141, "WARMUP"),
    (221, 1.0, 166, 171, "ACTIVE"), (150, 0.40, 148, 166, "REST"),
    (223, 1.0, 169, 175, "ACTIVE"), (150, 0.41, 151, 169, "REST"),
    (224, 1.0, 172, 178, "ACTIVE"), (150, 0.40, 154, 172, "REST"),
    (227, 1.0, 175, 181, "ACTIVE"), (150, 0.39, 157, 175, "REST"),
    (230, 1.0, 178, 184, "ACTIVE"),
    (600, 1.92, 141, 158, "COOLDOWN"),
]


def make_fit(laps=LAPS) -> bytes:
    """A minimal activity FIT file: one HR record per lap start and one lap message per step."""
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.lap_message import LapMessage
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.profile_type import FileType, Intensity, Manufacturer

    t = int(datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc).timestamp() * 1000)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.time_created = t
    builder = FitFileBuilder(auto_define=True)
    builder.add(fid)
    for dur, km, hr, hr_max, intensity in laps:
        rec = RecordMessage()
        rec.timestamp = t
        rec.heart_rate = hr
        builder.add(rec)
        lap = LapMessage()
        lap.start_time = t
        t += dur * 1000
        lap.timestamp = t
        lap.total_timer_time = float(dur)
        lap.total_elapsed_time = float(dur)
        lap.total_distance = km * 1000
        lap.enhanced_avg_speed = km * 1000 / dur
        lap.avg_heart_rate = hr
        lap.max_heart_rate = hr_max
        lap.intensity = getattr(Intensity, intensity)
        builder.add(lap)
    return builder.build().to_bytes()


def test_expand_course_names_and_bands():
    steps = RC.expand_course(COURSE)
    assert [s["name"] for s in steps] == ["Warm-up", "Rep 1", "Jog 1", "Rep 2", "Jog 2", "Rep 3", "Jog 3",
                                          "Rep 4", "Jog 4", "Rep 5", "Cool-down"]
    assert steps[1]["band"] == [219, 226] and steps[2]["band"] is None
    assert RC.rep_sub(steps) == "Target 3:39–3:46/km, 2′30 jog between reps."


def test_percent_of_threshold_band():
    sec = {"sectionType": 2, "targetType": 2, "targetValue": 600, "intensityType": 2,
           "intensityPercentStart": 100, "intensityPercentEnd": 105}
    steps = RC.expand_course({"sections": [sec]}, threshold_s=240)
    assert steps[0]["kind"] == "rep" and steps[0]["band"] == [229, 240]


def test_read_fit_laps():
    fit = RC.read_fit(make_fit())
    assert len(fit["laps"]) == 11
    rep1 = fit["laps"][1]
    assert rep1["pace_s"] == 221 and rep1["hr"] == 166 and rep1["hr_max"] == 171
    assert fit["laps"][0]["intensity"] == "warmup"
    assert len(fit["hr"]) == 11


def test_align_and_status():
    steps, warnings = RC.align(RC.expand_course(COURSE), RC.read_fit(make_fit())["laps"])
    assert warnings == []
    reps = [s for s in steps if s["kind"] == "rep"]
    assert [RC.status_of(s) for s in reps] == [0, 0, 0, 1, 4]


def test_align_count_mismatch_warns():
    laps = RC.read_fit(make_fit(LAPS[:-1]))["laps"]
    steps, warnings = RC.align(RC.expand_course(COURSE), laps)
    assert "10 laps for 11 planned steps" in warnings[0]
    assert steps[-1]["name"] == "Cool-down" and steps[-1]["pace"] is None  # planned time kept, no actual


def test_laps_without_plan_use_fit_intensity():
    steps, _ = RC.align([], RC.read_fit(make_fit())["laps"])
    assert [s["name"] for s in steps][:3] == ["Warm-up", "Rep 1", "Jog 1"]
    assert all(s["band"] is None for s in steps)


def test_build_data_matches_the_mock():
    planned = RC.expand_course(COURSE, threshold_s=235)
    steps, warnings = RC.align(planned, RC.read_fit(make_fit())["laps"])
    session = {
        "id": "w4-tue", "title": "5 × 1000 m at I pace", "key": True,
        "planned": {"duration_min": 55, "distance_km": 11},
        "actual": {"compliance_pct": 98, "training_load": 102, "aerobic_te": 3.4, "anaerobic_te": 2.6},
        "recap": {"verdict": "Séance réussie.", "lang": "fr", "rpe": 8, "rpe_expected": [7, 8],
                  "quote": "Jambes lourdes.", "tags": ["Heavy legs"],
                  "impact": [{"title": "Volume inchangé", "text": "La séance est validée."}]},
    }
    zones = RC.zones_block(steps, [12 * 60, 17 * 60, 6 * 60, 8 * 60, 645], 235, True)
    data = RC.build_data(steps=steps, title=session["title"], meta="Tue 10 Nov 2026", session=session,
                         planned=session["planned"], zones=zones, threshold_s=235, warnings=warnings)
    assert data["status"] == {"level": "mostly", "label": "Mostly on target"}
    assert data["status_bits"] == ["3 of 5 reps in target", "Compliance 98 %"]
    tiles = {t["label"]: t for t in data["tiles"]}
    assert tiles["Duration"]["value"] == "53:45" and tiles["Duration"]["delta"] == "−1:15"
    assert tiles["Avg rep pace"]["value"] == "3:45/km" and tiles["Avg rep pace"]["good"] is True
    assert data["hr_sub"].startswith("Average HR per rep. +12 bpm from rep 1 to rep 5 at similar pace")
    assert [z["actual"] for z in zones] == [12, 17, 6, 8, 10.8]
    assert zones[4]["intended"] > 0  # the reps are faster than threshold → Z5
    assert data["feel"]["rpe"] == 8 and data["impact"][0]["title"] == "Volume inchangé"


def test_context_only_uses_readiness_from_that_day():
    snap = {"date": "2026-11-10", "level": "yellow", "score": -1,
            "signals": {"hrv": {"score": -1, "detail": "HRV 52 ms below normal range (56-80)"},
                        "load": {"score": 0, "detail": "load ratio 1.12 (Optimal), short 300 / long 268"}}}
    ctx = RC.context_block(snap, {"training_load": 102}, "2026-11-10")
    assert ctx[0] == {"label": "Readiness", "value": "Yellow", "level": "yellow", "sub": "score -1"}
    assert ctx[1]["value"] == "52 ms" and "below normal range" in ctx[1]["sub"]
    assert ctx[-1] == {"label": "Training load", "value": "102", "sub": "load ratio 1.12 (Optimal)"}
    assert RC.context_block(snap, {}, "2026-11-11") == []


def test_render_escapes_and_embeds_data():
    data = RC.build_data(steps=[], title="</script><b>x", meta="m")
    page = RC.render_html(data)
    assert "</script><b>" not in page.split('id="recap-data"')[1].split("</script>")[0]
    blob = re.search(r'id="recap-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(blob)["title"] == "</script><b>x"
    assert "__DATA__" not in page and "&lt;/script&gt;" in page  # <title> is escaped


def test_cli_with_plan_and_fit(tmp_path):
    import yaml

    plan = {"plan": {"id": "demo", "title": "Demo", "start": "2026-11-09", "weeks": 9},
            "weeks": [{"n": 1, "phase": "build", "sessions": [
                {"id": "w1-tue", "date": "2026-11-10", "sport": "run", "type": "intervals", "key": True,
                 "title": "5 × 1000 m", "planned": {"duration_min": 55}, "course": COURSE, "status": "done"}]}]}
    (tmp_path / "plan.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
    fit = tmp_path / "a.fit"
    fit.write_bytes(make_fit())
    assert RC.main(["build", "--plan", str(tmp_path), "--session", "w1-tue", "--fit", str(fit)]) == 0
    page = (tmp_path / "recaps" / "2026-11-10-w1-tue.html").read_text(encoding="utf-8")
    assert "Mostly on target" in page and "Week 1 of 9" in page and "Build phase" in page


def test_unknown_session_exits(tmp_path):
    (tmp_path / "plan.yaml").write_text("plan: {id: d, title: D, start: '2026-11-09', weeks: 1}\nweeks: []\n")
    (tmp_path / "x.fit").write_bytes(make_fit())
    with pytest.raises(SystemExit):
        RC.main(["build", "--plan", str(tmp_path), "--session", "nope", "--fit", str(tmp_path / "x.fit")])
