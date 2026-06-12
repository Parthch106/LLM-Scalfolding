"""
scaffold/db.py

Supabase client setup + all database operations.
This is the ONLY file that talks to the database — the LLM never touches this directly.
"""
import os
from supabase import create_client, Client
from openai import OpenAI

_client: Client | None = None


def get_supabase() -> Client:
    """Lazy singleton — initialised once per process."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


def get_catalog_for_context(user_id: str) -> list[dict]:
    """
    Fetch the user's catalog to pass as context to the LLM.
    Only includes fields the LLM needs — never leaks other users' data.
    """
    sb = get_supabase()
    res = (
        sb.table("celestial_objects")
        .select("id, catalog_id, name, object_type, observation_status, priority, tags")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(100)  # cap context size sent to LLM
        .execute()
    )
    return res.data or []
    
def search_catalog(query: str, user_id: str) -> list[dict]:
    """
    RAG Semantic Vector Search.
    Converts the query into a math vector and performs Cosine Similarity search.
    """
    sb = get_supabase()
    
    try:
        # Default to github proxy, fallback to openai
        base_url = "https://models.inference.ai.azure.com"
        api_key = os.environ.get("GITHUB_TOKEN", os.environ.get("OPENAI_API_KEY", ""))
        
        # If GitHub proxy doesn't support text-embedding-3-small, you might need an actual OpenAI key.
        # But for this demo, we assume the proxy supports it or you have OPENAI_API_KEY.
        if "OPENAI_API_KEY" in os.environ:
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        else:
            client = OpenAI(api_key=api_key, base_url=base_url)
            
        resp = client.embeddings.create(
            input=[query],
            model="text-embedding-3-small"
        )
        query_vector = resp.data[0].embedding
    except Exception as e:
        print(f"Embedding error: {e}")
        return []

    res = sb.rpc("match_celestial_objects", {
        "query_embedding": query_vector,
        "match_threshold": 0.3,
        "match_count": 5
    }).execute()
    
    return res.data or []


def log_action(
    user_id: str,
    user_prompt: str,
    attempts: list[dict],
    final_status: str,
    executed_action: dict | None,
    provider: str = "github",
) -> None:
    """Write a full audit log entry for every AI-driven action."""
    sb = get_supabase()
    sb.table("ai_action_log").insert({
        "user_id": user_id,
        "user_prompt": user_prompt,
        "raw_llm_output": attempts[0].get("raw") if attempts else None,
        "validation_attempts": attempts,
        "final_status": final_status,
        "executed_action": executed_action,
        "provider": provider,
    }).execute()


def get_metrics(user_id: str) -> dict:
    """Compute live success/failure metrics from the audit log."""
    sb = get_supabase()
    res = (
        sb.table("ai_action_log")
        .select("final_status, provider")
        .eq("user_id", user_id)
        .execute()
    )
    rows = res.data or []
    total = len(rows)
    if total == 0:
        return {"total_runs": 0, "message": "No actions logged yet. Try a command!"}

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["final_status"]] = counts.get(row["final_status"], 0) + 1

    return {
        "total_runs": total,
        "first_pass_success_%": round(counts.get("success", 0) / total * 100, 1),
        "self_correction_%": round(counts.get("self_corrected", 0) / total * 100, 1),
        "failure_%": round(counts.get("failed", 0) / total * 100, 1),
        "rejected_unauthorized_%": round(counts.get("rejected_unauthorized", 0) / total * 100, 1),
    }
