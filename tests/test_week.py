import json
import re
from datetime import date

import recap as RC
import week as WK
import yaml

COURSE = {"sections": [
    {"sectionType": 1, "targetType": 2, "targetValue": 900},
    {"intervalGroup": True, "repeats": 2, "sets": [
        {"sectionType": 2, "targetType": 1, "targetValue": 1000, "intensityType": 2,
         "intensityValueStart": 220, "intensityValueEnd": 230},
        {"sectionType": 3, "targetType": 2, "targetValue": 120},
    ]},
    {"sectionType": 4, "targetType": 4},
]}


def make_plan() -> dict:
    return {
        "plan": {"id": "demo", "title": "Demo", "start": "2026-11-02", "weeks": 3},
        "weeks": [
            {"n": 1, "sessions": [
                {"id": "w1-sun", "date": "2026-11-08", "sport": "run", "type": "long", "status": "done",
                 "planned": {"duration_min": 80, "distance_km": 15}, "actual": {"distance_km": 14.2}}]},
            {"n": 2, "phase": "build", "focus": "Threshold", "sessions": [
                {"id": "w2-thu", "date": "2026-11-12", "sport": "run", "type": "tempo", "key": True,
                 "title": "Tempo", "planned": {"duration_min": 50, "distance_km": 10}, "status": "pushed"},
                {"id": "w2-mon", "date": "2026-11-09", "sport": "run", "type": "easy", "title": "Easy",
                 "planned": {"duration_min": 40, "distance_km": 7}, "status": "done", "feedback": "fine",
                 "actual": {"label_id": "SECRET-LABEL", "duration_min": 41, "distance_km": 7.2},
                 "coros": {"id_in_plan": "SECRET-COROS"}},
                {"id": "w2-tue", "date": "2026-11-10", "sport": "run", "type": "intervals", "key": True,
                 "title": "2 x 1000", "course": COURSE, "status": "missed",
                 "intervals": {"event_id": 987654}},
                {"id": "w2-wed", "date": "2026-11-11", "sport": "rest", "type": "rest"},
            ], "unplanned": [{"date": "2026-11-11", "sport": "Bouldering", "duration_min": 90}]},
            {"n": 3, "sessions": []},
        ],
    }


def test_week_for_clamps_to_plan():
    plan = make_plan()
    assert WK.week_for(plan, date(2026, 11, 11)) == 2
    assert WK.week_for(plan, date(2026, 11, 2)) == 1
    assert WK.week_for(plan, date(2026, 10, 1)) == 1
    assert WK.week_for(plan, date(2027, 3, 1)) == 3


def test_blocks_keep_repeats_and_targets():
    bl = WK.blocks({"course": COURSE}, threshold_s=240)
    assert [b["repeats"] for b in bl] == [1, 2, 1]
    work, rec = bl[1]["steps"]
    assert work["name"] == "Work" and work["length"] == "1 km" and work["target"] == "3:40–3:50/km"
    assert work["s"] == 225 and work["zone"] == 5            # 225 s/km: faster than the 240 threshold
    assert rec["kind"] == "jog" and rec["length"] == "2′" and rec["target"] == "5:17–5:48/km"   # recovery zone
    assert bl[0]["steps"][0]["target"] == "4:43–5:17/km"                   # warm-up: easy zone
    assert bl[2]["steps"][0]["length"] == RC.short_dur(WK.FREE_STEP_S) and bl[2]["steps"][0]["s"] == WK.FREE_STEP_S
    assert WK.total_seconds(bl) == 900 + 2 * (225 + 120) + WK.FREE_STEP_S


def test_blocks_without_course():
    assert WK.blocks({"type": "tempo", "planned": {"duration_min": 50, "target": "4:00/km"}}, None) == [
        {"repeats": 1, "steps": [{"name": "Work", "kind": "rep", "s": 3000, "zone": 3, "length": "50′",
                                  "target": "4:00/km"}]}]
    assert WK.blocks({"sport": "rest", "planned": {"duration_min": 20}}, None) == []


