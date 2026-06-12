"""
scaffold/agent.py

The self-correction retry loop.
Wires together: LLM → validation gate → (retry if needed) → execution → audit log.

This is the orchestration layer — it contains no business logic itself.
"""
from .llm import parse_command
from .validate import validate_action
from .execute import execute_actions
from .db import log_action, get_catalog_for_context, search_catalog
import json

MAX_RETRIES = 8  # Increased to 8 to allow multi-turn RAG + self-corrections

# Memory buffer for dynamic few-shot error injection
_correction_memory = []


def run_agent(
    user_prompt: str,
    user_id: str,
    provider: str = "github",
    history: list = None,
    secret_word: str | None = None,
) -> dict:
    """
    Process a natural language command end-to-end.

    Returns:
        {
            "success": bool,
            "message": str,       # human-readable result or error
            "status":  str,       # "success" | "self_corrected" | "failed"
        }
    """
    catalog_context = get_catalog_for_context(user_id)
    attempts: list[dict] = []
    last_error: str | None = None

    for attempt in range(MAX_RETRIES + 1):
        # On retries, append the validation error to the prompt so the LLM can self-correct
        prompt = user_prompt
        if last_error:
            prompt += (
                f"\n\n[SYSTEM CORRECTION — attempt {attempt + 1}/{MAX_RETRIES + 1}]: "
                f"The JSON you just generated failed backend validation with this error: {last_error}\n"
                f"CRITICAL: Do NOT use CLARIFICATION_NEEDED to explain this backend error to the user. "
                f"You must fix your own JSON output to satisfy the backend's rule and resend it."
            )
            if _correction_memory:
                example = _correction_memory[-1]  # Use the most recent successful correction
                prompt += (
                    f"\n\n--- PAST EXPERIENCE ---\n"
                    f"Here is an example of how you successfully fixed an error in the past:\n"
                    f"PAST ERROR: {example['error']}\n"
                    f"SUCCESSFUL FIX (JSON): {example['correction']}\n"
                    f"-----------------------"
                )

        try:
            raw = parse_command(prompt, catalog_context, provider=provider, history=history)
        except Exception as e:
            attempts.append({
                "attempt": attempt,
                "raw": "",
                "stage": "api_error",
                "error": f"LLM API Error: {str(e)}",
                "valid": False,
            })
            break  # Fatal API error, stop retrying

        # ── INTERCEPT REACT & RAG SEARCH ──────────────────────────────────────
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                # UI Yield for Thought Process
                if "thought_process" in parsed:
                    attempts.append({
                        "attempt": attempt,
                        "raw": raw,
                        "stage": "thought",
                        "error": f"🧠 {parsed['thought_process']}",
                        "valid": False,
                    })

                actions_list = parsed.get("actions", [])
                search_actions = [a for a in actions_list if a.get("action_type") == "SEARCH_CATALOG"]
                if search_actions:
                    query = search_actions[0].get("search_query", "")
                    results = search_catalog(query, user_id)
                    user_prompt += f"\n\n[TOOL RESULT: SEARCH_CATALOG for '{query}']:\n{json.dumps(results, indent=2)}\n\nPlease proceed with your update actions using these UUIDs."
                    last_error = None
                    
                    attempts.append({
                        "attempt": attempt,
                        "raw": raw,
                        "stage": "rag_search",
                        "error": f"🔍 AI Searched Database: '{query}' -> Found {len(results)} results.",
                        "valid": False,
                    })
                    continue  # Loop again, feeding the results back to the LLM!
        except Exception:
            pass
        # ──────────────────────────────────────────────────────────────────────

        result = validate_action(raw, user_id, secret_word)
        attempts.append({
            "attempt": attempt,
            "raw": raw,
            "stage": result.get("stage"),
            "error": result.get("error"),
            "valid": result["valid"],
        })

        if result["valid"]:
            # Capture experience for Few-Shot Error Injection
            if attempt > 0:
                _correction_memory.append({
                    "error": last_error,
                    "correction": raw
                })

            # Valid syntax, valid schema, business rules passed, auth passed
            # -> Execute the transaction!
            exec_result = execute_actions(result["actions"], user_id)
            final_status = "success" if attempt == 0 else "self_corrected"

            log_action(
                user_id=user_id,
                user_prompt=user_prompt,
                attempts=attempts,
                final_status=final_status,
                executed_action=[a.model_dump(mode="json") for a in result["actions"]],
                provider=provider,
            )

            # Extract thought process for the final success message
            thought_process = result.get("react_payload").thought_process if "react_payload" in result else "No thoughts recorded."
            combined_reasoning = f"**🧠 Thought Process:** {thought_process}\n\n**Actions Taken:**\n"
            combined_reasoning += "\n".join(f"- {a.reasoning}" for a in result["actions"])

            return {
                "success": True,
                "message": exec_result["message"],
                "reasoning": combined_reasoning,
                "status": final_status,
                "attempts": attempts,
            }

        last_error = result["error"]

    # All retries exhausted
    log_action(
        user_id=user_id,
        user_prompt=user_prompt,
        attempts=attempts,
        final_status="failed",
        executed_action=None,
        provider=provider,
    )

    return {
        "success": False,
        "message": f"AI could not produce a valid action after {MAX_RETRIES} retries. Last error: {last_error}",
        "status": "failed",
        "attempts": attempts,
    }
