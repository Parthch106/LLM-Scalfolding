---
title: LLM Scaffolding Architecture
emoji: 🛡️
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 6.16.0
app_file: app.py
pinned: false
---

# 🛡️ Deterministic AI Scaffolding Architecture

**Production-grade AI Orchestration using Pydantic, Supabase, and ReAct.**

This Hugging Face Space showcases a production-ready safety net around LLMs. Instead of granting database mutation access directly to the LLM agent, all operations output structured JSON intents which are checked by a deterministic **Pydantic Validation Gate** and self-corrected in a retry loop.

### Core Features:
- **💬 Sandboxed Chat & RAG:** Astronomy object catalog with ambiguity checks and verification.
- **📄 PDF Data Extraction:** Real-time extraction of structured data from invoice PDFs with strict math validation.
- **⚖️ Comparative A/B Test:** Parallel evaluation comparing scaffolded self-correction against raw, unscaffolded LLM parsing.
