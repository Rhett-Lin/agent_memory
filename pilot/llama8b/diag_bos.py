"""Diagnostic 2: does vllm 0.6.6 llm.chat double-add BOS for Llama-3.1?

Qwen2.5's tokenizer adds no BOS, so a double-BOS bug would hit ONLY Llama -
precisely the 'different special tokens' plumbing issue anticipated by the
pilot task. Checks: rendered chat text vs token ids the engine actually used.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generate_families import load_config

CFG = "/work1/zixuan/projects/agent_memory/pilot/configs/pilot_llama8b.yaml"
cfg = load_config(CFG)
msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}]

from vllm import LLM, SamplingParams
llm = LLM(model=cfg["models"]["llama8b"], gpu_memory_utilization=0.85,
          max_model_len=8192, dtype="float16", disable_log_stats=True)
tok = llm.get_tokenizer()

text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
print("rendered starts:", repr(text[:60]))
ids_plain = tok(text, add_special_tokens=True)["input_ids"]
ids_no_sp = tok(text, add_special_tokens=False)["input_ids"]
out = llm.chat([msgs], sampling_params=SamplingParams(
    temperature=0, max_tokens=1), add_generation_prompt=True, use_tqdm=False)[0]
eng = out.prompt_token_ids
bos = tok.bos_token_id
print("bos_id:", bos)
print("tokenizer(add_special_tokens=True )[:3]:", ids_plain[:3])
print("tokenizer(add_special_tokens=False)[:3]:", ids_no_sp[:3])
print("engine prompt_token_ids[:3]:          ", list(eng[:3]))
print("engine leading BOS count:", sum(1 for i in eng[:4] if i == bos))
print("DOUBLE_BOS" if list(eng[:2]) == [bos, bos] else "single/✓")
