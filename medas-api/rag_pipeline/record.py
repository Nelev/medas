"""The patient records the pipeline indexes, and a lookup by id."""

import json
from pathlib import Path

__all__ = ["MEDICAL_HISTORY_PATH", "find_record", "load_record"]

# The seeded patient's record. Synthetic for now; see dataset/README.md.
MEDICAL_HISTORY_PATH = (
    Path(__file__).parent.parent / "dataset" / "records" / "medical_history.json"
)


def load_record() -> dict:
    with MEDICAL_HISTORY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def find_record(record_id: str) -> dict | None:
    """The record with this id, or None. One seeded record for now: any other
    id has none."""
    record = load_record()
    return record if record["id"] == record_id else None
