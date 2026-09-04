import pandas as pd
import pytest

from railblock.approval import apply_approved_priorities, build_priority_review_table
from railblock.data import load_demo_data
from railblock.optimizer import optimize_blocks
from railblock.risk import assess_assets


def test_build_priority_review_table_shows_manual_and_ai_side_by_side():
    data = load_demo_data()
    risk_table = assess_assets(data["assets"])
    review = build_priority_review_table(data["requests"], risk_table)
    assert "priority" in review.columns  # manual
    assert "ai_suggested_priority" in review.columns
    assert "ai_suggested_priority_number" in review.columns
    assert review["ai_suggested_priority_number"].between(1, 5).all()


def test_approved_priority_overrides_only_the_approved_request():
    data = load_demo_data()
    original_priority = data["requests"][data["requests"].request_id == "MR-003"].priority.iloc[0]
    updated = apply_approved_priorities(data["requests"], {"MR-001": 5})
    assert updated[updated.request_id == "MR-001"].priority.iloc[0] == 5
    # every other request's priority is untouched
    assert updated[updated.request_id == "MR-003"].priority.iloc[0] == original_priority


def test_approved_priority_does_not_mutate_original_dataframe():
    data = load_demo_data()
    original = data["requests"].copy()
    apply_approved_priorities(data["requests"], {"MR-001": 5})
    pd.testing.assert_frame_equal(original, data["requests"])


def test_approved_priority_unknown_request_id_fails_gracefully():
    data = load_demo_data()
    with pytest.raises(ValueError):
        apply_approved_priorities(data["requests"], {"MR-DOES-NOT-EXIST": 5})


def test_optimizer_ignores_approved_priorities_unless_explicitly_applied():
    """The optimizer NEVER automatically uses AI priority — only a caller
    that explicitly builds and passes an approved-priority DataFrame does."""
    data = load_demo_data()
    baseline_result = optimize_blocks(data["requests"], data["trains"], data["windows"])

    # Merely computing an approval decision must not change what optimize_blocks
    # sees unless the caller explicitly re-optimizes with the updated frame.
    apply_approved_priorities(data["requests"], {"MR-006": 5})
    unaffected_result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    pd.testing.assert_frame_equal(
        baseline_result.plan.sort_values("request_id").reset_index(drop=True),
        unaffected_result.plan.sort_values("request_id").reset_index(drop=True),
    )


def test_rejected_ai_priority_leaves_manual_priority_in_place():
    """'Rejecting' is simply not calling apply_approved_priorities — the
    request keeps its manual priority and the optimizer behaves unchanged."""
    data = load_demo_data()
    result_without_approval = optimize_blocks(data["requests"], data["trains"], data["windows"])
    manual_priority = data["requests"][data["requests"].request_id == "MR-006"].priority.iloc[0]
    assert result_without_approval.plan[result_without_approval.plan.request_id == "MR-006"].priority.iloc[0] == manual_priority


def test_applying_an_approved_priority_can_change_the_optimized_plan():
    data = load_demo_data()
    # Boost a low-priority request to the maximum and confirm the override
    # actually reaches the optimizer's `priority` column it optimizes on.
    updated_requests = apply_approved_priorities(data["requests"], {"MR-006": 5})
    result = optimize_blocks(updated_requests, data["trains"], data["windows"])
    assert result.plan[result.plan.request_id == "MR-006"].priority.iloc[0] == 5
