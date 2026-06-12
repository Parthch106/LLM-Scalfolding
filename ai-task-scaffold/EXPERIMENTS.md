# LLM Scaffolding Experiments Log

This document tracks the various architectural experiments, stress tests, and AI red-teaming scenarios we conducted to test and harden the Agentic Orchestration Layer.

## Experiment 1: Multi-Action JSON Arrays
**Goal:** Test if the LLM could parse complex, chained user intents (e.g., *"Flag Orion Nebula as Anomalous and set Betelgeuse to Critical"*).
**Outcome:** We updated the `SYSTEM_PROMPT` to instruct the LLM to return a JSON array `[ {action1}, {action2} ]`. We then updated `execute.py` and `validate.py` to loop over these arrays, effectively allowing the AI to execute multi-step database transactions atomically.

## Experiment 2: Dynamic Business Rule Enforcement (The "BANANA" Rule)
**Goal:** Force the AI to fail its initial attempt to observe the self-correction loop in action.
**Outcome:** We added a dynamic UI textbox that injected a secret word (e.g., "BANANA") deep into the Pydantic Schema's validation context (`@model_validator`). If the LLM failed to include this exact word in its `reasoning` string, the Python backend rejected the payload and fed the exception trace back to the LLM. The AI successfully learned to read the Python stack trace and correct itself on Attempt 2.

## Experiment 3: The "Whack-A-Mole" Array Trap
**Goal:** Observe what happens when an LLM fails multiple rules simultaneously inside an array.
**Outcome:** We discovered a classic LLM logic trap. Because the original Validation Gate crashed and returned immediately upon finding the *first* error, the LLM would fix Action 1 on its retry, but forget to apply the fix to Action 2. On the next retry, it would fix Action 2, but regress and break Action 1!
**Solution:** We completely rewrote `validate.py` to aggregate *all* errors across the entire array into a single massive crash report. Giving the LLM the complete picture allowed it to fix all objects simultaneously.

## Experiment 4: Native Tool Calling & Structured Outputs
**Goal:** Eliminate syntax errors (like missing JSON brackets).
**Outcome:** We stripped out the markdown JSON instructions and refactored `llm.py` to use native OpenAI `tools`. We extracted the schemas directly from our Pydantic classes via `model_json_schema()` and forced execution with `tool_choice="required"`. The scaffolding layer now parses the native `tool_calls` directly, resulting in perfectly structured payloads every time.

## Experiment 5: Dynamic Few-Shot Injection & Context Poisoning
**Goal:** Help the AI learn from its past mistakes by building an "Experience Buffer".
**Outcome:** We created an in-memory `_correction_memory` array in `agent.py`. If the AI successfully fixed a rule violation (like the BANANA rule), we saved the successful JSON and injected it into future prompts as a Few-Shot example.
**The Red-Team Discovery:** The user executed a brilliant "Context Poisoning" attack. They changed the secret word to "Apple" and ran a simple single-action prompt. The AI crashed, triggering the injection of the massive multi-action Few-Shot example from the past. The LLM saw the past example and hallucinated actions from the *past* prompt (Betelgeuse) into the *current* prompt! This perfectly demonstrated the danger of overfitting to highly specific Few-Shot examples in agentic pipelines.
