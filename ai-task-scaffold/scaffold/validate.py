"""
scaffold/validate.py

The 4-stage validation gate — the heart of the project.
This is the file to walk an interviewer through.

Stage 1: JSON syntax    — can we parse the string at all?
Stage 2: Pydantic schema — does it match a known action type?
Stage 3: Business rules  — do the referenced task IDs actually exist?
Stage 4: Authorization   — does this user own all the targeted tasks?

The LLM never reaches the database. This gate is the only path.
"""
import json
from pydantic import TypeAdapter, ValidationError
from .schemas import AgentAction, ReActPayload
from .db import get_supabase

# Pre-built validators (fast, thread-safe)
_action_validator = TypeAdapter(AgentAction)
_react_validator = TypeAdapter(ReActPayload)


def validate_action(raw_output: str, user_id: str, secret_word: str | None = None) -> dict:
    """
    Validate an LLM-generated action string through all 4 stages.

    Returns:
        {"valid": True,  "action": <AgentAction instance>}
        {"valid": False, "stage": "syntax"|"schema"|"business"|"auth", "error": str}
    """
    # ── Stage 1: JSON Syntax ──────────────────────────────────────────────────
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "stage": "syntax",
            "error": f"Output was not valid JSON: {e}",
        }

    # ── Stage 2: ReAct Schema Validation ──────────────────────────────────────
    try:
        react_data = _react_validator.validate_json(raw_output, context={"secret_word": secret_word})
    except ValidationError as e:
        # Simplify the error structure for the LLM
        err_msgs = []
        for err in e.errors():
            loc = "->".join(str(l) for l in err["loc"]) if err.get("loc") else "root"
            err_msgs.append(f"[{loc}]: {err['msg']}")
            
        return {
            "valid": False,
            "stage": "schema",
            "error": "ReAct Schema Error: " + "; ".join(err_msgs),
        }

    actions = react_data.actions
    aggregated_errors = []

    # ── Stages 3 & 4: Business Rules + Authorization ──────────────────────────
    for idx, action in enumerate(actions):
        # Only run DB checks for actions that reference existing objects
        if hasattr(action, "target_object_ids"):
            sb = get_supabase()
            ids = [str(i) for i in action.target_object_ids]

            res = sb.table("celestial_objects").select("id, user_id").in_("id", ids).execute()
            data = res.data or []

            # Stage 3: All referenced IDs must exist
            if len(data) != len(ids):
                missing = set(ids) - {str(r["id"]) for r in data}
                aggregated_errors.append(
                    f"Action {idx+1} failed: Object IDs do not exist in the catalog: {list(missing)}"
                )
                continue

            # Stage 4: Simulate RLS auth check
            for row in data:
                if str(row["user_id"]) != user_id:
                    aggregated_errors.append(
                        f"Action {idx+1} failed: Unauthorized to edit object {row['id']}"
                    )
                    continue

    if aggregated_errors:
        return {
            "valid": False,
            "stage": "validation_gate",
            "error": "\n".join(aggregated_errors),
        }

    return {
        "valid": True,
        "actions": actions,
        "react_payload": react_data
    }
