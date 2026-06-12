import json
from .llm import _get_client, _CONFIGS
from .pdf_schemas import InvoiceData, MedicalRecordData

SYSTEM_PROMPT = """You are an expert Data Extraction AI. 
Your job is to read unstructured text from a PDF document and extract it perfectly into the provided JSON schema.

CRITICAL RULES:
- You must accurately extract all line items, subtotals, taxes, and final totals.
- The schema includes strict math validation (quantity * unit_price = total, etc.). Ensure your extracted numbers pass this math!
- If the document contains math errors, you must mathematically fix them in your output so it passes the strict validation gate.
- If a value is missing, infer it if mathematically possible, otherwise default to 0."""

INVOICE_TOOL = {
    "type": "function",
    "function": {
        "name": "EXTRACT_INVOICE",
        "description": "Extract structured invoice data from the unstructured text.",
        "parameters": InvoiceData.model_json_schema()
    }
}

MEDICAL_TOOL = {
    "type": "function",
    "function": {
        "name": "EXTRACT_MEDICAL_RECORD",
        "description": "Extract structured patient medical data from the unstructured text.",
        "parameters": MedicalRecordData.model_json_schema()
    }
}

def extract_pdf_data(
    pdf_text: str,
    user_prompt: str,
    document_type: str = "Invoice",
    provider: str = "github"
) -> str:
    """Send PDF text to LLM and get the structured JSON string back."""
    # Remove large empty spaces to save tokens
    clean_text = "\n".join([line.strip() for line in pdf_text.splitlines() if line.strip()])
    
    _, _, model_id = _CONFIGS[provider]

    full_prompt = (
        f"--- PDF DOCUMENT TEXT ---\n{clean_text}\n-------------------------\n\n"
        f"User Instruction: {user_prompt}"
    )
    
    if document_type == "Patient Medical Record":
        tools = [MEDICAL_TOOL]
        tool_choice = {"type": "function", "function": {"name": "EXTRACT_MEDICAL_RECORD"}}
    else:
        tools = [INVOICE_TOOL]
        tool_choice = {"type": "function", "function": {"name": "EXTRACT_INVOICE"}}

    client = _get_client(provider)
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt},
        ],
        temperature=0,
        tools=tools,
        tool_choice=tool_choice
    )
    
    msg = response.choices[0].message
    if msg.tool_calls:
        call = msg.tool_calls[0]
        try:
            args = json.loads(call.function.arguments)
            return json.dumps(args, indent=2)
        except json.JSONDecodeError:
            return "{}"
            
    return "{}"
