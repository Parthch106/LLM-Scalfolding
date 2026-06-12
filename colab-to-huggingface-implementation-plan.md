# AI Task Manager with Deterministic Scaffolding
## Build Plan: Colab/Kaggle Prototyping → Hugging Face Spaces Deployment

This is an adaptation of the original Next.js/Supabase plan for a **Python-first workflow**: prototype the core "scaffolding" logic in a Colab or Kaggle notebook, then package it as a **Gradio app** and deploy it to **Hugging Face Spaces** for a free, public, shareable demo link — ideal for a CV/portfolio.

The core architecture and "story" (LLM → validation gate → self-correction loop → deterministic execution → audit log/metrics) stays identical. Only the tooling changes.

---

## 1. Why This Stack Works Well

| Original (Next.js) | Adapted (Python) | Notes |
|---|---|---|
| TypeScript | Python | Easier to prototype interactively in notebooks |
| Zod | **Pydantic** | Same role — schema + validation |
| Next.js UI | **Gradio** | Free, deploys directly to HF Spaces, has built-in chat UI |
| Supabase (DB + Auth) | **Supabase (kept)** | Python client works identically; gives you a real persistent Postgres DB with RLS — keeps the "production-grade" story intact |
| Vercel hosting | **Hugging Face Spaces** | Free hosting, public URL, great visibility on a CV (recruiters browse HF) |

You're not downgrading the architecture — you're just building it in notebooks first (fast iteration, easy to demo cell-by-cell) and shipping the final logic as a small Python package + Gradio app.

---

## 2. Tech Stack

- **Development environment:** Google Colab (primary) or Kaggle Notebooks
- **LLM:** Multi-provider — Anthropic Claude (primary, via `anthropic` SDK) with Groq, OpenAI, and GitHub Models as drop-in alternatives behind a shared interface, used both for the live demo and for the multi-model reliability benchmark (see **Appendix A**)
- **Validation:** Pydantic v2
- **Database:** Supabase (Postgres, free tier) accessed via `supabase-py`
- **UI/Deployment:** Gradio app hosted on Hugging Face Spaces
- **Testing:** pytest (run inside notebooks or as standalone scripts)
- **Repo hosting:** GitHub (source of truth) + Hugging Face Space (deployment target)

---

## 3. Project Structure

Even though development starts in notebooks, structure the code as a small importable package from day one — this is what separates "notebook spaghetti" from a CV-worthy repo.

```
ai-task-scaffold/
├── app.py                     # Gradio entrypoint (used by HF Spaces)
├── requirements.txt
├── README.md                  # HF Space card + project writeup
├── SECURITY.md
├── scaffold/
│   ├── __init__.py
│   ├── schemas.py              # Pydantic action models
│   ├── llm.py                  # Anthropic API wrapper
│   ├── validate.py             # validation gate
│   ├── execute.py               # deterministic DB execution
│   ├── agent.py                  # self-correction loop
│   └── db.py                      # Supabase client + queries
├── notebooks/
│   ├── 01_prototype.ipynb      # Build & test scaffold step by step
│   ├── 02_eval.ipynb           # Adversarial prompt evaluation
│   └── 03_metrics.ipynb        # Self-correction metrics analysis
└── tests/
    └── test_validate.py
```

Develop modules inside `notebooks/01_prototype.ipynb` first (writing functions in cells is fine), but **periodically export them into `scaffold/*.py`** using either manual copy-paste or `%%writefile` magic. By the end of prototyping, `app.py` should just *import* from `scaffold/`, not contain logic itself.

---

## 4. Phased Plan

### Phase 0 — Environment Setup (Colab) (Day 1)

