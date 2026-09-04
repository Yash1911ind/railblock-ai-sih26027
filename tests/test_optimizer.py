from railblock.data import load_demo_data
from railblock.optimizer import baseline_plan, optimize_blocks

def test_optimized_plan_has_no_conflicts():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"])
    assert result.status in {"OPTIMAL", "FEASIBLE"}
    assert result.conflicts == []
    assert result.metrics["scheduled_requests"] >= 4

def test_baseline_exposes_demo_conflicts():
    data = load_demo_data()
    result = baseline_plan(data["requests"], data["trains"])
    assert len(result.conflicts) > 0

def test_replanning_is_safe():
    data = load_demo_data()
    result = optimize_blocks(data["requests"], data["trains"], data["windows"], cancelled_train_ids={"TR-101"})
    assert result.conflicts == []

