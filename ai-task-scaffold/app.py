"""
app.py — Gradio entrypoint for Hugging Face Spaces (Astronomy Domain)
"""
import os
import random
import json
import pypdf

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import gradio as gr
import pandas as pd
from scaffold.agent import run_agent, MAX_RETRIES
from scaffold.pdf_agent import run_pdf_agent, run_unscaffolded_pdf_agent, MAX_RETRIES as PDF_MAX_RETRIES
from scaffold.db import get_supabase, get_metrics

DEMO_USER_ID = os.environ.get("DEMO_USER_ID", "00000000-0000-0000-0000-000000000001")
PROVIDER = os.environ.get("LLM_PROVIDER", "github")

# ── Follow-up suggestion pools by action type ─────────────────────────────────

FOLLOWUPS = {
    "UPDATE_STATUS": [
        "Now set all Critical objects to Scheduled",
        "Mark the nearest star as Observed",
        "What's left in Unobserved? Show me.",
        "Set the exoplanets to Confirmed",
    ],
    "UPDATE_PRIORITY": [
        "Now schedule those objects for observation",
        "Downgrade all galaxies to Low priority",
        "Make the near-Earth asteroids Critical",
        "Set all Medium priority targets to High",
    ],
    "LOG_OBJECT": [
        "Now set that new object's priority to High",
        "Log another object: Comet Halley",
        "Flag the object I just logged as Anomalous",
    ],
    "FLAG_ANOMALY": [
        "Set the priority of the anomalous objects to Critical",
        "What other objects are anomalous?",
        "Mark the Crab Nebula as Anomalous too",
    ],
    "CLARIFICATION_NEEDED": [
        "Is Apophis going to hit us?",
        "How hot is a K-type star?",
        "Did we find aliens yet on TRAPPIST-1e?",
        "Schedule a meeting with the Crab Nebula",
        "Mark the weather outside as Cloudy",
        "Can we see Andromeda from here?",
        "Set Apophis to Critical priority",
        "Flag the Orion Nebula as Anomalous",
    ],
    "failed": [
        "Are we alone in the universe?",
        "Set the Apophis asteroid to Scheduled",
        "Move all Unobserved objects to Scheduled",
        "Mark the Crab Nebula as Observed",
    ],
}

def get_followups(action_type: str) -> list[str]:
    pool = FOLLOWUPS.get(action_type, FOLLOWUPS["CLARIFICATION_NEEDED"])
    return random.sample(pool, min(3, len(pool)))

# ── Data helpers ──────────────────────────────────────────────────────────────

PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
STATUS_ORDER   = {"Anomalous": 0, "Unobserved": 1, "Scheduled": 2, "Observed": 3, "Confirmed": 4}
STATUS_COLS    = ["Unobserved", "Scheduled", "Observed", "Confirmed", "Anomalous"]

def fetch_objects() -> list[dict]:
    try:
        sb = get_supabase()
        res = sb.table("celestial_objects").select("*").eq("user_id", DEMO_USER_ID).execute()
        return res.data or []
    except Exception as e:
        print(f"Error fetching objects: {e}")
        return []

