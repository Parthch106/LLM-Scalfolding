"""
tests/test_validate.py

Unit tests for the 4-stage validation gate.
Run with: pytest tests/ -v

These tests mock the database to test stages 1–2 without a real Supabase connection.
Integration tests (stages 3–4) require a real SUPABASE_URL + SUPABASE_KEY.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

# Set dummy env vars before importing scaffold modules
import os
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("GITHUB_TOKEN", "test-token")

from scaffold.validate import validate_action

DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
REAL_TASK_ID = "11111111-1111-1111-1111-111111111111"


# ── Stage 1: JSON Syntax ──────────────────────────────────────────────────────

def test_valid_create_task_passes_syntax():
    """Well-formed JSON should not fail at stage 1."""
    raw = json.dumps({
        "action_type": "CREATE_TASK",
        "reasoning": "User asked to create a task",
        "title": "Write tests",
    })
    # Stage 2+ may fail but stage 1 should pass
    result = validate_action(raw, DEMO_USER_ID)
    assert result.get("stage") != "syntax"


def test_malformed_json_fails_at_syntax():
    """Malformed JSON must be caught at stage 1, not crash."""
    result = validate_action("this is not json {{{", DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "syntax"


def test_empty_string_fails_at_syntax():
    result = validate_action("", DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "syntax"


def test_markdown_wrapped_json_fails_at_syntax():
    """LLM sometimes wraps output in ```json fences — must fail, not crash."""
    raw = "```json\n{\"action_type\": \"CREATE_TASK\"}\n```"
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "syntax"


# ── Stage 2: Pydantic Schema ──────────────────────────────────────────────────

def test_invalid_status_fails_at_schema():
    """An invalid status like 'Almost Done' must be caught at stage 2."""
    raw = json.dumps({
        "action_type": "UPDATE_STATUS",
        "reasoning": "test",
        "target_task_ids": [REAL_TASK_ID],
        "new_status": "Almost Done",  # not in the enum
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


def test_invalid_priority_fails_at_schema():
    raw = json.dumps({
        "action_type": "UPDATE_PRIORITY",
        "reasoning": "test",
        "target_task_ids": [REAL_TASK_ID],
        "new_priority": "ASAP",  # not in the enum
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


def test_unknown_action_type_fails_at_schema():
    raw = json.dumps({
        "action_type": "NUKE_DATABASE",
        "reasoning": "test",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


def test_missing_required_field_fails_at_schema():
    """CREATE_TASK requires a title."""
    raw = json.dumps({
        "action_type": "CREATE_TASK",
        "reasoning": "test",
        # missing "title"
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


def test_malformed_uuid_fails_at_schema():
    """task IDs must be valid UUIDs."""
    raw = json.dumps({
        "action_type": "UPDATE_STATUS",
        "reasoning": "test",
        "target_task_ids": ["not-a-uuid"],
        "new_status": "Done",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


def test_empty_target_task_ids_fails_at_schema():
    """target_task_ids must have at least 1 item."""
    raw = json.dumps({
        "action_type": "UPDATE_STATUS",
        "reasoning": "test",
        "target_task_ids": [],
        "new_status": "Done",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


def test_delete_without_confirmation_fails_at_schema():
    """DELETE_TASK requires confirmation_required: true."""
    raw = json.dumps({
        "action_type": "DELETE_TASK",
        "reasoning": "test",
        "target_task_ids": [REAL_TASK_ID],
        # missing "confirmation_required": true
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "schema"


# ── Stage 3: Business Rules (mocked DB) ──────────────────────────────────────

@patch("scaffold.validate.get_supabase")
def test_nonexistent_task_id_fails_at_business(mock_get_sb):
    """Task IDs that don't exist in the DB must be caught at stage 3."""
    mock_sb = MagicMock()
    mock_get_sb.return_value = mock_sb
    # DB returns empty result — no tasks found
    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    raw = json.dumps({
        "action_type": "UPDATE_STATUS",
        "reasoning": "test",
        "target_task_ids": [REAL_TASK_ID],
        "new_status": "Done",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "business"


# ── Stage 4: Authorization (mocked DB) ───────────────────────────────────────

@patch("scaffold.validate.get_supabase")
def test_cross_user_task_fails_at_auth(mock_get_sb):
    """Tasks owned by another user must be rejected at stage 4."""
    mock_sb = MagicMock()
    mock_get_sb.return_value = mock_sb
    # Task exists but belongs to a different user
    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": REAL_TASK_ID, "user_id": OTHER_USER_ID}
    ]

    raw = json.dumps({
        "action_type": "UPDATE_STATUS",
        "reasoning": "test",
        "target_task_ids": [REAL_TASK_ID],
        "new_status": "Done",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is False
    assert result["stage"] == "auth"


# ── Happy Path ────────────────────────────────────────────────────────────────

@patch("scaffold.validate.get_supabase")
def test_valid_update_status_passes_all_stages(mock_get_sb):
    """A fully valid action should pass all 4 stages."""
    mock_sb = MagicMock()
    mock_get_sb.return_value = mock_sb
    mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": REAL_TASK_ID, "user_id": DEMO_USER_ID}
    ]

    raw = json.dumps({
        "action_type": "UPDATE_STATUS",
        "reasoning": "User asked to mark the task as done",
        "target_task_ids": [REAL_TASK_ID],
        "new_status": "Done",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is True
    assert result["action"].action_type == "UPDATE_STATUS"


def test_valid_create_task_no_db_needed():
    """CREATE_TASK doesn't reference existing IDs — no DB call needed."""
    raw = json.dumps({
        "action_type": "CREATE_TASK",
        "reasoning": "User asked to create a new task",
        "title": "Write unit tests",
        "priority": "High",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is True
    assert result["action"].action_type == "CREATE_TASK"


def test_clarification_needed_no_db_needed():
    """CLARIFICATION_NEEDED doesn't touch the DB."""
    raw = json.dumps({
        "action_type": "CLARIFICATION_NEEDED",
        "reasoning": "The request was ambiguous",
        "message_to_user": "Which tasks did you want to delete?",
    })
    result = validate_action(raw, DEMO_USER_ID)
    assert result["valid"] is True
    assert result["action"].action_type == "CLARIFICATION_NEEDED"
