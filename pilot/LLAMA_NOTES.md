# LLAMA_NOTES.md — Llama-3.1-8B second-family plumbing record

Task: second-model-family pilot for CausalMemAgent with
`NousResearch/Meta-Llama-3.1-8B-Instruct` (config
`pilot/configs/pilot_llama8b.yaml`, byte-identical to
`pilot/configs/pilot_7b.yaml` except the added `llama8b` model entry —
verified by `diff`).

## Problem

First selfcheck (`python harness.py --selfcheck --model llama8b --config
configs/pilot_llama8b.yaml`) **FAILED** the pre-registered gate:

- parseable-action rate **0.837** (41/49 steps), gate ≥ 0.90
- 8 failing steps: 7× JSON missing exactly the outermost closing `}` before
  generation stopped (all `filter`-nested aggregates/reads on family 4),
  1× arithmetic expression inside JSON (`"qty": 52 - 10`).

## Token-level diagnosis (scripts kept in `pilot/llama8b/`)

1. `diag_brace.py` — reconstructed the exact failing conversation (family 4,
   N cell, step 3) from `logs/agent_memory/selfcheck_llama8b.jsonl` and
   re-generated. Both the seeded sample **and greedy decoding** emit the
   identical 52 tokens ending `"}}` + `<|eot_id|>`: finish_reason=stop, the
   brace is absent in the model's own token stream. EOS/eot routing and
   detokenization are faithful — not the root cause at that layer.
2. `diag_bos.py` — **root cause found: doubled BOS**. vllm 0.6.6.post1
   `LLM.chat` renders the HF chat template to text (the stock Llama-3.1
   template prepends `<|begin_of_text|>`) and then lets the engine
   retokenize with `add_special_tokens=True`, adding a second BOS:
   engine prompt ids `[128000, 128000, 128006, ...]`. Qwen2.5's tokenizer
   has no BOS to add, so the qwen runs were never affected — this is a
   Llama-only special-token plumbing defect. The out-of-distribution
   double-BOS prefix is what degraded Llama's structured-output behavior.

## Fix (chat-template plumbing only; zero semantic change)

One change in `pilot/harness.py`: `_run_chunk` now calls a new helper
`_chat_single_bos()` instead of `llm.chat(...)`. The helper renders the same
chat template text (`tokenizer.apply_chat_template(..., tokenize=False,
add_generation_prompt=True)`) and encodes it once with
`add_special_tokens=False`, feeding `TokensPrompt` ids directly to
`llm.generate(...)`. Prompt text, system/user messages, sampling parameters,
parsing (`parse_action`), retry and success logic are all untouched.

Qwen behavior is provably identical: for `Qwen/Qwen2.5-7B-Instruct` the
tokenizer's `add_special_tokens` path adds nothing, so the old and new
prompt token-id sequences are byte-identical (verified on CPU:
`identical: True` for qwen7b; token stream differs only for Llama, where it
now starts with a single `<|begin_of_text|>`).

## Verdict after fix

Selfcheck rerun with the identical command:

- parseable-action rate **0.978 (44/45) ≥ 0.90 -> PASS**
- per-family: fam0 6/6, fam1 7/7, fam2 10/11, fam3 11/11, fam4 10/10
  (fam4 previously 5/12 — the brace-drop pathology is gone; the only
  remaining failure is a single arithmetic-in-JSON slip on fam2).
- N-condition success 2/5 on the five selfcheck tasks (not a gate metric).

Files changed: `pilot/harness.py` (helper + one call site, 2 hunks).
Files added: `pilot/configs/pilot_llama8b.yaml` (config copy + model entry),
`pilot/llama8b/diag_brace.py`, `pilot/llama8b/diag_bos.py` (diagnostics,
audit trail). No hyperparameter, prompt, parser, or terminal-predicate
changes.
