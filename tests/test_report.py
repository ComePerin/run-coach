from datetime import date
from pathlib import Path

import parsers as P
import plan as PL
import report as RP
from test_plan import make_plan

FIX = Path(__file__).parent / "fixtures"


def fixture_inputs():
    def fx(name):
        return (FIX / f"{name}.txt").read_text(encoding="utf-8")

    return {
        "fitness": P.parse_fitness(fx("fitness")),
        "load": P.parse_training_load(fx("training_load")),
        "hrv": P.parse_sleep_hrv(fx("sleep_hrv")),
        "rhr": P.parse_resting_hr(fx("resting_hr")),
        "sleep": P.parse_sleep_overview(fx("sleep_overview")),
        "recovery": P.parse_recovery(fx("recovery")),
        "activities": P.parse_sport_records(fx("sport_records")),
    }


def test_weekly_volume():
    rows = RP.weekly_volume(fixture_inputs()["activities"], 2, date(2026, 10, 3))
    assert [r["week_start"] for r in rows] == ["2026-09-21", "2026-09-28"]
    assert rows[0]["run_km"] == round(8.87 + 11.4 + 7.79 + 11.55 + 5.98, 1)
    assert rows[1]["partial"] is True  # week of 28/09 ends after 03/10
    assert "hike" not in rows[0]["by_family"]  # the 20/09 hike belongs to the previous week
    assert "other" in rows[0]["by_family"]


def test_report_without_plan():
    md = RP.build_report(fixture_inputs(), None, 2, date(2026, 10, 3))
    assert md.startswith("# Training report — Training")
    assert "## Training volume — last 2 weeks" in md
    assert "Excessive* on" in md
    assert "🟡 yellow" in md
    assert "Plan progress" not in md
    assert "<!-- COACH:" in md


def test_report_with_plan():
    data = fixture_inputs()
    plan = make_plan()
    plan["weeks"][1]["sessions"][0]["date"] = "2026-09-28"
    plan["plan"]["goal"] = {"distance": "half", "date": "2026-12-06", "target_time": "1:22:00"}
    PL.match_activities(plan, data["activities"], until=date(2026, 10, 2))
    md = RP.build_report(data, plan, 2, date(2026, 10, 2))
    assert "## Plan progress" in md
    assert "COROS prediction today: **1:33:20**" in md
    assert "Key sessions completed: 2/2" in md
    assert "| 2 ◀ |" in md
    assert "### Key sessions" in md
