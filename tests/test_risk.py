import pandas as pd

from railblock.data import load_demo_data
from railblock.risk import (
    assess_assets,
    calculate_asset_risk,
    get_risk_level,
    priority_number_for_level,
    suggest_priority,
)


def test_low_risk_asset_scores_low():
    result = calculate_asset_risk({"asset_id": "A-TEST", "condition_score": 95, "last_maintenance_days": 5})
    assert result["risk_level"] == "LOW"
    assert 0 <= result["risk_score"] <= 24


def test_medium_risk_asset_scores_medium():
    result = calculate_asset_risk({"asset_id": "A-TEST", "condition_score": 70, "last_maintenance_days": 90})
    assert result["risk_level"] == "MEDIUM"


def test_high_risk_asset_scores_high():
    result = calculate_asset_risk({"asset_id": "A-TEST", "condition_score": 40, "last_maintenance_days": 150})
    assert result["risk_level"] == "HIGH"


def test_critical_risk_asset_scores_critical():
    result = calculate_asset_risk({"asset_id": "A-TEST", "condition_score": 10, "last_maintenance_days": 400})
    assert result["risk_level"] == "CRITICAL"
    assert result["risk_score"] >= 75


def test_missing_optional_columns_does_not_crash():
    result = calculate_asset_risk({"asset_id": "A-TEST", "condition_score": 60})
    assert 0 <= result["risk_score"] <= 100
    assert any("not present" in factor for factor in result["factors"])


def test_missing_all_columns_returns_zero_risk():
    result = calculate_asset_risk({"asset_id": "A-TEST"})
    assert result["risk_score"] == 0.0
    assert result["risk_level"] == "LOW"


def test_invalid_and_null_values_are_ignored_not_crashed():
    result = calculate_asset_risk(
        {"asset_id": "A-TEST", "condition_score": float("nan"), "last_maintenance_days": "not-a-number"}
    )
    assert result["risk_score"] == 0.0


def test_risk_score_always_within_bounds():
    extreme_cases = [
        {"condition_score": -500, "last_maintenance_days": 100000},
        {"condition_score": 500, "last_maintenance_days": -50},
        {"condition_score": 0, "last_maintenance_days": 0},
    ]
    for case in extreme_cases:
        result = calculate_asset_risk({"asset_id": "A-TEST", **case})
        assert 0 <= result["risk_score"] <= 100


def test_get_risk_level_thresholds():
    assert get_risk_level(0) == "LOW"
    assert get_risk_level(24) == "LOW"
    assert get_risk_level(25) == "MEDIUM"
    assert get_risk_level(49) == "MEDIUM"
    assert get_risk_level(50) == "HIGH"
    assert get_risk_level(74) == "HIGH"
    assert get_risk_level(75) == "CRITICAL"
    assert get_risk_level(100) == "CRITICAL"


def test_suggest_priority_matches_risk_level():
    for score in (10, 30, 60, 90):
        assert suggest_priority(score) == get_risk_level(score)


def test_ai_priority_never_overwrites_manual_priority():
    data = load_demo_data()
    requests_before = data["requests"]["priority"].copy()
    for _, asset_row in data["assets"].iterrows():
        calculate_asset_risk(asset_row)
    pd.testing.assert_series_equal(requests_before, data["requests"]["priority"])
    assert "priority" not in calculate_asset_risk(data["assets"].iloc[0])


def test_assess_assets_covers_every_asset_without_mutating_input():
    data = load_demo_data()
    original = data["assets"].copy()
    risk_table = assess_assets(data["assets"])
    pd.testing.assert_frame_equal(original, data["assets"])
    assert set(risk_table["asset_id"]) == set(data["assets"]["asset_id"])
    assert risk_table["risk_score"].between(0, 100).all()


def test_priority_number_for_level_spans_the_manual_1_to_5_scale():
    assert priority_number_for_level("LOW") == 1
    assert priority_number_for_level("MEDIUM") == 2
    assert priority_number_for_level("HIGH") == 4
    assert priority_number_for_level("CRITICAL") == 5
    for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        assert 1 <= priority_number_for_level(level) <= 5


def test_priority_number_for_unknown_level_falls_back_safely():
    assert priority_number_for_level("NOT_A_LEVEL") == 3


def test_real_demo_assets_do_not_crash():
    data = load_demo_data()
    for _, asset_row in data["assets"].iterrows():
        result = calculate_asset_risk(asset_row)
        assert 0 <= result["risk_score"] <= 100
        assert result["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
