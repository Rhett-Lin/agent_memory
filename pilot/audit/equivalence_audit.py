"""Gate B audit 4/4: program-equivalence audit (independent judge + oracle).

Two checks on the P=1 / near-miss labels that everything else rests on:

1) Independent-judge annotation (Qwen2.5-7B-Instruct, zero-shot): for a
   stratified sample of 8 families (1 per schema, seeded), the judge sees
   (task instruction, candidate memory) pairs of two types:
     A10 pair: task of family f + cross-domain SAME-PROGRAM memory (P=1)
     A01 pair: task of family f + its NEAR-MISS memory (P=0)
   and answers, under two paraphrased wordings, whether the two procedures
   require the same underlying program:
     wording A ("same"):     same sequence of operations up to irrelevant
                             surface details?  -> same iff yes
     wording B ("different"): require DIFFERENT underlying programs?
                             -> same iff no
   Agreement with the generator's structural labels is reported per wording
   and overall (target >= 0.85). If mismatches exceed 15% of the sampled
   16 pairs (32 judgements), every mismatched pair is dumped verbatim to
   pilot/audit/eq_disagreements.md.

2) Executable consistency recheck: re-run the oracle walker
   (pilot.program_dsl.run_oracle_plan) for every task instance
   (16 sibling + 4 near-miss per family) of the same 8 families against
   freshly rebuilt environments from the public task tables. Expected
   160/160 legal terminals (matches sealed/oracle_report.json).

Usage:
  CUDA_VISIBLE_DEVICES=9 python equivalence_audit.py            # full (judge)
  python equivalence_audit.py --oracle-only                     # no GPU part
"""

import argparse
import json
import os
import random

import numpy as np

import common as C

JUDGE_MODEL_KEY = "qwen7b"
SAMPLE_SEED = C.AUDIT_SEED + 41

WORDINGS = {
    "A_same": {
        "system": "You are a meticulous procedure auditor. You compare "
                  "procedures by their underlying operation sequence, "
                  "conditions and write targets, not by surface wording. "
                  "You answer with exactly one word: yes or no.",
        "user": ("TASK:\n{instruction}\n\n"
                 "CANDIDATE PROCEDURE (from a memory card):\n{memory}\n\n"
                 "Question: setting aside irrelevant surface details "
                 "(entity names, domain nouns, exact phrasing), do these "
                 "two procedures require the SAME sequence of operations -- "
                 "the same steps, in the same dependency order, with the "
                 "same decision conditions, comparison directions and "
                 "write targets?\n"
                 "Answer with exactly one word: yes or no."),
        "same_if": "yes",
    },
    "B_different": {
        "system": "You are a strict operations reviewer. You judge whether "
                  "two procedures are DIFFERENT programs at the structural "
                  "level: different steps, ordering, gating conditions, "
                  "comparison polarity or write targets. You answer with "
                  "exactly one word: yes or no.",
        "user": ("Here is a task an agent must perform:\n{instruction}\n\n"
                 "Here is a procedure described in a retrieved memory "
                 "card:\n{memory}\n\n"
                 "Ignoring mere surface variation (names, nouns, style): "
                 "do these two require DIFFERENT underlying programs -- "
                 "i.e., would following the memory card execute a "
                 "structurally different sequence of operations, checks or "
                 "writes than the task demands?\n"
                 "Answer with exactly one word: yes or no."),
        "same_if": "no",
    },
}


def sample_families():
    fams = C.load_families()
    by_schema = {}
    for fi, f in sorted(fams.items()):
        by_schema.setdefault(f["schema_key"], []).append(fi)
    rng = random.Random(SAMPLE_SEED)
    picks = {}
    for schema, fis in sorted(by_schema.items()):
        picks[schema] = rng.choice(sorted(fis))
    return picks


