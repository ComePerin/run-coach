from pathlib import Path

import parsers as P
import readiness as R

FIX = Path(__file__).parent / "fixtures"


def hrv_row(value, low=55, high=80, baseline=68, day="2026-10-01"):
    return {"date": day, "hrv": value, "status": "", "low": low, "high": high, "baseline": baseline}


def test_hrv_rules():
    assert R.score_hrv([])[0] is None
    assert R.score_hrv([hrv_row(70), hrv_row(50)])[0] == -1
    assert R.score_hrv([hrv_row(50), hrv_row(50)])[0] == -2
    assert R.score_hrv([hrv_row(70), hrv_row(72), hrv_row(70)])[0] == 1
    assert R.score_hrv([hrv_row(90)])[0] == 0


def test_rhr_rules():
    base = [{"date": f"2026-09-{i:02d}", "rhr": 54} for i in range(1, 8)]
    assert R.score_rhr(base + [{"date": "2026-09-08", "rhr": 62}])[0] == -2
    assert R.score_rhr(base + [{"date": "2026-09-08", "rhr": 59}])[0] == -1
    assert R.score_rhr(base + [{"date": "2026-09-08", "rhr": 53}])[0] == 1
    assert R.score_rhr(base[:2])[0] is None


def test_sleep_rules():
    assert R.score_sleep([{"sleep_min": 330, "score": 80}])[0] == -2
    assert R.score_sleep([{"sleep_min": 400, "score": 80}])[0] == -1
    assert R.score_sleep([{"sleep_min": 480, "score": 90}])[0] == 1


def test_levels():
    green = R.compute([hrv_row(70)], [], [{"sleep_min": 480, "score": 90}], {"recovery_pct": 95}, [])
    assert green["level"] == "green"
    assert green["confidence"] == 0.6
    yellow = R.compute([hrv_row(50)], [], [{"sleep_min": 400, "score": 75}], {"recovery_pct": 100}, [])
    assert yellow["level"] == "yellow"
    red = R.compute([hrv_row(50), hrv_row(50)], [], [{"sleep_min": 400, "score": 75}], None, [])
    assert red["level"] == "red"


def test_fixture_snapshot():
    snap = R.compute(
        P.parse_sleep_hrv((FIX / "sleep_hrv.txt").read_text()),
        P.parse_resting_hr((FIX / "resting_hr.txt").read_text()),
        P.parse_sleep_overview((FIX / "sleep_overview.txt").read_text()),
        P.parse_recovery((FIX / "recovery.txt").read_text()),
        P.parse_training_load((FIX / "training_load.txt").read_text()),
    )
    assert snap["level"] == "yellow"
    assert snap["signals"]["hrv"]["score"] == -1
    assert snap["confidence"] == 1.0


def test_pace_zones_from_threshold():
    zones = R.pace_zones(235)  # 3:55/km
    assert zones["threshold"][0] < 235 < zones["threshold"][1]
    assert zones["interval"][1] < zones["threshold"][0]
    assert zones["easy"][0] > zones["marathon"][1]