1. Create a new Colab notebook: `01_prototype.ipynb`
2. Install dependencies:
```python
!pip install anthropic openai pydantic supabase gradio pytest -q
```
3. Store secrets using Colab's built-in secrets manager (key icon in left sidebar) — **never hardcode API keys**:
```python
from google.colab import userdata
import os

os.environ["ANTHROPIC_API_KEY"] = userdata.get("ANTHROPIC_API_KEY")
os.environ["SUPABASE_URL"] = userdata.get("SUPABASE_URL")
os.environ["SUPABASE_KEY"] = userdata.get("SUPABASE_KEY")

# Optional — only needed for the multi-model benchmark (Phase 5b) and/or
# if you choose a different default provider for the live demo
os.environ["GROQ_API_KEY"] = userdata.get("GROQ_API_KEY")        # free tier, no card
os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")    # ~$5 signup credit
os.environ["GITHUB_TOKEN"] = userdata.get("GITHUB_TOKEN")        # free, models:read scope
```
> On Kaggle, use **Add-ons → Secrets** instead, which works the same way via `kaggle_secrets.UserSecretsClient`.

4. Set up Supabase project (free tier at supabase.com), create the same tables as before:

```sql
create table tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default '00000000-0000-0000-0000-000000000001', -- single demo user for now
  title text not null,
  description text,
  status text not null check (status in ('To Do', 'In Progress', 'Done', 'Blocked')),
  priority text not null check (priority in ('Low', 'Medium', 'High', 'Urgent')),
  tags text[] default '{}',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table ai_action_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  user_prompt text not null,
  raw_llm_output jsonb,
  validation_attempts jsonb,
  final_status text not null check (final_status in ('success','self_corrected','failed','rejected_unauthorized')),
  executed_action jsonb,
  created_at timestamptz default now()
);
```

> For a public demo, you can either (a) use a single fixed demo `user_id` (simplest — full multi-user auth is overkill for a portfolio demo), or (b) add a lightweight Gradio textbox where users enter a "demo session ID" that's used as `user_id`. Document this tradeoff explicitly in your README — it shows you understand the difference between a demo and production auth.

**Deliverable:** Notebook that can connect to Supabase and read/write a row.

---

### Phase 1 — Action Schema with Pydantic (Day 2)

```python
# scaffold/schemas.py
from typing import Literal, Union
from pydantic import BaseModel, Field
from uuid import UUID

class BaseAction(BaseModel):
    reasoning: str = Field(max_length=500)

class UpdateStatusAction(BaseAction):
    action_type: Literal["UPDATE_STATUS"]
    target_task_ids: list[UUID] = Field(min_length=1, max_length=50)
    new_status: Literal["To Do", "In Progress", "Done", "Blocked"]

class UpdatePriorityAction(BaseAction):
    action_type: Literal["UPDATE_PRIORITY"]
    target_task_ids: list[UUID] = Field(min_length=1, max_length=50)
    new_priority: Literal["Low", "Medium", "High", "Urgent"]

class CreateTaskAction(BaseAction):
    action_type: Literal["CREATE_TASK"]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    priority: Literal["Low", "Medium", "High", "Urgent"] = "Medium"
    status: Literal["To Do", "In Progress", "Done", "Blocked"] = "To Do"

class DeleteTaskAction(BaseAction):
    action_type: Literal["DELETE_TASK"]
    target_task_ids: list[UUID] = Field(min_length=1, max_length=50)
    confirmation_required: Literal[True]

class ClarificationNeeded(BaseAction):
    action_type: Literal["CLARIFICATION_NEEDED"]
    message_to_user: str

AgentAction = Union[
    UpdateStatusAction,
    UpdatePriorityAction,
    CreateTaskAction,
    DeleteTaskAction,
    ClarificationNeeded,
]
```

Use `pydantic.TypeAdapter(AgentAction)` to validate/discriminate by `action_type`:

```python
from pydantic import TypeAdapter
ActionValidator = TypeAdapter(AgentAction)
```

**Deliverable:** `schemas.py` module, tested interactively in the notebook with a few hand-written valid/invalid JSON examples.

---