def build_pairs(picks):
    fams = C.load_families()
    cells = C.load_cells()
    mems = {m["memory_id"]: m for m in C.load_memories()}
    tasks = C.load_tasks_sealed()
    t_by_key = {(t["family_idx"], t["sibling_idx"], t["seed"]): t
                for t in tasks if t["kind"] == "sibling"}
    pairs = []
    sig_check = []
    for schema, fi in sorted(picks.items()):
        fam = fams[fi]
        partner = fams[fam["a10_partner"]]
        sig_check.append({
            "schema_key": schema, "family_idx": fi,
            "signature": fam["signature"],
            "a10_partner": fam["a10_partner"],
            "partner_signature": partner["signature"],
            "signatures_equal": fam["signature"] == partner["signature"],
            "nm_kind": fam["nm_kind"],
        })
        t = t_by_key[(fi, 0, 0)]
        crow = cells[(fi, 0)]
        for pair_type, cell, gen_label in (("A10", "A10", "same"),
                                           ("A01", "A01", "different")):
            m = mems[crow[cell]]
            pairs.append({
                "schema_key": schema, "family_idx": fi, "pair_type": pair_type,
                "cell": cell, "generator_label": gen_label,
                "memory_id": m["memory_id"], "task_id": t["task_id"],
                "instruction": t["instruction"], "memory_text": m["text"],
            })
    return pairs, sig_check


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------

def load_judge_llm(model_id):
    from vllm import LLM
    llm = LLM(model=model_id, gpu_memory_utilization=0.75, max_model_len=4096,
              seed=C.AUDIT_SEED)
    return llm, llm.get_tokenizer()


def run_judge(pairs, llm, tok):
    from vllm import SamplingParams
    sp = SamplingParams(temperature=0.0, max_tokens=1, logprobs=20)

    verdicts = []
    for wname, w in WORDINGS.items():
        prompts = []
        for p in pairs:
            msgs = [{"role": "system", "content": w["system"]},
                    {"role": "user", "content": w["user"].format(
                        instruction=p["instruction"], memory=p["memory_text"])}]
            prompts.append(tok.apply_chat_template(msgs, tokenize=False,
                                                   add_generation_prompt=True))
        outs = llm.generate(prompts, sp)
        for p, out in zip(pairs, outs):
            lp = out.outputs[0].logprobs[0]
            p_yes = p_no = 0.0
            for tid, lobj in lp.items():
                wword = tok.decode([tid]).strip().lower()
                if wword == "yes":
                    p_yes += float(np.exp(lobj.logprob))
                elif wword == "no":
                    p_no += float(np.exp(lobj.logprob))
            if p_yes + p_no <= 0:
                judged = "unparsed"
            else:
                yes = (p_yes / (p_yes + p_no)) >= 0.5
                judged = "same" if ((yes and w["same_if"] == "yes")
                                    or (not yes and w["same_if"] == "no")) \
                    else "different"
            agree = judged == p["generator_label"]
            verdicts.append({
                "wording": wname, "schema_key": p["schema_key"],
                "family_idx": p["family_idx"], "pair_type": p["pair_type"],
                "generator_label": p["generator_label"],
                "judged": judged, "agree": agree,
                "p_yes": (p_yes / (p_yes + p_no)) if (p_yes + p_no) > 0 else None,
            })
    return verdicts


COT_SYSTEM = ("You are a meticulous procedure auditor. You compare procedures "
              "by structure: step sets, dependency order, decision conditions, "
              "comparison direction, which child-set a gate counts, whether "
              "an archive/backup write precedes deletion, and write-target "
              "ROLES (not table names). Entity names, domain nouns and "
              "phrasing are irrelevant surface details.")
COT_USER = ("TASK:\n{instruction}\n\n"
            "CANDIDATE PROCEDURE (from a memory card):\n{memory}\n\n"
            "First give 'ANALYSIS:' 2-4 sentences: walk through the memory "
            "card's steps and check each structural element against the task "
            "(operations and their order, the gating condition including its "
            "polarity/direction and which items are counted, the presence or "
            "absence of required safety writes, and the write-target roles). "
            "State explicitly any element that differs structurally, or that "
            "all elements correspond up to surface details.\n"
            "Then finish with exactly one line: 'ANSWER: yes' if the two "
            "procedures are the same underlying program, or 'ANSWER: no' if "
            "they require different programs.")


