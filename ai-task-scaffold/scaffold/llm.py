"""
scaffold/llm.py — Astronomy observation catalog domain.

Multi-provider LLM wrapper. All providers expose an OpenAI-compatible API.
Provider priority: github (primary) → groq (backup)
"""
import os
import json
from openai import OpenAI
import scaffold.schemas as sc_schemas

SYSTEM_PROMPT = """You are an AI assistant for an astronomical observation catalog system.
You convert natural language commands from researchers into structured tool calls.

Valid observation_status values: Unobserved, Scheduled, Observed, Confirmed, Anomalous
Valid priority values: Low, Medium, High, Critical
Valid object_type values: Star, Exoplanet, Asteroid, Galaxy, Nebula, Comet

CRITICAL RULES:
- You DO NOT have the database context upfront. You MUST use the SEARCH_CATALOG tool first to find the exact UUIDs of the objects requested before executing any updates.
- ALL UUIDs in target_object_ids MUST be valid UUIDs retrieved from the SEARCH_CATALOG tool.
- If the search reveals the object doesn't exist, fallback to the CLARIFICATION_NEEDED tool.
- If the command is physically impossible or ambiguous, fallback to the CLARIFICATION_NEEDED tool.
- Every action must include a "reasoning" field (max 600 chars) explaining which objects were selected and why."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "EXECUTE_AGENT_PLAN",
            "description": "Execute a database action plan containing your thought process, execution plan, and a list of actions.",
            "parameters": sc_schemas.ReActPayload.model_json_schema()
        }
    }
]

_CONFIGS = {
    "github": (
        "https://models.inference.ai.azure.com",
        "GITHUB_TOKEN",
        "gpt-4o-mini",
    ),
    "groq": (
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "llama-3.3-70b-versatile",
    ),
    "huggingface": (
        "https://api-inference.huggingface.co/v1/",
        "HF_TOKEN",
        "meta-llama/Llama-3.3-70B-Instruct",
    ),
}

_instances: dict[str, OpenAI] = {}


def _get_client(provider: str) -> OpenAI:
    if provider not in _CONFIGS:
        raise ValueError(f"Unknown provider: {provider!r}. Choose from: {list(_CONFIGS)}")
    if provider not in _instances:
        base_url, env_key, _ = _CONFIGS[provider]
        _instances[provider] = OpenAI(
            api_key=os.environ.get(env_key, ""),
            base_url=base_url,
            timeout=30.0,
        )
    return _instances[provider]


def parse_command(
    user_prompt: str,
    catalog_context: list[dict],
    provider: str = "github",
    history: list = None,
) -> str:
    """
    Send a natural language command + catalog context to the LLM.
    Returns the raw response string (not yet validated).
    """
    _, _, model_id = _CONFIGS[provider]

    history = history or []
    # Include up to the last 3 turns of history for context
    history_text = ""
    if history:
        history_text = "Recent conversation history (for resolving pronouns like 'those' or 'them'):\n"
        for turn in history[-3:]:
            # Gradio 6 style history: turn is a list of dicts, but we just want text.
            # Handle both Gradio 4 format [user_str, bot_str] and Gradio 6 format [{"role":"user", "content":str}, ...]
            if isinstance(turn, dict):
                history_text += f"{turn.get('role', 'unknown')}: {turn.get('content', '')}\n"
            elif isinstance(turn, list) and len(turn) == 2:
                user_msg, bot_msg = turn
                if isinstance(user_msg, dict): user_msg = user_msg.get('content', '')
                if isinstance(bot_msg, dict): bot_msg = bot_msg.get('content', '')
                history_text += f"User: {user_msg}\nAssistant: {bot_msg}\n"
        history_text += "\n"

    full_prompt = (
        f"{history_text}"
        f"Researcher command: {user_prompt}"
    )
    client = _get_client(provider)
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt},
        ],
        temperature=0,
        tools=TOOLS,
        tool_choice="required"
    )
    
    msg = response.choices[0].message
    if msg.tool_calls:
        call = msg.tool_calls[0]
        try:
            args = json.loads(call.function.arguments)
        except json.JSONDecodeError:
            args = {}
        return json.dumps(args, indent=2)
        
    return msg.content or ""