def render_kanban() -> str:
    """Render the celestial objects as an HTML Kanban board."""
    objects = fetch_objects()
    
    # Group by status
    cols = {s: [] for s in STATUS_COLS}
    for obj in objects:
        status = obj.get("observation_status", "Unobserved")
        if status in cols:
            cols[status].append(obj)
            
    # Sort within columns by priority
    for s in cols:
        cols[s].sort(key=lambda x: PRIORITY_ORDER.get(x.get("priority", "Medium"), 9))
        
    # Build HTML
    html = '<div style="display: flex; gap: 1rem; overflow-x: auto; padding: 1rem; background: var(--background-fill-secondary); border-radius: 8px;">'
    
    status_colors = {
        "Unobserved": "gray",
        "Scheduled": "blue",
        "Observed": "purple",
        "Confirmed": "green",
        "Anomalous": "red"
    }
    
    priority_colors = {
        "Low": "#888",
        "Medium": "#4a90e2",
        "High": "#f39c12",
        "Critical": "#e74c3c"
    }
    
    for status in STATUS_COLS:
        objs = cols[status]
        color = status_colors[status]
        
        html += f'<div style="flex: 1; min-width: 250px; background: var(--background-fill-primary); padding: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-top: 4px solid {color}">'
        html += f'<h3 style="margin-top: 0; color: var(--body-text-color)">{status} <span style="opacity: 0.5; font-size: 0.8em">({len(objs)})</span></h3>'
        html += '<div style="display: flex; flex-direction: column; gap: 0.5rem;">'
        
        for obj in objs:
            pri_color = priority_colors.get(obj.get("priority"), "#888")
            tags = obj.get("tags", [])
            tag_html = " ".join([f'<span style="font-size: 0.7em; background: var(--background-fill-secondary); padding: 2px 6px; border-radius: 10px; margin-right: 4px;">{t}</span>' for t in tags])
            
            html += f'''
            <div style="background: var(--background-fill-secondary); border: 1px solid var(--border-color-primary); padding: 0.75rem; border-radius: 6px;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.25rem;">
                    <strong style="font-size: 0.9em;">{obj.get('catalog_id')}</strong>
                    <span style="font-size: 0.7em; padding: 2px 6px; border-radius: 4px; background: {pri_color}; color: white;">{obj.get('priority')}</span>
                </div>
                <div style="font-size: 0.85em; margin-bottom: 0.25rem;">{obj.get('name') or ''} <span style="opacity:0.6">({obj.get('object_type')})</span></div>
                <div>{tag_html}</div>
            </div>
            '''
        
        html += '</div></div>'
    
    html += '</div>'
    return html

def refresh_metrics() -> dict:
    return get_metrics(DEMO_USER_ID)

# ── Chat handler ──────────────────────────────────────────────────────────────

def handle_user_submit(message: str, history: list) -> tuple[str, list]:
    if not message:
        return "", history
    new_message = {"role": "user", "content": [{"type": "text", "text": message}]}
    return "", history + [new_message]

def chat_response_handler(history: list, secret_word: str) -> tuple[list, gr.Dataframe, gr.HTML]:
    if not history:
        return [], gr.update(), gr.update()
        
    content_list = history[-1]["content"]
    if isinstance(content_list, list) and len(content_list) > 0:
        user_message = content_list[0].get("text", "")
    elif isinstance(content_list, str):
        user_message = content_list
    else:
        user_message = ""
        
    existing_history = history[:-1] if len(history) > 1 else []

    result = run_agent(user_message, DEMO_USER_ID, provider=PROVIDER, history=existing_history, secret_word=secret_word)

    if result["status"] == "success":
        badge = "**✅ Success**"
    elif result["status"] == "self_corrected":
        badge = "**🔄 Self-corrected** *(validation failed on attempt 1 — AI fixed it automatically)*"
        first_error = result.get("attempts", [{}])[0].get("error", "Unknown error")
        badge += f"\n\n> ⚠️ **Pass 1 Blocked:** `{first_error}`"
    else:
        badge = f"**❌ Failed** *(could not produce valid output after {MAX_RETRIES} retries)*"
        attempts_log = "\n\n### 📜 Attempt History"
        for att in result.get("attempts", []):
            attempts_log += f"\n\n<details><summary><b>Attempt {att['attempt'] + 1}</b></summary>\n\n**Raw Output:**\n```json\n{att['raw']}\n```\n\n**Error:**\n`{att['error']}`\n</details>"
        badge += attempts_log

    search_log = ""
    for att in result.get("attempts", []):
        if att.get("stage") == "rag_search":
            search_log += f"\n\n🔍 **AI Searched Database:** `{att['error']}`"
            
    if search_log:
        badge += search_log

    lines = [badge, "", result["message"]]
    reasoning = result.get("reasoning", "")
    if reasoning and result["success"]:
        lines += ["", f"*🧠 AI reasoning: {reasoning}*"]

    if not result["success"]:
        action_type = "failed"
    else:
        msg_val = result["message"]
        if "Logged" in msg_val: action_type = "LOG_OBJECT"
        elif "Anomalous" in msg_val: action_type = "FLAG_ANOMALY"
        elif "priority" in msg_val.lower(): action_type = "UPDATE_PRIORITY"
        elif "→" in msg_val: action_type = "UPDATE_STATUS"
        else: action_type = "CLARIFICATION_NEEDED"

    followups = get_followups(action_type)
    response_text = "\n".join(lines)
    
    new_message = {"role": "assistant", "content": [{"type": "text", "text": response_text}]}
    new_history = history + [new_message]
    new_df = gr.Dataframe(
        headers=["💡 Contextual Follow-ups"],
        value=[[s] for s in followups]
    )
    
    return new_history, new_df, gr.update(value=render_kanban(), visible=True)

