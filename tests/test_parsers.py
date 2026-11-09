from pathlib import Path

import parsers as P

FIX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return (FIX / f"{name}.txt").read_text(encoding="utf-8")


def test_time_helpers():
    assert P.hms_to_seconds("42:18") == 2538
    assert P.hms_to_seconds("1:00:03") == 3603
    assert P.pace_to_seconds("4:05 /km") == 245
    assert P.seconds_to_pace(245) == "4:05"


def test_sport_records():
    acts = P.parse_sport_records(fx("sport_records"))
    assert len(acts) == 12
    run = acts[1]
    assert run["date"] == "2026-09-30"
    assert run["sport_type"] == 100
    assert run["duration_s"] == 2566
    assert run["distance_km"] == 7.42
    assert run["avg_pace_s"] == 346
    assert run["avg_hr"] == 147
    assert run["label_id"] == "900000000000000001"
    boulder = acts[0]
    assert boulder["distance_km"] is None and boulder["avg_hr"] == 94
    assert P.sport_family(boulder["sport_type"]) == "other"
    assert P.sport_family(run["sport_type"]) == "run"


def test_fitness():
    fit = P.parse_fitness(fx("fitness"))
    assert fit["vo2max"] == 57
    assert fit["threshold_pace"] == "4:14"
    assert fit["predictions"]["marathon"] == "3:16:45"


def test_training_load_sorted_oldest_first():
    rows = P.parse_training_load(fx("training_load"))
    assert len(rows) == 28
    assert rows[0]["date"] < rows[-1]["date"]
    assert rows[-1] == {"date": "2026-10-03", "comment": "Performance", "short_term": 45, "long_term": 62,
                        "ratio": 0.73}


def test_sleep_hrv():
    rows = P.parse_sleep_hrv(fx("sleep_hrv"))
    assert len(rows) == 7
    assert rows[-1]["hrv"] == 45 and rows[-1]["low"] == 49 and rows[-1]["status"] == "Below normal"


def test_resting_hr_handles_no_data():
    rows = P.parse_resting_hr(fx("resting_hr"))
    assert len(rows) == 30
    assert any(r["rhr"] is None for r in rows)
    assert rows[-1] == {"date": "2026-10-03", "rhr": 57}


def test_sleep_overview():
    rows = P.parse_sleep_overview(fx("sleep_overview"))
    assert len(rows) == 14
    last = rows[-1]
    assert last["date"] == "2026-10-03" and last["score"] == 63 and last["sleep_min"] == 382
    missing = next(r for r in rows if r["date"] == "2026-09-26")
    assert missing["score"] is None and missing["sleep_min"] is None


def test_recovery_and_detail():
    assert P.parse_recovery(fx("recovery"))["recovery_pct"] == 100
    det = P.parse_activity_detail(fx("activity_detail"))
    assert det["training_load"] == 114
    assert det["avg_hr"] == 147
    assert det["anaerobic_te"] == 2.8


def test_schedule_and_created_id():
    entries = P.parse_schedule(fx("schedule"))
    assert len(entries) == 7
    assert sum(e["standalone"] for e in entries) == 1
    assert P.parse_created_id(fx("create_result")) == "12345"


def test_hikes_are_not_runs():
    assert P.sport_family(104) == "hike"
    assert P.sport_family(102) == "trail"