### Phase 2 — LLM Wrapper (Multi-Provider) (Day 3)

Build this as a thin, provider-agnostic interface from the start. Claude Haiku is the default, but Groq, OpenAI, and GitHub Models are wired in behind the same `parse_command()` function — this is what lets you swap models with a one-line change later, and is the foundation for the Phase 5b benchmark.

```python
# scaffold/llm.py
import os, json
from anthropic import Anthropic
from openai import OpenAI

SYSTEM_PROMPT = """You convert user task-management commands into a single JSON action.
Available statuses: To Do, In Progress, Done, Blocked.
Available priorities: Low, Medium, High, Urgent.
Only reference task IDs that exist in the provided context.
If the request is ambiguous, return a CLARIFICATION_NEEDED action.
Respond ONLY with valid JSON. No prose, no markdown fences."""

# Claude uses its native SDK; the rest are OpenAI-compatible endpoints
_anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

_openai_compatible_clients = {
    "openai": lambda: OpenAI(api_key=os.environ.get("OPENAI_API_KEY")),
    "groq": lambda: OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    ),
    "github": lambda: OpenAI(
        api_key=os.environ.get("GITHUB_TOKEN"),
        base_url="https://models.github.ai/inference",
    ),
}

# Pick one model per provider — see Appendix A for free-tier notes
MODEL_IDS = {
    "claude": "claude-haiku-4-5",
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4.1-nano",
    "github": "openai/gpt-4o-mini",
}

def parse_command(user_prompt: str, task_context: list[dict], provider: str = "claude") -> str:
    full_prompt = f"Context: {json.dumps(task_context)}\n\nCommand: {user_prompt}"

    if provider == "claude":
        response = _anthropic_client.messages.create(
            model=MODEL_IDS["claude"],
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": full_prompt}],
        )
        return response.content[0].text

    client = _openai_compatible_clients[provider]()
    response = client.chat.completions.create(
        model=MODEL_IDS[provider],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt},
        ],
    )
    return response.choices[0].message.content
```

**Deliverable:** Run the same command through `parse_command(prompt, context, provider="claude")` and `parse_command(prompt, context, provider="groq")` and print both raw JSON outputs side by side — eyeball them before building validation.

---

### Phase 3 — Validation Gate (Days 4–5)

```python
# scaffold/validate.py
import json
from pydantic import ValidationError
from .schemas import AgentAction, ActionValidator
from .db import get_supabase

def validate_action(raw_output: str, user_id: str) -> dict:
    """Returns a dict: {valid: bool, stage, error, action (if valid)}"""

    # Stage 1: syntax
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return {"valid": False, "stage": "syntax", "error": "Output was not valid JSON."}

    # Stage 2: schema (Pydantic discriminated union)
    try:
        action = ActionValidator.validate_python(parsed)
    except ValidationError as e:
        return {"valid": False, "stage": "schema", "error": str(e)}

    # Stage 3 & 4: business rules + authorization
    if hasattr(action, "target_task_ids"):
        sb = get_supabase()
        ids = [str(i) for i in action.target_task_ids]
        res = sb.table("tasks").select("id, user_id").in_("id", ids).execute()
        found = {row["id"]: row["user_id"] for row in res.data}

        missing = [i for i in ids if i not in found]
        if missing:
            return {"valid": False, "stage": "business", "error": f"Task IDs not found: {missing}"}

        unauthorized = [i for i in ids if found[i] != user_id]
        if unauthorized:
            return {"valid": False, "stage": "auth", "error": "User does not own one or more target tasks."}

    return {"valid": True, "action": action}
```

**Deliverable:** Unit test this with: valid JSON, malformed JSON, JSON with a hallucinated status (`"Almost Done"`), JSON referencing a real task ID owned by a different user. Write these as a `tests/test_validate.py` file early — they're great evidence for your README.

---

### Phase 4 — Self-Correction Loop + Execution (Days 6–7)

