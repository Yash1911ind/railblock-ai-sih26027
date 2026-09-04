import pandas as pd

from railblock.data import data_quality_report, load_demo_data


def test_record_counts_match_actual_loaded_tables():
    data = load_demo_data()
    report = data_quality_report(data)
    for name, df in data.items():
        assert report["record_counts"][name] == len(df)


def test_data_mode_is_labeled_synthetic():
    data = load_demo_data()
    report = data_quality_report(data)
    assert report["data_mode"] == "SYNTHETIC DEMO DATA"


def test_optional_risk_columns_reflect_actual_csv_columns():
    data = load_demo_data()
    report = data_quality_report(data)
    # the real demo assets.csv has condition_score and last_maintenance_days,
    # but not traffic_load_score or historical_failure_count
    assert report["optional_risk_columns"]["Condition Score"] is True
    assert report["optional_risk_columns"]["Maintenance Age"] is True
    assert report["optional_risk_columns"]["Traffic Load"] is False
    assert report["optional_risk_columns"]["Failure History"] is False


def test_report_does_not_mutate_input_data():
    data = load_demo_data()
    originals = {name: df.copy() for name, df in data.items()}
    data_quality_report(data)
    for name, df in data.items():
        pd.testing.assert_frame_equal(df, originals[name])


def test_missing_values_are_counted_honestly():
    data = {
        "assets": pd.DataFrame({"asset_id": ["A-1", "A-2"], "condition_score": [90, None]}),
    }
    report = data_quality_report(data)
    assert report["missing_values"]["assets"] == 1
