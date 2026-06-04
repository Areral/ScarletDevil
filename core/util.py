# --- START OF FILE core/util.py ---
"""Shared small utilities used across the orchestrator."""
import uuid


def is_valid_uuid(val: str) -> bool:
    """Return True if *val* parses as a UUID."""
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False