```python
# scaffold/execute.py
from .db import get_supabase

def execute_action(action, user_id: str) -> dict:
    sb = get_supabase()
    match action.action_type:
        case "UPDATE_STATUS":
            ids = [str(i) for i in action.target_task_ids]
            sb.table("tasks").update({"status": action.new_status}) \
              .in_("id", ids).eq("user_id", user_id).execute()
            return {"message": f"Updated {len(ids)} task(s) to {action.new_status}"}

        case "UPDATE_PRIORITY":
            ids = [str(i) for i in action.target_task_ids]
            sb.table("tasks").update({"priority": action.new_priority}) \
              .in_("id", ids).eq("user_id", user_id).execute()
            return {"message": f"Updated {len(ids)} task(s) to priority {action.new_priority}"}

        case "CREATE_TASK":
            sb.table("tasks").insert({
                "user_id": user_id, "title": action.title,
                "description": action.description,
                "priority": action.priority, "status": action.status,
            }).execute()
            return {"message": f"Created task '{action.title}'"}

        case "DELETE_TASK":
            ids = [str(i) for i in action.target_task_ids]
            sb.table("tasks").delete().in_("id", ids).eq("user_id", user_id).execute()
            return {"message": f"Deleted {len(ids)} task(s)"}

        case "CLARIFICATION_NEEDED":
            return {"message": action.message_to_user}
```

```python
# scaffold/agent.py
from .llm import parse_command
from .validate import validate_action
from .execute import execute_action
from .db import log_action, get_tasks_for_context

MAX_RETRIES = 2

def run_agent(user_prompt: str, user_id: str, provider: str = "claude") -> dict:
    task_context = get_tasks_for_context(user_id)
    attempts = []
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error:
            prompt += f"\n\n[SYSTEM CORRECTION]: Previous output failed validation: \"{last_error}\". Resend corrected JSON only."

        raw = parse_command(prompt, task_context, provider=provider)
        result = validate_action(raw, user_id)
        attempts.append({"attempt": attempt, "raw": raw, "result": {k: v for k, v in result.items() if k != "action"}})

        if result["valid"]:
            exec_result = execute_action(result["action"], user_id)
            status = "success" if attempt == 0 else "self_corrected"
            log_action(user_id, user_prompt, attempts, status, result["action"].model_dump())
            return {"success": True, "message": exec_result["message"], "status": status}

        last_error = result["error"]

    log_action(user_id, user_prompt, attempts, "failed", None)
    return {"success": False, "message": f"AI failed validation after {MAX_RETRIES} retries: {last_error}", "status": "failed"}
```

**Deliverable:** Run `run_agent("move all high priority tasks to In Progress", DEMO_USER_ID)` in the notebook and watch it execute against your real Supabase tasks. Manually break things (e.g. temporarily ask the model to use an invalid status via a crafted prompt) to *trigger and observe* the self-correction path.

---

### Phase 5 — Adversarial Evaluation Set (Day 8)

In `notebooks/02_eval.ipynb`, build a small evaluation harness — this becomes the source of your "first-pass success rate" and "self-correction success rate" metrics for the README.

```python
EVAL_PROMPTS = [
    {"prompt": "Move all high priority design tasks to In Progress", "expects": "UPDATE_STATUS"},
    {"prompt": "Create a task called 'Write CV project README'", "expects": "CREATE_TASK"},
    {"prompt": "Delete everything", "expects": "CLARIFICATION_NEEDED"},  # ambiguous/destructive
    {"prompt": "Set task xyz to 'Almost Done'", "expects": "schema_failure_then_recover"},
    {"prompt": "asdkjasd random gibberish", "expects": "CLARIFICATION_NEEDED"},
    # ... 15-25 total, mix of normal, ambiguous, and adversarial
]

results = []
for case in EVAL_PROMPTS:
    r = run_agent(case["prompt"], DEMO_USER_ID)
    results.append({**case, "result": r})

import pandas as pd
df = pd.DataFrame(results)
df.to_csv("eval_results.csv", index=False)
```