def run_cot_judge(pairs, llm, tok):
    """Chain-of-thought annotator variant: forces the judge to enumerate the
    structural elements before answering. Returns verdicts + rationales."""
    from vllm import SamplingParams
    sp = SamplingParams(temperature=0.0, max_tokens=220)
    prompts = []
    for p in pairs:
        msgs = [{"role": "system", "content": COT_SYSTEM},
                {"role": "user", "content": COT_USER.format(
                    instruction=p["instruction"], memory=p["memory_text"])}]
        prompts.append(tok.apply_chat_template(msgs, tokenize=False,
                                               add_generation_prompt=True))
    outs = llm.generate(prompts, sp)
    verdicts = []
    for p, out in zip(pairs, outs):
        text = out.outputs[0].text
        judged = "unparsed"
        low = text.lower()
        if "answer: yes" in low:
            judged = "same"
        elif "answer: no" in low:
            judged = "different"
        verdicts.append({
            "wording": "C_cot", "schema_key": p["schema_key"],
            "family_idx": p["family_idx"], "pair_type": p["pair_type"],
            "generator_label": p["generator_label"], "judged": judged,
            "agree": judged == p["generator_label"],
            "rationale": text.strip()})
    return verdicts


def agreement_block(verdicts):
    out = {}
    for wname in WORDINGS:
        vs = [v for v in verdicts if v["wording"] == wname]
        per_type = {}
        for pt in ("A10", "A01"):
            vt = [v for v in vs if v["pair_type"] == pt]
            per_type[pt] = float(np.mean([v["agree"] for v in vt]))
        out[wname] = {"agreement": float(np.mean([v["agree"] for v in vs])),
                      "n": len(vs), "per_pair_type": per_type,
                      "n_unparsed": sum(1 for v in vs if v["judged"] == "unparsed")}
    out["overall"] = {"agreement": float(np.mean([v["agree"] for v in verdicts])),
                      "n": len(verdicts)}
    return out


