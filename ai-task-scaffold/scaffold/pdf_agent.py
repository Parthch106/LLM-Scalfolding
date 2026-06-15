import json
from pydantic import ValidationError
from .pdf_llm import extract_pdf_data
from .pdf_schemas import InvoiceData, MedicalRecordData

MAX_RETRIES = 5

def run_pdf_agent(pdf_text: str, user_prompt: str, document_type: str = "Invoice", provider: str = "github", secret_word: str | None = None) -> dict:
    """
    Orchestration layer for PDF extraction.
    Wires together: LLM -> Validation Gate -> (Retry Loop).
    """
    attempts: list[dict] = []
    last_error: str | None = None

    for attempt in range(MAX_RETRIES + 1):
        prompt = user_prompt
        if last_error:
            prompt += (
                f"\n\n[SYSTEM CORRECTION — attempt {attempt + 1}/{MAX_RETRIES + 1}]: "
                f"The JSON you just generated failed backend validation with this error: {last_error}\n"
                f"CRITICAL: You MUST mathematically fix your own JSON output to satisfy the backend's rule and resend it."
            )

        try:
            raw = extract_pdf_data(pdf_text, prompt, document_type=document_type, provider=provider)
        except Exception as e:
            attempts.append({
                "attempt": attempt,
                "raw": "",
                "error": f"LLM API Error: {str(e)}",
                "valid": False,
            })
            break

        # Validate
        valid = False
        error_msg = None
        parsed_data = None
        
        try:
            if document_type == "Patient Medical Record":
                parsed_data = MedicalRecordData.model_validate_json(raw, context={"secret_word": secret_word})
            else:
                parsed_data = InvoiceData.model_validate_json(raw, context={"secret_word": secret_word})
            valid = True
        except ValidationError as e:
            # Flatten pydantic errors for the LLM
            errors = []
            for err in e.errors():
                loc = " -> ".join(map(str, err['loc'])) if err.get('loc') else "root"
                msg = err['msg']
                errors.append(f"[{loc}]: {msg}")
            error_msg = "Schema/Business Rule Violation:\n" + "\n".join(errors)
        except ValueError as e:
            error_msg = f"JSON Syntax Error: {str(e)}"
            
        attempts.append({
            "attempt": attempt,
            "raw": raw,
            "error": error_msg,
            "valid": valid,
        })
        
        if valid:
            return {
                "success": True,
                "status": "success" if attempt == 0 else "self_corrected",
                "attempts": attempts,
                "data": parsed_data.model_dump(mode="json")
            }
            
        last_error = error_msg
        
    return {
        "success": False,
        "status": "failed",
        "attempts": attempts,
        "data": None
    }

def run_unscaffolded_pdf_agent(pdf_text: str, user_prompt: str, document_type: str = "Invoice", provider: str = "github", secret_word: str | None = None) -> dict:
    """
    Runs the exact same extraction but WITHOUT the retry loop or self-correction.
    It simulates a raw LLM application.
    """
    try:
        raw = extract_pdf_data(pdf_text, user_prompt, document_type=document_type, provider=provider)
    except Exception as e:
        return {
            "success": False,
            "message": f"LLM API Error: {str(e)}",
            "raw": "",
            "status": "failed",
        }

    valid = False
    error_msg = None
    
    try:
        if document_type == "Patient Medical Record":
            parsed_data = MedicalRecordData.model_validate_json(raw, context={"secret_word": secret_word})
        else:
            parsed_data = InvoiceData.model_validate_json(raw, context={"secret_word": secret_word})
        valid = True
    except ValidationError as e:
        err_msgs = []
        for err in e.errors():
            loc = "->".join(str(l) for l in err["loc"]) if err.get("loc") else "root"
            err_msgs.append(f"[{loc}]: {err['msg']}")
        error_msg = "Schema/Business Rule Violation: " + "; ".join(err_msgs)
    except Exception as e:
        error_msg = f"Unknown Error: {str(e)}"

    if valid:
        return {
            "success": True,
            "message": "Perfect execution on Attempt 1!",
            "raw": raw,
            "status": "success",
        }
    else:
        return {
            "success": False,
            "message": error_msg,
            "raw": raw,
            "status": "failed",
        }