def run_evaluation(file_obj, instruction: str, document_type: str, secret_word: str | None = None):
    if not file_obj:
        return "**❌ No file uploaded**", "{}", "**❌ No file uploaded**", "{}"
        
    try:
        reader = pypdf.PdfReader(file_obj.name)
        text = "\n".join(page.extract_text() for page in reader.pages)
    except Exception as e:
        return f"**❌ PDF Error:** {str(e)}", "{}", f"**❌ PDF Error:** {str(e)}", "{}"
        
    # 1. Run Unscaffolded Track
    raw_res = run_unscaffolded_pdf_agent(text, instruction, document_type=document_type, provider=PROVIDER, secret_word=secret_word)
    if raw_res["success"]:
        raw_status = "**✅ Passed!**\n\nThe LLM magically generated perfect math on the first try."
    else:
        raw_status = f"**❌ Failed (Math/Schema Error)**\n\n{raw_res['message']}\n\n*Without scaffolding, this corrupted data would have been saved directly to your database!*"
    
    raw_json = raw_res["raw"]
    
    # 2. Run Scaffolded Track
    scaf_res = run_pdf_agent(text, instruction, document_type=document_type, provider=PROVIDER, secret_word=secret_word)
    if scaf_res["status"] == "success":
        scaf_status = "**✅ Passed on Attempt 1**\n\nThe Python gate verified the math was perfect."
    elif scaf_res["status"] == "self_corrected":
        scaf_status = f"**🔄 Self-Corrected!**\n\nThe Python gate blocked the bad math and forced the AI to recalculate it. It took {len(scaf_res['attempts'])} attempts to get it right."
    else:
        last_err = scaf_res["attempts"][-1]["error"] if scaf_res.get("attempts") else "Unknown Error"
        scaf_status = f"**❌ Failed**\n\nThe AI could not fix the math after {len(scaf_res['attempts'])} retries.\n\n**Last Error:**\n`{last_err}`"
        
    import json
    scaf_json = json.dumps(scaf_res["data"], indent=2) if scaf_res.get("data") else "{}"
    
    return raw_status, raw_json, scaf_status, scaf_json

def extract_pdf_handler(file_obj, instruction: str, document_type: str, secret_word: str | None = None) -> tuple[str, str]:
    if not file_obj:
        return "**❌ Failed** *(No file uploaded)*", "{}"
        
    try:
        reader = pypdf.PdfReader(file_obj.name)
        text = "\n".join(page.extract_text() for page in reader.pages)
    except Exception as e:
        return f"**❌ Failed** *(Could not parse PDF: {str(e)})*", "{}"
        
    result = run_pdf_agent(text, instruction, document_type=document_type, provider=PROVIDER, secret_word=secret_word)
    
    if result["status"] == "success":
        badge = "**✅ Success**"
    elif result["status"] == "self_corrected":
        badge = "**🔄 Self-corrected** *(validation failed on attempt 1 — AI fixed it automatically)*"
        first_error = result.get("attempts", [{}])[0].get("error", "Unknown error")
        badge += f"\n\n> ⚠️ **Pass 1 Blocked:** `{first_error}`"
    else:
        badge = f"**❌ Failed** *(could not produce valid output after {PDF_MAX_RETRIES} retries)*"
        
    attempts_log = "\n\n### 📜 Attempt History"
    for att in result.get("attempts", []):
        attempts_log += f"\n\n<details><summary><b>Attempt {att['attempt'] + 1}</b></summary>\n\n**Raw Output:**\n```json\n{att['raw']}\n```\n\n**Error:**\n`{att['error']}`\n</details>"
    badge += attempts_log
    
    if result["success"]:
        formatted_json = json.dumps(result["data"], indent=2)
        return badge, formatted_json
    else:
        return badge, "{}"

# ── PREMIUM UI DESIGN ─────────────────────────────────────────────────────────

