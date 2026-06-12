"""
scaffold/execute.py — Astronomy catalog execution layer.

This is the ONLY place database writes happen.
The LLM produces validated action objects; this layer executes them deterministically.
Every query is scoped by user_id as defense-in-depth.
"""
from .db import get_supabase
from .schemas import AgentAction


def _fetch_names(sb, ids: list[str], user_id: str) -> list[str]:
    """Look up catalog_id + name for display in response."""
    res = (
        sb.table("celestial_objects")
        .select("id, catalog_id, name")
        .in_("id", ids)
        .eq("user_id", user_id)
        .execute()
    )
    rows = {row["id"]: row for row in (res.data or [])}
    labels = []
    for i in ids:
        row = rows.get(i)
        if row:
            label = row["catalog_id"]
            if row.get("name") and row["name"] != row["catalog_id"]:
                label += f' "{row["name"]}"'
            labels.append(label)
        else:
            labels.append(i)
    return labels


def execute_actions(actions: list[AgentAction], user_id: str) -> dict:
    """
    Execute a list of validated actions against the celestial_objects table.
    Returns a dict with aggregated 'message' and 'object_labels' for display.
    """
    sb = get_supabase()
    all_messages = []
    all_labels = []

    for action in actions:
        match action.action_type:
            case "UPDATE_STATUS":
                ids = [str(i) for i in action.target_object_ids]
                labels = _fetch_names(sb, ids, user_id)
                sb.table("celestial_objects") \
                  .update({"observation_status": action.new_status}) \
                  .in_("id", ids) \
                  .eq("user_id", user_id) \
                  .execute()
                obj_list = "\n".join(f"  • {l}" for l in labels)
                all_messages.append(f"Set {len(ids)} object(s) → **{action.new_status}**:\n{obj_list}")
                all_labels.extend(labels)

            case "UPDATE_PRIORITY":
                ids = [str(i) for i in action.target_object_ids]
                labels = _fetch_names(sb, ids, user_id)
                sb.table("celestial_objects") \
                  .update({"priority": action.new_priority}) \
                  .in_("id", ids) \
                  .eq("user_id", user_id) \
                  .execute()
                obj_list = "\n".join(f"  • {l}" for l in labels)
                all_messages.append(f"Set {len(ids)} object(s) → **{action.new_priority}** priority:\n{obj_list}")
                all_labels.extend(labels)

            case "LOG_OBJECT":
                sb.table("celestial_objects").insert({
                    "user_id": user_id,
                    "catalog_id": action.catalog_id,
                    "name": action.name,
                    "object_type": action.object_type,
                    "observation_status": action.observation_status,
                    "priority": action.priority,
                    "magnitude": action.magnitude,
                    "distance_ly": action.distance_ly,
                    "tags": action.tags,
                    "notes": action.notes,
                }).execute()
                label = action.catalog_id + (f' "{action.name}"' if action.name else "")
                all_messages.append(
                    f"Logged: **{label}** — {action.object_type}\n"
                    f"  Status: {action.observation_status} | Priority: {action.priority}"
                )
                all_labels.append(label)

            case "FLAG_ANOMALY":
                ids = [str(i) for i in action.target_object_ids]
                labels = _fetch_names(sb, ids, user_id)
                sb.table("celestial_objects") \
                  .update({
                      "observation_status": "Anomalous",
                      "notes": action.anomaly_note,
                  }) \
                  .in_("id", ids) \
                  .eq("user_id", user_id) \
                  .execute()
                obj_list = "\n".join(f"  • {l}" for l in labels)
                all_messages.append(
                    f"⚠️ Flagged {len(ids)} object(s) as **Anomalous**:\n{obj_list}\n\n"
                    f"*Note recorded:* {action.anomaly_note}"
                )
                all_labels.extend(labels)

            case "CLARIFICATION_NEEDED":
                all_messages.append(action.message_to_user)

            case _:
                raise ValueError(f"Unhandled action_type: {action.action_type!r}")

    return {
        "message": "\n\n---\n\n".join(all_messages),
        "object_labels": all_labels,
    }