Then compute summary stats (first-pass success %, self-correction recovery %, failure %) — this is exactly the data you'll show in the README and on the Gradio "Metrics" tab.

**Deliverable:** `eval_results.csv` + a short markdown table summarizing the numbers.

---

### Phase 5b — Multi-Model Reliability Benchmark (Stretch Goal, Day 8 cont.)

Run the *same* `EVAL_PROMPTS` set against each provider and compare first-pass success rate, self-correction recovery rate, failure rate, and latency. This is the single highest-leverage addition for your README — it turns "I picked Claude Haiku" into "I benchmarked four providers on a structured-output task."

```python
import time
import pandas as pd

# Use whichever providers you have keys for — see Appendix A for free-tier limits
PROVIDERS_TO_TEST = ["claude", "groq", "github"]  # add "openai" if you topped up credits

benchmark_rows = []
for provider in PROVIDERS_TO_TEST:
    for case in EVAL_PROMPTS:
        start = time.time()
        result = run_agent(case["prompt"], DEMO_USER_ID, provider=provider)
        latency = round(time.time() - start, 2)
        benchmark_rows.append({
            "provider": provider,
            "prompt": case["prompt"],
            "status": result.get("status"),
            "success": result["success"],
            "latency_sec": latency,
        })
        time.sleep(2)  # be polite to free-tier rate limits, especially GitHub Models

bench_df = pd.DataFrame(benchmark_rows)

summary = bench_df.groupby("provider").apply(lambda g: pd.Series({
    "first_pass_success_%": round((g["status"] == "success").mean() * 100, 1),
    "self_correction_%":    round((g["status"] == "self_corrected").mean() * 100, 1),
    "failure_%":            round((g["status"] == "failed").mean() * 100, 1),
    "avg_latency_sec":      round(g["latency_sec"].mean(), 2),
})).reset_index()

bench_df.to_csv("benchmark_results.csv", index=False)
print(summary.to_markdown(index=False))
```

> **Rate limit note:** GitHub Models and Groq free tiers cap requests per minute — the `time.sleep(2)` above keeps you under most limits for a ~20–30 prompt eval. If you hit a 429, just increase the sleep or run providers in separate cells/sessions.

Drop the `summary` table directly into your README — a 3–4 row table comparing providers on these four columns is exactly the kind of artifact that makes a recruiter stop scrolling.

**Deliverable:** `benchmark_results.csv` + the printed markdown summary table, ready to paste into the README.

---

### Phase 6 — Build the Gradio App (Days 9–10)

This is what gets deployed to Hugging Face Spaces. Build it in the notebook first (Gradio runs fine in Colab with `share=True` for a temporary public link), then finalize as `app.py`.

```python
# app.py
import os
import gradio as gr
import pandas as pd
from scaffold.agent import run_agent
from scaffold.db import get_supabase, get_metrics

DEMO_USER_ID = os.environ.get("DEMO_USER_ID", "00000000-0000-0000-0000-000000000001")

def chat_handler(message, history):
    result = run_agent(message, DEMO_USER_ID)
    return result["message"]

def refresh_tasks():
    sb = get_supabase()
    res = sb.table("tasks").select("*").eq("user_id", DEMO_USER_ID).execute()
    return pd.DataFrame(res.data)

def refresh_metrics():
    return get_metrics(DEMO_USER_ID)  # returns dict -> render as markdown/dataframe

with gr.Blocks(title="AI Task Manager — Deterministic Scaffolding Demo") as demo:
    gr.Markdown("# 🧩 AI Task Manager with Deterministic Scaffolding")
    gr.Markdown(
        "Type natural language commands. Every AI output passes through a "
        "Pydantic validation gate + self-correction loop before touching the database. "
        "[Read the writeup](https://github.com/yourname/ai-task-scaffold)"
    )

    with gr.Tab("Chat"):
        chatbot = gr.ChatInterface(fn=chat_handler, title="Try a command")
        gr.Examples(
            examples=[
                "Create a task called 'Prepare slides' with high priority",
                "Move all high priority tasks to In Progress",
                "Set the 'Prepare slides' task to Done",
            ],
            inputs=chatbot.textbox,
        )

    with gr.Tab("Task Board"):
        task_table = gr.Dataframe(headers=["title", "status", "priority"], label="Current Tasks")
        refresh_btn = gr.Button("Refresh")
        refresh_btn.click(fn=refresh_tasks, outputs=task_table)
        demo.load(fn=refresh_tasks, outputs=task_table)

    with gr.Tab("Reliability Metrics"):
        gr.Markdown("### Self-Correction Success Rate (live, from ai_action_log)")
        metrics_table = gr.JSON()
        gr.Button("Refresh Metrics").click(fn=refresh_metrics, outputs=metrics_table)

demo.launch()
```