custom_theme = gr.themes.Monochrome(
    font=(gr.themes.GoogleFont("Space Grotesk"), "ui-sans-serif", "system-ui", "sans-serif"),
    font_mono=(gr.themes.GoogleFont("Space Mono"), "ui-monospace", "monospace"),
    primary_hue="indigo",
    secondary_hue="purple",
    neutral_hue="slate",
    radius_size="lg",
).set(
    body_background_fill="*neutral_950",
    body_text_color="*neutral_50",
    background_fill_primary="*neutral_900",
    background_fill_secondary="*neutral_800",
    border_color_accent="*primary_500",
    border_color_primary="*neutral_700",
    color_accent_soft="*neutral_800",
    block_background_fill="rgba(15, 23, 42, 0.6)",
    block_border_width="1px",
    block_border_color="rgba(255, 255, 255, 0.1)",
    block_radius="*radius_lg",
    block_label_background_fill="*neutral_800",
    block_label_text_color="*neutral_200",
    button_primary_background_fill="linear-gradient(135deg, #6366f1, #8b5cf6)",
    button_primary_background_fill_hover="linear-gradient(135deg, #4f46e5, #7c3aed)",
    button_primary_text_color="white",
    button_primary_border_color="transparent",
    button_secondary_background_fill="*neutral_800",
    button_secondary_background_fill_hover="*neutral_700",
    button_secondary_text_color="*neutral_50",
    button_secondary_border_color="*neutral_700",
    input_background_fill="*neutral_800",
    input_border_color="*neutral_700",
    input_border_color_focus="*primary_500",
)

custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Space+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap');

body, input, textarea, select, button, span, p, h1, h2, h3, h4, h5, h6, label {
    font-family: 'Space Grotesk', 'Inter', 'ui-sans-serif', 'system-ui', sans-serif;
}
code, pre, .mono, .kanban-container, .suggestion-grid, table.dataframe, .chatbot .message {
    font-family: 'Space Mono', 'Courier New', Courier, monospace !important;
}
body {
    background: radial-gradient(circle at top center, #1e1b4b 0%, #020617 100%) !important;
}
.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
}
.header-title h1 {
    background: -webkit-linear-gradient(45deg, #818cf8, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 900;
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
}
.gr-button-primary {
    transition: all 0.2s ease-in-out !important;
    box-shadow: 0 4px 14px 0 rgba(99, 102, 241, 0.39) !important;
}
.gr-button-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5) !important;
}
.kanban-container { font-family: 'Space Mono', 'Courier New', Courier, monospace !important; }
/* Expand the dataframe to fill full width */
.suggestion-grid, .suggestion-grid .table-wrap, .suggestion-grid > div {
    width: 100% !important;
    max-width: 100% !important;
}
/* Force chatbot and input-row to take full width */
#chat-box, #input-row {
    width: 100% !important;
    max-width: 100% !important;
}
/* Exact Gradio 6 Svelte dataframe cell selector */
span.svelte-odwpey.text.wrap[role="button"] {
    transition: outline 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
    border-radius: 4px;
    display: inline-block;
}
span.svelte-odwpey.text.wrap[role="button"]:hover {
    outline: 2px solid #10b981 !important;
    outline-offset: 2px;
    box-shadow: 0 0 10px 3px rgba(16, 185, 129, 0.7) !important;
    background-color: rgba(16, 185, 129, 0.15) !important;
    cursor: pointer !important;
}
"""

HOVER_GLOW_JS = """
function applyGlowEffect() {
    function attachHover(el) {
        if (el._glowAttached) return;
        el._glowAttached = true;
        el.style.transition = 'outline 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease';
        el.style.borderRadius = '4px';
        el.addEventListener('mouseover', function(e) {
            e.stopPropagation();
            this.style.outline = '2px solid #10b981';
            this.style.boxShadow = '0 0 10px 3px rgba(16, 185, 129, 0.7)';
            this.style.backgroundColor = 'rgba(16, 185, 129, 0.15)';
            this.style.cursor = 'pointer';
        });
        el.addEventListener('mouseout', function() {
            this.style.outline = '';
            this.style.boxShadow = '';
            this.style.backgroundColor = '';
        });
    }
    function scan() {
        document.querySelectorAll('.suggestion-grid span[role="button"]').forEach(attachHover);
    }
    scan();
    const obs = new MutationObserver(scan);
    obs.observe(document.body, { childList: true, subtree: true });
}
"""

with gr.Blocks() as demo:

    gr.Markdown("""
# 🛡️ LLM Scaffolding Architecture (ReAct + RAG & Self-Correction)
### Example Application: 🔭 AI Observation Catalog
""", elem_classes=["header-title"])

    gr.Markdown("""
