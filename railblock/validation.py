"""Independent conflict reporting for proposed plans."""
import pandas as pd

def validate_plan(plan: pd.DataFrame, trains: pd.DataFrame) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    scheduled = plan[plan["status"] == "Scheduled"] if not plan.empty else plan
    for _, block in scheduled.iterrows():
        if block.start_min < block.earliest_start or block.end_min > block.latest_end:
            conflicts.append({"type":"Window", "item":block.request_id, "detail":"Outside request window"})
        affected = trains[(trains.section_id == block.section_id) & (trains.start_min < block.end_min) & (trains.end_min > block.start_min)]
        for _, train in affected[~affected.can_delay.astype(bool)].iterrows():
            conflicts.append({"type":"Train", "item":block.request_id, "detail":f"Conflicts with protected {train.train_id}"})
    rows = list(scheduled.itertuples())
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            overlaps = left.start_min < right.end_min and right.start_min < left.end_min
            if overlaps and (left.section_id == right.section_id or left.crew_id == right.crew_id):
                reason = "section" if left.section_id == right.section_id else "crew"
                conflicts.append({"type":"Resource", "item":f"{left.request_id}/{right.request_id}", "detail":f"Overlapping {reason} use"})
    return conflicts