```python
# scaffold/db.py — add this metrics helper
def get_metrics(user_id: str) -> dict:
    sb = get_supabase()
    res = sb.table("ai_action_log").select("final_status").eq("user_id", user_id).execute()
    total = len(res.data)
    if total == 0:
        return {"total_runs": 0}
    counts = {}
    for row in res.data:
        counts[row["final_status"]] = counts.get(row["final_status"], 0) + 1
    return {
        "total_runs": total,
        "first_pass_success_rate": round(counts.get("success", 0) / total * 100, 1),
        "self_correction_rate": round(counts.get("self_corrected", 0) / total * 100, 1),
        "failure_rate": round(counts.get("failed", 0) / total * 100, 1),
    }
```

**Deliverable:** Working Gradio app, runnable locally / in Colab via `demo.launch(share=True)`.

---

### Phase 7 — Deploy to Hugging Face Spaces (Day 11)

**Option A — Web UI (simplest):**
1. Go to huggingface.co → New Space → choose **Gradio** SDK
2. Upload `app.py`, `requirements.txt`, and the `scaffold/` folder (HF Spaces support subfolders)
3. Go to **Settings → Repository secrets** and add `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `DEMO_USER_ID`
4. Space auto-builds and gives you a public URL like `https://huggingface.co/spaces/yourname/ai-task-scaffold`