def write_disagreements(pairs, verdicts, path):
    bad = [v for v in verdicts if not v["agree"]]
    by_pair = {}
    for p in pairs:
        by_pair[(p["family_idx"], p["pair_type"])] = p
    lines = ["# Equivalence-audit judge/generator disagreements",
             "",
             "Every sampled (task, memory) pair on which the independent "
             "Qwen2.5-7B judge (either wording) disagreed with the "
             "generator's structural P label. Text verbatim.",
             ""]
    for v in bad:
        p = by_pair[(v["family_idx"], v["pair_type"])]
        lines += [
            "---",
            "## family %d (%s) pair %s | wording %s | generator=%s judged=%s"
            % (p["family_idx"], p["schema_key"], p["pair_type"], v["wording"],
               v["generator_label"], v["judged"]),
            "",
            "### task instruction",
            "```",
            p["instruction"],
            "```",
            "### memory card (%s, %s)" % (p["cell"], p["memory_id"]),
            "```",
            p["memory_text"],
            "```",
        ]
        if v.get("rationale"):
            lines += ["### judge rationale (CoT variant)", "```",
                      v["rationale"], "```"]
        lines += [""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return len(bad)


# ---------------------------------------------------------------------------
# oracle recheck
# ---------------------------------------------------------------------------

def oracle_recheck(picks):
    from program_dsl import ARCHETYPES, run_oracle_plan
    from env_relationalops import RelationalOpsEnv
    fams = C.load_families()
    tasks = C.load_tasks_sealed()
    keep = set(picks.values())
    results = []
    n_ok = 0
    for t in tasks:
        if t["family_idx"] not in keep:
            continue
        pub = C.load_public_task(t["task_id"])
        env = RelationalOpsEnv(pub["tables"], t["terminal"])
        prog = ARCHETYPES[fams[t["family_idx"]]["archetype"]](
            t["program_params"])
        ok, detail = run_oracle_plan(env, prog, t["oracle_plan"])
        n_ok += int(ok)
        results.append({"family_idx": t["family_idx"], "kind": t["kind"],
                        "sibling_idx": t["sibling_idx"], "seed": t["seed"],
                        "task_id": t["task_id"], "ok": bool(ok),
                        "error": None if ok else detail.get("error")})
    return {"n_checked": len(results), "n_ok": n_ok,
            "pass": n_ok == len(results), "failures":
            [r for r in results if not r["ok"]], "rows": results}


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "..", "configs",
                                                     "pilot.yaml"))
    ap.add_argument("--oracle-only", action="store_true")
    ap.add_argument("--gpu-note", default=None)
    args = ap.parse_args()

    from generate_families import load_config
    cfg = load_config(args.config)
    model_id = cfg["models"][JUDGE_MODEL_KEY]

    picks = sample_families()
    print("[eq] sampled families (1 per schema): %s" % picks)
    pairs, sig_check = build_pairs(picks)
    n_sig_equal = sum(1 for s in sig_check if s["signatures_equal"])
    print("[eq] signature equality (family vs a10 partner): %d/%d equal"
          % (n_sig_equal, len(sig_check)))
    for s in sig_check:
        print("[eq]   fam %2d (%-18s) sig=%r | partner fam %2d sig=%r equal=%s"
              % (s["family_idx"], s["schema_key"], s["signature"],
                 s["a10_partner"], s["partner_signature"],
                 s["signatures_equal"]))

    print("[eq] --- A10 pairs (task instruction, cross-domain memory) ---")
    for p in pairs:
        if p["pair_type"] != "A10":
            continue
        print("[eq] fam %d (%s) partner-domain card %s" % (
            p["family_idx"], p["schema_key"], p["memory_id"]))
        print("[eq]   TASK: %s" % p["instruction"][:400])
        print("[eq]   MEM : %s" % p["memory_text"][:400].replace("\n", " | "))

    result = {"env": C.env_block({"judge_model": model_id,
                                  "sample_seed": SAMPLE_SEED}),
              "sampled_families": picks, "signature_check": sig_check,
              "n_pairs": len(pairs), "wordings": {k: v["user"] for k, v in
                                                  WORDINGS.items()}}

    # oracle recheck (CPU, always)
    print("[eq] oracle recheck on the 8 sampled families ...")
    orec = oracle_recheck(picks)
    result["oracle_recheck"] = {k: v for k, v in orec.items() if k != "rows"}
    print("[eq] oracle recheck: %d/%d plans reach a legal terminal "
          "(pass=%s)" % (orec["n_ok"], orec["n_checked"], orec["pass"]))
    for fail in orec["failures"][:5]:
        print("[eq]   FAILURE: %s" % fail)

    if not args.oracle_only:
        print("[eq] running independent judge (%s) ..." % model_id)
        llm, tok = load_judge_llm(model_id)
        verdicts = run_judge(pairs, llm, tok)
        agree = agreement_block(verdicts)
        print("[eq] running CoT annotator variant ...")
        cot_verdicts = run_cot_judge(pairs, llm, tok)
        cot_agree = {}
        for pt in ("A10", "A01"):
            vt = [v for v in cot_verdicts if v["pair_type"] == pt]
            cot_agree[pt] = float(np.mean([v["agree"] for v in vt]))
        cot_overall = float(np.mean([v["agree"] for v in cot_verdicts]))
        cot_blk = {"agreement": cot_overall, "n": len(cot_verdicts),
                   "per_pair_type": cot_agree,
                   "n_unparsed": sum(1 for v in cot_verdicts
                                     if v["judged"] == "unparsed")}
        agree["C_cot"] = cot_blk
        result["judge"] = {"verdicts": verdicts, "cot_verdicts": cot_verdicts,
                           "agreement": agree}
        for wname in ("A_same", "B_different", "C_cot"):
            blk = agree[wname]
            print("[eq] wording %s agreement=%.3f (A10 %.3f, A01 %.3f, "
                  "unparsed %d)" % (wname, blk["agreement"],
                                    blk["per_pair_type"]["A10"],
                                    blk["per_pair_type"]["A01"],
                                    blk["n_unparsed"]))
        print("[eq] overall agreement one-shot wordings=%.3f over %d "
              "judgements" % (agree["overall"]["agreement"],
                              agree["overall"]["n"]))
        mismatch_frac = 1 - agree["overall"]["agreement"]
        result["judge"]["mismatch_fraction"] = mismatch_frac
        result["judge"]["target"] = 0.85
        result["judge"]["target_met"] = agree["overall"]["agreement"] >= 0.85
        if mismatch_frac > 0.15:
            path = os.path.join(C.AUDIT_DIR, "eq_disagreements.md")
            n_bad = write_disagreements(pairs, verdicts + cot_verdicts, path)
            result["judge"]["disagreements_file"] = path
            print("[eq] %.1f%% mismatch > 15%%: %d verdicts written to %s"
                  % (mismatch_frac * 100, n_bad, path))

    C.write_result("equivalence.json", result)


if __name__ == "__main__":
    main()