This dashboard showcases a production-grade **LLM Scaffolding Architecture** for sandboxing database-interacting AI agents. 
Instead of direct database access, the agent produces structured tool intents (**ReAct + RAG**) which are intercepted, checked by a deterministic **Pydantic Validation Gate**, and automatically **self-corrected** via a retry loop before safe execution.

[[GitHub Repo]](https://github.com/yourname/ai-task-scaffold) · [[Read the writeup]](https://github.com/yourname/ai-task-scaffold#readme)
""")

    with gr.Tab("💬 Chat"):
        with gr.Accordion("ℹ️ How to Use & Examine Scaffolding (ReAct + RAG)", open=True):
            gr.Markdown("""
### 🔍 How to examine the scaffolding in action:

1. **Trigger the self-correction loop:**
   * **Try this prompt:** `Update object NGC-9999 to Confirmed`
   * *What happens:* `NGC-9999` doesn't exist in the database. The LLM will construct a valid JSON status update action, but the **validation gate (Stage 3)** will intercept the fake ID and throw a validation error. The orchestration layer (`agent.py`) catches this error, feeds it back to the LLM, and asks it to self-correct.

2. **Test ambiguity handling (CLARIFICATION_NEEDED):**
   * **Try this prompt:** `Schedule the weird one near Orion`
   * *What happens:* The LLM realizes it can't map "the weird one" to a specific catalog UUID. Instead of guessing and updating a random object, it safely calls the `CLARIFICATION_NEEDED` tool to ask you for more details.

3. **Check the Live Audit Log & Metrics:**
   * Go to the **📊 Reliability Metrics** tab. Every single action (success, self-corrected, or failed) is permanently logged in the `ai_action_log` table. You can see how many times the AI failed validation and had to self-correct!

4. **Test Forced Self-Correction (Advanced Setting):**
   * Expand the **⚙️ Advanced: Force 1st-Pass Failure** accordion below and verify/change the secret word (e.g., `BANANA`).
   * Ask the assistant any command, e.g., `Schedule Betelgeuse`.
   * *What happens:* The validation gate will fail on the first pass because the LLM didn't use `BANANA` in its reasoning. Watch the assistant catch the error and automatically retry, adding `BANANA` to its reasoning to satisfy the gate!
""")

        with gr.Accordion("⚙️ Advanced: Force 1st-Pass Failure (Test Self-Correction)", open=False):
            gr.Markdown("Inject a secret business rule into the backend Pydantic schema that the AI doesn't know about. This guarantees it will fail on Pass 1, forcing a self-correction.")
            secret_input = gr.Textbox(
                label="Secret Required Word",
                value="BANANA",
                placeholder="If set, the AI MUST use this exact word in its reasoning string...",
            )

        gr.Markdown(
            "*Try the examples below — mix of clear commands, ambiguous requests, and "
            "nearly-irrelevant prompts. Watch the validation gate catch hallucinated IDs and the self-correction loop in action.*"
        )

        # ── Custom Chat UI ───
        chatbot = gr.Chatbot(height=280, label="Astronomer's Assistant", elem_id="chat-box")
        
        with gr.Row(elem_id="input-row"):
            msg = gr.Textbox(
                scale=4,
                show_label=False,
                placeholder="Type a command (e.g. 'Schedule all K-type stars') and press Enter...",
                container=False,
            )
            submit_btn = gr.Button("Send", scale=1, variant="primary")

        # Suggestion cards (Categorized Grid)
        gr.Markdown("### 💡 Test the Scaffolding (Click any cell to send)")
        suggestions = gr.Dataframe(
            headers=[
                "✅ Clear (Actionable)", 
                "🔗 Multi-Step",
                "🤔 Less Ambiguous", 
                "❓ 70% Ambiguous", 
                "❌ Unclear / Irrelevant", 
                "😈 Adversarial"
            ],
            value=[
                [
                    "Schedule all K-type stars for observation",
                    "Mark Andromeda as Confirmed and schedule Apophis",
                    "Flag the weird one near Orion",
                    "Is Apophis going to hit us?",
                    "What's for lunch?",
                    "Update object NGC-9999 to Confirmed"
                ],
                [
                    "Mark Apophis as Critical priority",
                    "Flag Orion Nebula as Anomalous and set Betelgeuse to Critical",
                    "Prioritise anything that might have life",
                    "How hot is a K-type star anyway?",
                    "help",
                    "Flag all stars brighter than magnitude 2 as high priority"
                ],
                [
                    "Set TRAPPIST-1e to Scheduled and Critical priority",
                    "Log a new Star called 'Sirius C' and make sure Vega is Low priority",
                    "Schedule the usual observations",
                    "Schedule a meeting with the Crab Nebula",
                    "Is it cloudy tonight?",
                    ""
                ],
                [
                    "Log a new Asteroid called 'Oumuamua'",
                    "",
                    "It's moving",
                    "Mark the weather as Cloudy",
                    "",
                    ""
                ]
            ],
            interactive=False,
            wrap=True,
            elem_classes=["suggestion-grid"],
        )





        # ── Kanban Board (Initially hidden, revealed on first chat) ───
        kanban_visible = gr.HTML(visible=False, elem_classes=["kanban-container"])

        # Wire up chat submit
        msg.submit(
            fn=handle_user_submit,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot]
        ).then(
            fn=chat_response_handler,
            inputs=[chatbot, secret_input],
            outputs=[chatbot, suggestions, kanban_visible]
        )

        submit_btn.click(
            fn=handle_user_submit,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot]
        ).then(
            fn=chat_response_handler,
            inputs=[chatbot, secret_input],
            outputs=[chatbot, suggestions, kanban_visible]
        )
        
        def handle_suggestion_click(evt: gr.SelectData, history: list) -> tuple[str, list]:
            if not evt.value:  # Ignore clicks on empty padding cells
                return "", history
            new_message = {"role": "user", "content": [{"type": "text", "text": str(evt.value)}]}
            return "", history + [new_message]

        # When a cell in the dataframe is clicked, automatically send it
        suggestions.select(
            fn=handle_suggestion_click,
            inputs=[chatbot],
            outputs=[msg, chatbot]
        ).then(
            fn=chat_response_handler,
            inputs=[chatbot, secret_input],
            outputs=[chatbot, suggestions, kanban_visible]
        )

    with gr.Tab("PDF Data Extractor"):
        gr.Markdown("### 📄 Structured Data Extraction")
        gr.Markdown("Upload a messy PDF invoice. The AI will extract it into a rigidly structured JSON object. The backend enforces strict math validation (Quantity * Price = Total) and will force the AI to self-correct if it hallucinates the numbers!")
        
        with gr.Accordion("ℹ️ How to Use & Examine PDF Data Extraction", open=True):
            gr.Markdown("""
### 🔍 How to examine the PDF Scaffolding in action:

1. **Get a test file:** Find one of the provided test invoices in your workspace directory (e.g., `test_invoice.pdf` or `test_complex_invoice.pdf`).
2. **Upload & Extract:** Upload the PDF file, select the **Invoice** target schema, and click **Extract Structured Data**.
3. **Pydantic Validation:** The AI processes the text and converts it to JSON matching the target Pydantic schema. The backend automatically checks that:
   * The JSON structure matches the schema layout.
   * **Math check (Invoice):** The math for all lines is validated (`quantity * price == total`), and the sum of all item line totals equals the invoice subtotal.
   * **Math check (Medical Record):** The BMI is mathematically validated against height and weight.
4. **Self-Correction:** If the AI hallucinates a math total or output format, the validation gate catches it, intercepts the write, and instructs the LLM to self-correct and recalculate the values.
5. **Test Forced Self-Correction (Advanced Setting):**
   * Expand the **⚙️ Advanced: Force 1st-Pass Failure** accordion below.
   * Enter a secret required word (e.g., `BANANA`).
   * Click **Extract Structured Data**.
   * *What happens:* Because the LLM does not know about this requirement initially, it will generate JSON without this word. The **Pydantic Validation Gate** catches it, triggers a validation failure, and passes the error back. The AI automatically self-corrects on the next attempt by including the secret word in its reasoning field, resulting in a successful extraction!
""")

        with gr.Accordion("⚙️ Advanced: Force 1st-Pass Failure (Test Self-Correction)", open=False):
            gr.Markdown("Inject a secret business rule into the backend Pydantic schema that the AI doesn't know about. This guarantees it will fail on Pass 1, forcing a self-correction.")
            pdf_secret_input = gr.Textbox(
                label="Secret Required Word",
                value="BANANA",
                placeholder="If set, the AI MUST use this exact word in its reasoning string...",
            )

        with gr.Row():
            with gr.Column(scale=1):
                pdf_upload = gr.File(label="Upload PDF", file_types=[".pdf"])
                doc_type_dropdown = gr.Dropdown(["Invoice", "Patient Medical Record"], value="Invoice", label="Target Schema")
                pdf_instruction = gr.Textbox(label="Instruction", value="Extract the document details exactly as they appear.", lines=2)
                extract_btn = gr.Button("Extract Structured Data", variant="primary")
            
            with gr.Column(scale=2):
                pdf_status = gr.Markdown("Waiting for upload...")
                pdf_output = gr.Code(language="json", label="Validated JSON Output")
                
        extract_btn.click(
            extract_pdf_handler,
            inputs=[pdf_upload, pdf_instruction, doc_type_dropdown, pdf_secret_input],
            outputs=[pdf_status, pdf_output],
        )

    with gr.Tab("A/B Scaffolding Evaluation"):
        gr.Markdown("## The Scaffolding Test")
        gr.Markdown("Upload a complex document with broken math (e.g., `test_complex_invoice_no_note.pdf`). This tab runs the exact same LLM prompt down two parallel tracks: one with our Scaffolding Architecture, and one without. Watch what happens to your data!")
        
        with gr.Accordion("ℹ️ How to Use & Compare Scaffolding A/B tracks", open=True):
            gr.Markdown("""
### 🔍 How to run the A/B Scaffolding Evaluation:

1. **Use a broken-math file:** Select `test_complex_invoice_no_note.pdf` from your project folder. This invoice contains intentionally corrupted line totals (e.g. quantity or price multiplication is wrong in the document itself).
2. **Execute A/B Test:** Upload this file, select the **Invoice** target schema, and click **Run A/B Evaluation**.
3. **Compare the Tracks:**
   * **❌ Unscaffolded AI (Left):** The raw LLM copies the numbers. It doesn't run any backend validations. If it hallucinates the math or copies bad math, it simply saves the bad data.
   * **🛡️ Scaffolded AI (Right):** The scaffolded pipeline runs the validation gate. It catches the broken math (where `quantity * price != total` in the document), rejects it, and starts a **self-correction loop** using feedback prompts, forcing the LLM to recalculate the correct values before writing to the database!
4. **Test Forced Self-Correction (Advanced Setting):**
   * Expand the **⚙️ Advanced: Force 1st-Pass Failure** accordion below and enter a secret word (e.g., `BANANA`).
   * Click **Run A/B Evaluation**.
   * *What happens:* The **❌ Unscaffolded AI (Left)** will fail completely because it does not retry. The **🛡️ Scaffolded AI (Right)** will fail on its first attempt, receive the validation feedback, and immediately self-correct to satisfy the schema before displaying the final validated JSON!
""")

        with gr.Accordion("⚙️ Advanced: Force 1st-Pass Failure (Test Self-Correction)", open=False):
            gr.Markdown("Inject a secret business rule into the backend Pydantic schema that the AI doesn't know about. This guarantees it will fail on Pass 1, forcing a self-correction.")
            eval_secret_input = gr.Textbox(
                label="Secret Required Word",
                value="BANANA",
                placeholder="If set, the AI MUST use this exact word in its reasoning string...",
            )

        with gr.Row():
            eval_upload = gr.File(label="Upload PDF", file_types=[".pdf"])
            eval_schema = gr.Dropdown(["Invoice", "Patient Medical Record"], value="Invoice", label="Target Schema")
            eval_instruction = gr.Textbox(
                label="Instruction", 
                value="Extract the document details exactly as they appear. DO NOT fix any math errors in the document, just blindly copy the numbers you see.", 
                lines=2
            )
            eval_btn = gr.Button("Run A/B Evaluation", variant="primary")
            
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### ❌ Unscaffolded AI (Raw LLM)")
                unscaffolded_status = gr.Markdown("Waiting...")
                unscaffolded_output = gr.Code(language="json", label="Raw JSON Output")
            
            with gr.Column(scale=1):
                gr.Markdown("### 🛡️ Scaffolded AI (Validation + Retry Loop)")
                scaffolded_status = gr.Markdown("Waiting...")
                scaffolded_output = gr.Code(language="json", label="Final Validated JSON")
                
        eval_btn.click(
            run_evaluation,
            inputs=[eval_upload, eval_instruction, eval_schema, eval_secret_input],
            outputs=[unscaffolded_status, unscaffolded_output, scaffolded_status, scaffolded_output]
        )

    with gr.Tab("📋 Full Catalog"):
        gr.Markdown("*Full catalog view — Kanban style.*")
        kanban_full = gr.HTML(elem_classes=["kanban-container"])
        gr.Button("🔄 Refresh").click(fn=render_kanban, outputs=kanban_full)
        demo.load(fn=render_kanban, outputs=kanban_full)

    with gr.Tab("📊 Reliability Metrics"):
        gr.Markdown("""
### Live metrics from `ai_action_log`
- **First-pass success** = valid JSON on first attempt
- **Self-corrected** = failed then recovered within 2 retries
- **Failed** = exhausted all retries
""")
        metrics_display = gr.JSON(label="Metrics (all-time)")
        gr.Button("🔄 Refresh Metrics").click(fn=refresh_metrics, outputs=metrics_display)
        demo.load(fn=refresh_metrics, outputs=metrics_display)

    with gr.Tab("ℹ️ How It Works"):
        gr.Markdown("""
## What is Deterministic Scaffolding?

Most AI agents are allowed to write direct database queries (like SQL) or execute raw code. This is extremely dangerous and unpredictable because LLMs hallucinate. 

**Deterministic Scaffolding** is a design pattern where the AI is placed in a "sandbox". It cannot touch the database. Instead, the AI only outputs structured JSON requests (intents), which are then strictly validated by traditional, deterministic Python code before anything is executed.

---

### ❌ Without Scaffolding (Traditional Agents)
- **User:** "Schedule TRAPPIST-1e and TRAPPIST-1f for observation."
- **AI:** Writes `UPDATE celestial_objects SET status = 'Scheduled' WHERE name LIKE 'TRAPPIST%';`
- **Result:** The AI hallucinates a SQL injection, accidentally updates 7 other planets, or crashes because it used the wrong table name. The user has no idea what happened.

### ✅ With Scaffolding (This Architecture)
1. **User:** "Schedule TRAPPIST-1e and TRAPPIST-1f for observation."
2. **AI Intent:** Outputs `{"action_type": "UPDATE_STATUS", "target_object_ids": ["uuid-1", "uuid-2"], "new_status": "Scheduled"}`
3. **The Gate:** Python intercepts the JSON and checks:
   - *Is it valid JSON?*
   - *Does it match our Pydantic schema?*
   - *Do those UUIDs actually exist in the database?*
   - *Does this user have permission to edit them?*
4. **Execution:** Only if all checks pass, a secure, parameterized Supabase function is called.

---

## The 4-Stage Validation Gate

```text
User input
    ↓
scaffold/agent.py     ← Orchestration + Self-Correction loop (max 2 retries)
    ↓
scaffold/llm.py       ← Multi-provider wrapper (GitHub Models / Groq)
    ↓ raw JSON string
scaffold/validate.py  ← 🛡️ THE 4-STAGE GATE:
                          [1] JSON syntax check
                          [2] Pydantic discriminated union schema validation
                          [3] Business rules (IDs must exist in catalog)
                          [4] Authorization (user must own the objects)
    ↓ (PASS only)
scaffold/execute.py   ← Deterministic, parameterized Supabase queries
    ↓
scaffold/db.py        ← Full audit log written for every action
```

---

## 🔍 How to examine this in action

Want to see the scaffolding working? Try these experiments in the Chat tab:

1. **Trigger the self-correction loop:**
   - *Prompt:* `Update object NGC-9999 to Confirmed`
   - *What happens:* NGC-9999 doesn't exist. The LLM will output a valid JSON action, but **Stage 3** of the gate will catch the fake ID and throw an error. The orchestration layer (`agent.py`) intercepts this error, feeds it back to the LLM behind the scenes, and asks it to fix it. Eventually, it will fail safely instead of crashing the database.

2. **Test ambiguity (CLARIFICATION_NEEDED):**
   - *Prompt:* `Schedule the weird one near Orion`
   - *What happens:* The LLM realizes it can't map this to a specific UUID. Instead of guessing and updating a random object, it uses the fallback `CLARIFICATION_NEEDED` schema to safely ask you for more details.

3. **Check the Audit Log:**
   - Go to the **📊 Reliability Metrics** tab. Every single action (success, self-corrected, or failed) is permanently logged in the `ai_action_log` table. You can open your Supabase dashboard and see exactly how many times the AI failed validation and had to self-correct!
""")

demo.launch(theme=custom_theme, css=custom_css, js=HOVER_GLOW_JS, ssr_mode=False)