**Option B — From Colab via `huggingface_hub` (shows more CLI skill):**
```python
from huggingface_hub import HfApi, create_repo

create_repo("yourname/ai-task-scaffold", repo_type="space", space_sdk="gradio")

api = HfApi()
api.upload_folder(
    folder_path=".",
    repo_id="yourname/ai-task-scaffold",
    repo_type="space",
)
```
Then set secrets via the Space settings page (secrets can't be uploaded programmatically for security reasons — by design).

**requirements.txt:**
```
gradio
anthropic
openai
pydantic>=2
supabase
pandas
tabulate
```

> `openai` covers the Groq and GitHub Models clients too, since both expose OpenAI-compatible endpoints. `tabulate` is only needed if you use `df.to_markdown()` in the benchmark notebook.

**Deliverable:** Live public Space URL — this is the link you put on your CV/LinkedIn.

---

### Phase 8 — Final Polish & CV Packaging (Days 12–13)

- **README.md** (doubles as your HF Space card via YAML frontmatter):

```markdown
---
title: AI Task Manager — Deterministic Scaffolding
emoji: 🧩
colorFrom: indigo
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
---

# AI Task Manager with Deterministic Scaffolding
...
```

- Include: architecture diagram, the eval results table from Phase 5, a screen recording (GIF) of the chat updating the task board, and a link to the GitHub repo with full commit history
- Push the *same code* to a GitHub repo (HF Spaces can also sync from GitHub via webhook — set this up so HF stays in sync automatically with `git push`)
- Add `SECURITY.md` covering: prompt injection mitigation, scoping all DB writes by `user_id`, rate-limiting considerations for the public demo (HF Spaces have usage limits anyway, but mention how you'd add request throttling for a multi-user version)

**Deliverable:** Public HF Space + GitHub repo + polished README, ready to link from your CV/portfolio site.

---

## 5. Colab vs Kaggle — Which to Use

- **Colab**: better for this project. Easier secrets management, better Gradio `share=True` support, no internet-access restrictions (Kaggle notebooks can have network disabled by default and need it enabled in settings).
- **Kaggle**: useful if you also want to publish a **dataset** (e.g., your `eval_results.csv` adversarial test set) or a **Kaggle Notebook writeup** as an additional public artifact — Kaggle notebooks are discoverable and add another portfolio link. Consider publishing `02_eval.ipynb` as a public Kaggle notebook purely as a "research writeup" companion piece, even if the live app is hosted on HF.

---

## 6. Suggested Timeline

| Days | Focus |
|---|---|
| 1–3 | Setup, schemas, LLM wrapper (Colab) |
| 4–7 | Validation gate, self-correction loop, execution |
| 8 | Adversarial eval set + metrics |
| 9–10 | Gradio app |
| 11 | Deploy to Hugging Face Spaces |
| 12–13 | README, diagrams, GitHub sync, polish |

~2 weeks part-time.

---

## 7. What Stays the Same as the Original Plan

The interview-worthy talking points don't change at all:
- The discriminated-union action schema as the contract between AI and system
- The multi-stage validation gate (syntax → schema → business rules → auth)
- The self-correction retry loop and measuring its success rate
- Full audit logging for every AI decision
- Defense-in-depth: scoping every DB write by `user_id` even though the LLM never has direct DB access

Only the *delivery mechanism* changed — from a Next.js app on Vercel to a Gradio app on Hugging Face Spaces, built and tested interactively in Colab. If anything, the HF Space link is **easier for recruiters to click and try immediately** than a Vercel deploy that might require sign-up.

---

## Appendix A — Free LLM Provider Options & Setup Notes

For both the live demo and the Phase 5b benchmark, you don't need to spend any money. Here's how the providers compare:

| Provider | Free access | How to get a key | Good for |
|---|---|---|---|
| **Groq** (Llama 3.3 70B, etc.) | Permanent free tier, no card — rate-limited (~30 req/min, ~1,000 req/day on the default tier) | Sign up at console.groq.com, create an API key | **Always-on HF Space demo** — won't run out of credit |
| **Anthropic (Claude Haiku)** | No permanent free tier, but new accounts get a one-time API credit (~$5) | console.anthropic.com → API Keys | Primary model for the demo + benchmark; one-off eval cost is a fraction of a cent |
| **OpenAI (GPT-4.1 nano / GPT-4o-mini)** | New accounts get a one-time credit (~$5, expires after a few months) | platform.openai.com → API Keys | Optional 4th benchmark entry |
| **GitHub Models** | Free for any GitHub account, OpenAI-compatible endpoint, rate-limited (~10 req/min, ~50 req/day on higher-tier models for free accounts) | github.com → Settings → Developer settings → Personal access tokens → grant `models:read` scope | Zero-setup way to add an OpenAI model to the benchmark without a separate OpenAI account |

**Recommended split:**
- **Live HF Space demo:** default to **Groq** so the public demo never gets throttled by a depleted credit balance.
- **Phase 5b benchmark (one-off, ~20–30 prompts):** run all 3–4 providers — Claude Haiku, Groq/Llama, and GitHub Models (plus OpenAI direct if you have credits). The total cost across all of them is at most a few cents, well within free signup credits.

**Caveat:** free-tier rate limits, credit amounts, and expiry windows for all of these providers change fairly often. Before wiring up the benchmark, do a quick check of each provider's current docs/pricing page so your code doesn't get unexpectedly throttled mid-run.