def test_easy_session_without_course_gets_zone_pace():
    bl = WK.blocks({"type": "easy", "planned": {"duration_min": 45, "target": "easy"}}, 240)
    assert bl[0]["steps"][0]["target"] == "4:43–5:17/km"
    bl = WK.blocks({"type": "recovery", "planned": {"duration_min": 30}}, 240)
    assert bl[0]["steps"][0]["kind"] == "jog" and bl[0]["steps"][0]["target"] == "5:17–5:48/km"
    bl = WK.blocks({"type": "easy", "planned": {"duration_min": 45, "target": "5:20–5:45/km"}}, 240)
    assert bl[0]["steps"][0]["target"] == "5:20–5:45/km"                   # the plan's own pace wins
    assert WK.blocks({"type": "easy", "planned": {"duration_min": 45}}, None)[0]["steps"][0]["target"] == ""


def test_build_data_sessions_and_overview():
    data = WK.build_data(make_plan(), 2, history=0)
    assert data["title"] == "Threshold"
    assert data["meta"].startswith("Week 2 of 3 · 9–15 Nov · Build phase")
    s = data["sessions"]
    assert [x["title"] for x in s] == ["Easy", "2 x 1000", "Tempo"]          # date order, rest day dropped
    assert [x["n"] for x in s] == [1, 2, 3] and all(x["of"] == 3 for x in s)
    assert s[0]["status_word"] == "Done" and s[0]["feedback"] == "fine"
    assert s[1]["status_level"] == "off" and s[1]["minutes"] == round(WK.total_seconds(s[1]["blocks"]) / 60)
    assert s[2]["status_word"] == "" and s[2]["difficulty"] == 3
    ov = {o["label"]: o for o in data["overview"]}
    assert ov["Sessions"]["value"] == "1" and ov["Sessions"]["of"] == "of 3"
    assert ov["Distance"]["value"] == "7.2" and ov["Distance"]["of"] == "of 17 km"
    assert data["volume"] is None


def test_volume_from_plan_and_from_activities():
    plan = make_plan()
    v = WK.volume(plan, 2, 6, None)
    assert [w["week"] for w in v["weeks"]] == [1, 2]                         # nothing before the plan offline
    assert v["weeks"][0] == {"start": "2026-11-02", "label": "2 Nov", "week": 1, "planned": 15.0,
                             "done": 14.2, "current": False}
    assert v["weeks"][1]["planned"] == 17.0 and v["weeks"][1]["current"] and v["avg"] == 14.2
    acts = [{"date": "2026-10-28", "sport": "Run", "sport_type": 100, "distance_km": 10},
            {"date": "2026-11-03", "sport": "Run", "sport_type": 100, "distance_km": 12},
            {"date": "2026-11-04", "sport": "Bouldering", "sport_type": 999, "distance_km": 0}]
    v = WK.volume(plan, 2, 3, acts)
    assert [w["done"] for w in v["weeks"]] == [10, 12, 0] and v["weeks"][0]["week"] is None
    assert v["source"] == "activities" and v["avg"] == 11.0


def test_no_internal_ids_in_page_data():
    blob = json.dumps(WK.build_data(make_plan(), 2, history=4))
    for secret in ("SECRET-LABEL", "SECRET-COROS", "987654", "label_id", "event_id"):
        assert secret not in blob


def test_render_escapes_and_embeds_data():
    data = WK.build_data(make_plan(), 2)
    data["title"] = "</script><b>x"
    page = WK.render_html(data)
    blob = re.search(r'id="week-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(blob)["title"] == "</script><b>x"
    assert "__DATA__" not in page and "&lt;/script&gt;" in page


def test_cli_writes_week_file(tmp_path, monkeypatch):
    (tmp_path / "plan.yaml").write_text(yaml.safe_dump(make_plan(), allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(WK.PL, "today", lambda: date(2026, 11, 11))
    assert WK.main(["build", "--plan", str(tmp_path), "--offline"]) == 0
    page = (tmp_path / "weeks" / "week-2.html").read_text(encoding="utf-8")
    assert '"title": "Threshold"' in page
    assert WK.main(["build", "--plan", str(tmp_path), "--week", "1", "--offline", "--out", str(tmp_path / "w1.html")]) == 0
    assert (tmp_path / "w1.html").exists()


def test_cli_falls_back_when_provider_fails(tmp_path, monkeypatch, capsys):
    (tmp_path / "plan.yaml").write_text(yaml.safe_dump(make_plan(), allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(WK.PL, "today", lambda: date(2026, 11, 11))

    def boom(*a):
        raise SystemExit("not logged in")
    monkeypatch.setattr(WK.PL, "fetch_activities", boom)
    assert WK.main(["build", "--plan", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["volume_source"] == "plan" and "not logged in" in out["warning"]
