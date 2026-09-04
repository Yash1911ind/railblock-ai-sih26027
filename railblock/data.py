"""Load deterministic demonstration data."""
from pathlib import Path
from typing import Any
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_demo_data(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    """Return synthetic demo inputs; none are official railway records."""
    files = {"assets":"assets.csv", "requests":"maintenance_requests.csv", "trains":"trains.csv", "windows":"candidate_windows.csv", "resources":"resources.csv"}
    return {name: pd.read_csv(data_dir / filename) for name, filename in files.items()}

def hhmm(minutes: int) -> str:
    minutes = int(minutes) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# Optional asset columns the risk engine (railblock/risk.py) will use if
# present, and their labels for the Data Quality panel.
OPTIONAL_ASSET_RISK_COLUMNS: dict[str, str] = {
    "Condition Score": "condition_score",
    "Maintenance Age": "last_maintenance_days",
    "Traffic Load": "traffic_load_score",
    "Failure History": "historical_failure_count",
}


def data_quality_report(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """A read-only summary of what is actually loaded, for the Data Quality
    panel. Never mutates `data` and never touches the source CSV files.
    """
    record_counts = {name: len(df) for name, df in data.items()}
    missing_values = {name: int(df.isna().sum().sum()) for name, df in data.items()}
    assets = data.get("assets")
    optional_columns_present = {
        label: bool(assets is not None and column in assets.columns)
        for label, column in OPTIONAL_ASSET_RISK_COLUMNS.items()
    }
    return {
        "record_counts": record_counts,
        "missing_values": missing_values,
        "optional_risk_columns": optional_columns_present,
        "data_mode": "SYNTHETIC DEMO DATA",
    }
