import pandas as pd

from railblock.coordination import (
    build_optimization_proposal,
    check_group_compatibility,
    department_label,
    detect_coordination_opportunities,
    summarize_opportunities,
)
from railblock.data import load_demo_data


def _row(**overrides):
    base = {
        "request_id": "MR-X",
        "section_id": "SEC-A",
        "department": "Engineering",
        "duration_min": 60,
        "earliest_start": 60,
        "latest_end": 420,
        "crew_id": "CREW-E1",
    }
    base.update(overrides)
    return pd.Series(base)


def _windows(section_id="SEC-A", start_min=60, end_min=420):
    return pd.DataFrame(
        [{"window_id": "W-TEST", "section_id": section_id, "start_min": start_min, "end_min": end_min, "line_capacity": 1}]
    )


def test_same_section_compatible_jobs_are_detected():
    a = _row(request_id="MR-A", department="Engineering", crew_id="CREW-E1", duration_min=60, earliest_start=60, latest_end=300)
    b = _row(request_id="MR-B", department="S&T", crew_id="CREW-S1", duration_min=45, earliest_start=60, latest_end=300)
    result = check_group_compatibility([a, b], _windows())
    assert result["compatible"] is True
    assert result["section"] == "SEC-A"


def test_different_section_jobs_are_not_grouped():
    requests_df = pd.DataFrame(
        [
            _row(request_id="MR-A", section_id="SEC-A", department="Engineering", crew_id="CREW-E1", earliest_start=60, latest_end=300),
            _row(request_id="MR-B", section_id="SEC-B", department="S&T", crew_id="CREW-S1", earliest_start=60, latest_end=300),
        ]
    )
    windows_df = pd.concat([_windows("SEC-A"), _windows("SEC-B")], ignore_index=True)
    groups = detect_coordination_opportunities(requests_df, windows_df)
    assert groups == []

    mixed_section_result = check_group_compatibility(
        [
            _row(request_id="MR-A", section_id="SEC-A", department="Engineering"),
            _row(request_id="MR-B", section_id="SEC-B", department="S&T"),
        ],
        _windows(),
    )
    assert mixed_section_result["compatible"] is False
    assert "same section" in mixed_section_result["reason"]


def test_different_departments_are_recognized():
    assert department_label("Electrical") == "Traction"
    assert department_label("Engineering") == "Engineering"
    assert department_label("S&T") == "S&T"


def test_incompatible_jobs_are_rejected_same_department():
    result = check_group_compatibility(
        [
            _row(request_id="MR-A", department="Engineering", crew_id="CREW-E1"),
            _row(request_id="MR-B", department="Engineering", crew_id="CREW-E2"),
        ],
        _windows(),
    )
    assert result["compatible"] is False
    assert "same department" in result["reason"]


def test_incompatible_jobs_are_rejected_same_crew():
    result = check_group_compatibility(
        [
            _row(request_id="MR-A", department="Engineering", crew_id="CREW-E1"),
            _row(request_id="MR-B", department="S&T", crew_id="CREW-E1"),
        ],
        _windows(),
    )
    assert result["compatible"] is False
    assert "same crew" in result["reason"]


def test_incompatible_jobs_are_rejected_no_overlap():
    result = check_group_compatibility(
        [
            _row(request_id="MR-A", department="Engineering", crew_id="CREW-E1", earliest_start=60, latest_end=150),
            _row(request_id="MR-B", department="S&T", crew_id="CREW-S1", earliest_start=300, latest_end=420),
        ],
        _windows(),
    )
    assert result["compatible"] is False
    assert "do not overlap" in result["reason"]


def test_incompatible_jobs_are_rejected_no_hosting_window():
    result = check_group_compatibility(
        [
            _row(request_id="MR-A", department="Engineering", crew_id="CREW-E1", duration_min=90, earliest_start=60, latest_end=420),
            _row(request_id="MR-B", department="S&T", crew_id="CREW-S1", duration_min=75, earliest_start=180, latest_end=540),
        ],
        _windows(start_min=60, end_min=360),
    )
    assert result["compatible"] is False
    assert "candidate window" in result["reason"]


def test_possession_savings_are_calculated_correctly():
    a = _row(request_id="MR-A", department="Engineering", crew_id="CREW-E1", duration_min=60, earliest_start=60, latest_end=300)
    b = _row(request_id="MR-B", department="S&T", crew_id="CREW-S1", duration_min=45, earliest_start=60, latest_end=300)
    c = _row(request_id="MR-C", department="Electrical", crew_id="CREW-O1", duration_min=30, earliest_start=60, latest_end=300)
    result = check_group_compatibility([a, b, c], _windows())
    assert result["compatible"] is True
    assert result["combined_duration_minutes"] == 60
    assert result["individual_duration_minutes"] == 135
    assert result["estimated_possession_reduction_minutes"] == 75


def test_real_demo_data_finds_the_grounded_sec_c_opportunity():
    data = load_demo_data()
    groups = detect_coordination_opportunities(data["requests"], data["windows"])
    assert len(groups) == 1
    group = groups[0]
    assert group["section"] == "SEC-C"
    assert set(group["request_ids"]) == {"MR-001", "MR-006"}
    assert group["estimated_possession_reduction_minutes"] == 60
    summary = summarize_opportunities(groups)
    assert summary["opportunity_count"] == 1
    assert summary["total_estimated_reduction_minutes"] == 60


def test_detect_coordination_opportunities_does_not_mutate_input():
    data = load_demo_data()
    requests_before = data["requests"].copy()
    windows_before = data["windows"].copy()
    detect_coordination_opportunities(data["requests"], data["windows"])
    pd.testing.assert_frame_equal(requests_before, data["requests"])
    pd.testing.assert_frame_equal(windows_before, data["windows"])


def test_build_optimization_proposal_is_a_preview_only_and_never_optimizes():
    data = load_demo_data()
    groups = detect_coordination_opportunities(data["requests"], data["windows"])
    assert groups, "expected the grounded SEC-C opportunity to exist"
    proposal = build_optimization_proposal(groups[0], data["requests"])
    assert proposal["group_id"] == groups[0]["group_id"]
    assert set(proposal["request_ids"]) == set(groups[0]["request_ids"])
    assert proposal["crews_involved"] == sorted(
        data["requests"][data["requests"].request_id.isin(groups[0]["request_ids"])].crew_id.unique().tolist()
    )
    assert len(proposal["crews_involved"]) == len(groups[0]["request_ids"]), "distinct crews required for a joint block"
    assert proposal["combined_duration_minutes"] == groups[0]["combined_duration_minutes"]
    assert "PROPOSAL ONLY" in proposal["status"]
    assert "not yet applied" in proposal["status"].lower()


def test_build_optimization_proposal_includes_a_shared_time_window():
    data = load_demo_data()
    groups = detect_coordination_opportunities(data["requests"], data["windows"])
    proposal = build_optimization_proposal(groups[0], data["requests"])
    assert proposal["shared_end_min"] > proposal["shared_start_min"]
    assert proposal["shared_end_min"] - proposal["shared_start_min"] == proposal["combined_duration_minutes"]
