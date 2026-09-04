"""Explainable CP-SAT maintenance block planner."""
from dataclasses import dataclass
from time import perf_counter
import pandas as pd
from ortools.sat.python import cp_model
from .validation import validate_plan

@dataclass
class PlanningResult:
    plan: pd.DataFrame
    conflicts: list[dict[str, str]]
    metrics: dict[str, float | int | str]
    status: str
    solve_seconds: float
    options_by_request: dict[str, list[dict]] | None = None

def _overlap(start: int, end: int, row: pd.Series) -> int:
    return max(0, min(end, int(row.end_min)) - max(start, int(row.start_min)))

def _candidates(request, windows, trains, step=15):
    options = []
    for _, window in windows[windows.section_id == request.section_id].iterrows():
        lower = max(int(request.earliest_start), int(window.start_min))
        upper = min(int(request.latest_end), int(window.end_min)) - int(request.duration_min)
        for start in range(lower, upper + 1, step):
            end = start + int(request.duration_min)
            crossing = trains[(trains.section_id == request.section_id) & (trains.start_min < end) & (trains.end_min > start)]
            if any(~crossing.can_delay.astype(bool)):
                continue
            disruption = sum(_overlap(start, end, train) * int(train.importance) for _, train in crossing.iterrows())
            options.append({"start":start, "end":end, "disruption":disruption, "window_id":window.window_id})
    return options

def optimize_blocks(requests, trains, windows, *, time_limit=5.0, cancelled_train_ids=None):
    """Maximize priority-weighted maintenance subject to safety and capacity constraints."""
    started = perf_counter()
    active_trains = trains[~trains.train_id.isin(cancelled_train_ids or set())].copy()
    model, choices, options_by_request = cp_model.CpModel(), {}, {}
    for _, request in requests.iterrows():
        options = _candidates(request, windows, active_trains)
        options_by_request[request.request_id] = options
        variables = []
        for index in range(len(options)):
            variable = model.new_bool_var(f"choose_{request.request_id}_{index}")
            choices[(request.request_id, index)] = variable
            variables.append(variable)
        if variables:
            model.add(sum(variables) <= 1)

    request_rows = {row.request_id:row for row in requests.itertuples()}
    all_options = [(rid, i, option) for rid, options in options_by_request.items() for i, option in enumerate(options)]
    for pos, (left_id, left_idx, left) in enumerate(all_options):
        for right_id, right_idx, right in all_options[pos + 1:]:
            if left_id == right_id:
                continue
            left_request, right_request = request_rows[left_id], request_rows[right_id]
            overlaps = left["start"] < right["end"] and right["start"] < left["end"]
            shared = left_request.section_id == right_request.section_id or left_request.crew_id == right_request.crew_id
            if overlaps and shared:
                model.add(choices[(left_id,left_idx)] + choices[(right_id,right_idx)] <= 1)

    terms = []
    for _, request in requests.iterrows():
        for index, option in enumerate(options_by_request[request.request_id]):
            reward = int(request.priority) * int(request.duration_min) * 100
            penalty = option["disruption"] * 12 + max(0, option["start"] - int(request.earliest_start))
            terms.append((reward - penalty) * choices[(request.request_id,index)])
    if terms:
        model.maximize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    code = solver.solve(model)

    output, total_disruption = [], 0
    for _, request in requests.iterrows():
        selected = next((option for index, option in enumerate(options_by_request[request.request_id]) if solver.boolean_value(choices[(request.request_id,index)])), None)
        if selected:
            total_disruption += selected["disruption"]
            output.append({**request.to_dict(), **selected, "start_min":selected["start"], "end_min":selected["end"], "status":"Scheduled"})
        else:
            output.append({**request.to_dict(), "start_min":None, "end_min":None, "disruption":0, "window_id":None, "status":"Deferred"})
    plan = pd.DataFrame(output)
    scheduled = plan[plan.status == "Scheduled"]
    conflicts = validate_plan(plan, active_trains)
    requested = int(requests.duration_min.sum())
    completed = int(scheduled.duration_min.sum()) if not scheduled.empty else 0
    solve_seconds = perf_counter() - started
    metrics = {
        "scheduled_requests":len(scheduled), "total_requests":len(requests),
        "maintenance_completion_pct":round(100 * completed / requested, 1) if requested else 0,
        "protected_train_conflicts":sum(c["type"] == "Train" for c in conflicts),
        "weighted_disruption_minutes":int(total_disruption),
        "block_utilization_pct":round(100 * completed / max(1, int((windows.end_min - windows.start_min).sum())), 1),
        "planning_time_seconds":round(solve_seconds, 3),
    }
    return PlanningResult(
        plan, conflicts, metrics, solver.status_name(code), solve_seconds, options_by_request
    )

def baseline_plan(requests, trains):
    """Naive earliest-start plan used only as the simulated BEFORE state."""
    rows = []
    for _, request in requests.iterrows():
        start = int(request.earliest_start)
        rows.append({**request.to_dict(), "start_min":start, "end_min":start + int(request.duration_min), "status":"Scheduled", "disruption":0})
    plan = pd.DataFrame(rows)
    conflicts = validate_plan(plan, trains)
    metrics = {"scheduled_requests":len(plan), "total_requests":len(plan), "maintenance_completion_pct":100.0,
        "protected_train_conflicts":sum(c["type"] == "Train" for c in conflicts), "weighted_disruption_minutes":0,
        "block_utilization_pct":0, "planning_time_seconds":0.0}
    return PlanningResult(plan, conflicts, metrics, "MANUAL_BASELINE", 0.0)
