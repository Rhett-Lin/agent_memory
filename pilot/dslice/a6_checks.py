"""H-DC A6 auxiliary checks (auto-review-loop round 1, thread 019fe135).

Two evidence gaps the reviewer flagged in the A6 appendix paragraph:

1. Qwen tokenization no-op.  harness.py::_chat_single_bos (commit 8bee901)
   replaced llm.chat() with render-once + encode-once
   (add_special_tokens=False).  The claim "token-id-identical on Qwen2.5"
   had no archived output.  Here we verify it directly on CPU with the
   frozen HF snapshot: render the chat text once, then compare
   tokenizer(text, add_special_tokens=True) vs (False) id streams for the
   exact system+user prompt shapes the harness uses.

2. First-row metadata.  analyze_dslice.py's a6_report sampled metas[:1]
   per arm.  Here we scan EVERY A-cell rollout row of every H-DC arm and
   report the distinct config_hash / env_versions / git_commit values.

Run from pilot/ (CPU only, no GPU):
  python dslice/a6_checks.py --config configs/pilot_7b.yaml
"""

import argparse
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config  # noqa: E402

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
ARMS = ["dslice", "raw_matched", "raw"]
MODELS = ["qwen7b", "qwen3b"]


def _tokenizer_revision(tok_path):
    """HF cache snapshot revision, if resolvable locally."""
    try:
        from huggingface_hub import snapshot_download
        p = snapshot_download(tok_path, local_files_only=True)
        rev = os.path.basename(os.path.normpath(p))
        return {"resolved": p, "revision": rev}
    except Exception as e:  # noqa: BLE001
        return {"resolved": tok_path, "revision": None,
                "note": "local snapshot not resolvable: %s" % type(e).__name__}


def token_id_check(cfg):
    from transformers import AutoTokenizer
    from harness import SYSTEM_PROMPT, FIRST_USER_TMPL
    first_no_mem = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FIRST_USER_TMPL.format(
            instruction="INS", memory_block="", max_steps=12)}]
    first_mem = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FIRST_USER_TMPL.format(
            instruction="INS", memory_block="MEM", max_steps=12)}]
    follow_turns = [
        {"role": "assistant", "content":
            '{"tool": "read", "args": {"table": "T", "filter": {"c": "v"}}}'},
        {"role": "user", "content":
            "<tool_result>{\"ok\": true, \"rows\": [{\"c\": \"v\"}]}"
            "</tool_result>"},
        {"role": "assistant", "content":
            '{"tool": "update", "args": {"table": "T", "filter": {"c": "v"}, '
            '"set": {"d": 1}}}'},
        {"role": "user", "content":
            "<tool_result>{\"ok\": true, \"changed\": 1}</tool_result>"}]
    shapes = {"first-turn sys+user(no memory)": first_no_mem,
              "first-turn sys+user(with memory)": first_mem,
              "multi-turn 2 tool rounds(with memory)": first_mem + follow_turns,
              "multi-turn 2 tool rounds(no memory)":
                  first_no_mem + follow_turns}
    per_model = {}
    for model_key in ("qwen7b", "qwen3b"):
        tok_path = cfg["models"][model_key]
        tok = AutoTokenizer.from_pretrained(tok_path)
        rec = {"tokenizer": tok_path,
               **_tokenizer_revision(tok_path),
               "bos_token_id": tok.bos_token_id, "shapes": {}}
        for name, msgs in shapes.items():
            text = tok.apply_chat_template(msgs, tokenize=False,
                                           add_generation_prompt=True)
            a = tok(text, add_special_tokens=True)["input_ids"]
            b = tok(text, add_special_tokens=False)["input_ids"]
            rec["shapes"][name] = {"len": len(a), "identical": a == b,
                                   "render_start": text[:48]}
        rec["all_identical"] = all(s["identical"]
                                   for s in rec["shapes"].values())
        per_model[model_key] = rec
    return {"per_model": per_model,
            "all_identical": all(r["all_identical"]
                                 for r in per_model.values())}


def full_meta_scan(cfg):
    rep = {}
    root = cfg["paths"]["output_root"]
    for m in MODELS:
        rep[m] = {}
        pats = {"pilot": os.path.join(root,
                                      "rollouts_%s_shard*-of-*.jsonl" % m)}
        for a in ARMS:
            pats[a] = os.path.join(
                root, "rollouts_hc_%s_%s_shard*-of-*.jsonl" % (a, m))
        for arm, pat in pats.items():
            files = sorted(glob.glob(pat))
            if arm == "pilot":
                files = [f for f in files if "_hc_" not in f]
            hashes, envs, commits, n, seen_rows = set(), set(), set(), 0, 0
            missing = {"config_hash": 0, "env_versions": 0, "git_commit": 0}
            for fn in files:
                with open(fn) as f:
                    for line in f:
                        r = json.loads(line)
                        mt = r.get("meta", {})
                        if mt.get("model") != m:
                            continue
                        sysname = mt.get("system", "procedural")
                        if arm != "pilot" and sysname != arm:
                            continue
                        seen_rows += 1
                        if mt.get("cell") in ("N", "Q") and arm == "pilot":
                            n += 1
                        hashes.add(mt.get("config_hash"))
                        envs.add(json.dumps(mt.get("env_versions"),
                                            sort_keys=True))
                        commits.add(mt.get("git_commit"))
                        for k in missing:
                            if mt.get(k) in (None, "", {}):
                                missing[k] += 1
            rep[m][arm] = {"rows": seen_rows,
                           "n_config_hash": len(hashes),
                           "config_hash": sorted(h for h in hashes if h),
                           "n_env_versions": len(envs),
                           "env_versions": sorted(e for e in envs if e),
                           "n_git_commits": len(commits),
                           "git_commits": sorted(c for c in commits if c),
                           "missing_field_rows": missing}
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args()
    cfg = load_config(args.config)
    rep = {"token_id_check": token_id_check(cfg),
           "full_meta_scan": full_meta_scan(cfg)}
    out = os.path.join(_HERE, "A6_CHECKS.json")
    with open(out, "w") as f:
        json.dump(rep, f, indent=1, sort_keys=True, default=str)
    t = rep["token_id_check"]
    print("[a6] qwen token-id identical (all models/shapes):",
          t["all_identical"])
    for mk, r in sorted(t["per_model"].items()):
        print("[a6]   %-7s bos=%s rev=%s identical=%s"
              % (mk, r["bos_token_id"], r["revision"], r["all_identical"]))
    for m in MODELS:
        for arm, r in rep["full_meta_scan"][m].items():
            print("[a6] %-7s %-12s rows=%-5d config_hash=%d env=%d commits=%s "
                  "missing=%s"
                  % (m, arm, r["rows"], r["n_config_hash"],
                     r["n_env_versions"], r["git_commits"],
                     r["missing_field_rows"]))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
