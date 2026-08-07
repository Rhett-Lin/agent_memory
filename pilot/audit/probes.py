"""Gate B audit 1/4: strong memory-text leakage probes.

Adversarial question: can the P label (program match) be read off a candidate
memory ALONE, from public text? If yes, the pilot's P-contrasts (tau_struct,
tau_trap, tau_PxS) could be surface-text artifacts instead of causal effects
of program equivalence.

Probes:
  (a) char 3-5-gram TF-IDF + logistic regression   (AUC + Brier)
  (b) length / token-count / style-template features + logistic
  (c) frozen bge-small-en-v1.5 embedding + logistic
  (d) zero-shot LLM probe (Qwen2.5-1.5B-Instruct, vllm): given (task
      instruction, memory), "does this memory describe exactly the same
      procedure the task needs?" -- AUC separating correct-program from
      near-miss / cross-domain memories from public text alone.

Evaluation:
  * family-held-out: train on 30 families, test on 10 (seeded split).
  * archetype-held-out: 8 schemas, leave-2-out (all 28 folds) -- tests
    generalisation to unseen program schemas.
  * AUC 95% CI: family-cluster bootstrap over the test families.
  * Brier score (calibration) reported for probe (a), family split.

Three prediction tasks for probes (a)-(c):
  P_all : {A00,A01} vs {A10,A11}   (640 cards)
  P_S1  : A01 vs A11               (the tau_trap / harmful-flip plane)
  P_S0  : A00 vs A10               (the tau_struct plane)
plus 40-way family_idx classification with probe (a) as a leakage reference.

Probe (d) runs the S1 subset (per spec) and additionally the S0 subset so we
can quantify how much of tau_struct an LLM-probe-only admission gate could
already capture: with admission probability p(cell) = judge says "same
procedure", a gated agent scores
    E[cell] = p(cell)*rate(cell) + (1-p(cell))*rate(N),
and the gate-induced contrast E[A1x]-E[A0x] is compared to the raw one.

Usage:
  python probes.py            # surface probes (CPU)
  CUDA_VISIBLE_DEVICES=8 python probes.py --llm   # adds the LLM probe
"""

import argparse
import json
import os

import numpy as np

import common as C

SCHEMAS_ORDER = None  # filled from families


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def load_probe_frame():
    fams = C.load_families()
    mems = [m for m in C.load_memories() if m["P"] is not None]
    rows = []
    for m in mems:
        fam = fams[m["family_idx"]]
        rows.append({
            "memory_id": m["memory_id"], "text": m["text"],
            "family_idx": m["family_idx"], "target_sibling": m["target_sibling"],
            "cell": m["cell"], "P": int(m["P"]), "S": int(m["S"]),
            "schema_key": fam["schema_key"], "archetype": fam["archetype"],
            "style_name": m["style_name"], "token_count": m["token_count"],
        })
    return rows


def family_split(rows, n_test=10, seed=C.AUDIT_SEED):
    fams = sorted({r["family_idx"] for r in rows})
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(fams))
    test_fams = {fams[i] for i in perm[:n_test]}
    tr = [r for r in rows if r["family_idx"] not in test_fams]
    te = [r for r in rows if r["family_idx"] in test_fams]
    return tr, te, sorted(test_fams)


def auc_with_ci(test_rows, y, score, seed):
    units = [{"family_idx": r["family_idx"], "y": yy, "s": ss}
             for r, yy, ss in zip(test_rows, y, score)]

    def stat(sub):
        return C.auc_scores([u["y"] for u in sub], [u["s"] for u in sub])

    p, lo, hi, _ = C.family_cluster_bootstrap(units, stat, seed=seed)
    return {"auc": p, "ci": [lo, hi], "n_test": len(units),
            "n_pos": int(sum(u["y"] for u in units)),
            "n_test_families": len({u["family_idx"] for u in units})}


# ---------------------------------------------------------------------------
# probe feature extractors / model builders
# ---------------------------------------------------------------------------

def build_probe_a():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                  min_df=2, sublinear_tf=True)),
        ("lr", LogisticRegression(max_iter=2000, C=1.0)),
    ])


STYLE_NAMES = ["formal_sop", "runbook_bullets", "postmortem", "terse_note",
               "training_qa", "checklist"]


def style_features(rows):
    X = []
    for r in rows:
        t = r["text"]
        words = t.split()
        n_ch = max(1, len(t))
        lines = t.split("\n")
        X.append([
            r["token_count"], len(t), len(words), len(lines),
            sum(ch.isdigit() for ch in t) / n_ch,
            sum(ch.isupper() for ch in t) / n_ch,
            float(np.mean([len(w) for w in words])) if words else 0.0,
            t.count(".") / max(1, len(words)),
            sum(1 for ln in lines if ln.strip().startswith("Note:")),
            t.count(";"), t.count(":"), t.count("*"),
        ] + [1.0 if r["style_name"] == s else 0.0 for s in STYLE_NAMES])
    return np.asarray(X, float)


def build_probe_b():
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    return Pipeline([
        ("sc", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000, C=1.0)),
    ])


def build_probe_c():
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    return Pipeline([
        ("sc", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000, C=1.0)),
    ])


def fit_probe(kind, rows_train, rows_eval, embedding_lookup=None):
    """Returns (scores_on_eval, fitted_model). kind in {'a','b','c'}.
    embedding_lookup: memory_id -> vector (precomputed once for probe c)."""
    if kind == "a":
        model = build_probe_a()
        model.fit([r["text"] for r in rows_train],
                  [r["P"] for r in rows_train])
        return model.predict_proba([r["text"] for r in rows_eval])[:, 1], model
    if kind == "b":
        model = build_probe_b()
        model.fit(style_features(rows_train), [r["P"] for r in rows_train])
        return model.predict_proba(style_features(rows_eval))[:, 1], model
    if kind == "c":
        assert embedding_lookup is not None
        model = build_probe_c()
        Xtr = np.stack([embedding_lookup[r["memory_id"]] for r in rows_train])
        model.fit(Xtr, [r["P"] for r in rows_train])
        Xte = np.stack([embedding_lookup[r["memory_id"]] for r in rows_eval])
        return model.predict_proba(Xte)[:, 1], model
    raise ValueError(kind)


# ---------------------------------------------------------------------------
# surface-probe evaluation driver
# ---------------------------------------------------------------------------

def eval_task_subset(rows_subset, kind, embedding_lookup=None, seed=C.AUDIT_SEED):
    """Family-held-out + archetype-held-out AUCs for one label subset."""
    out = {}
    tr, te, test_fams = family_split(rows_subset, seed=seed)
    score, model = fit_probe(kind, tr, te, embedding_lookup=embedding_lookup)
    y = [r["P"] for r in te]
    res = auc_with_ci(te, y, score, seed + 1)
    out["family_holdout"] = res
    out["family_holdout"]["test_families"] = test_fams
    if kind == "a":
        prob = np.clip(score, 1e-7, 1 - 1e-7)
        out["family_holdout"]["brier"] = float(
            np.mean((prob - np.asarray(y, float)) ** 2))

    # archetype (schema) held-out: leave-2-of-8-schemas-out, all 28 folds
    schemas = sorted({r["schema_key"] for r in rows_subset})
    fold_aucs, folds = [], []
    for i in range(len(schemas)):
        for j in range(i + 1, len(schemas)):
            held = {schemas[i], schemas[j]}
            tr2 = [r for r in rows_subset if r["schema_key"] not in held]
            te2 = [r for r in rows_subset if r["schema_key"] in held]
            if len({r["P"] for r in te2}) < 2 or len({r["P"] for r in tr2}) < 2:
                continue
            try:
                sc2, _ = fit_probe(kind, tr2, te2,
                                   embedding_lookup=embedding_lookup)
            except Exception as e:  # e.g. degenerate fold
                folds.append({"held_out": sorted(held), "error": str(e)})
                continue
            a = C.auc_scores([r["P"] for r in te2], sc2)
            fold_aucs.append(a)
            folds.append({"held_out": sorted(held), "auc": a})
    if fold_aucs:
        out["archetype_holdout"] = {
            "mean_auc": float(np.mean(fold_aucs)),
            "fold_q": [float(np.quantile(fold_aucs, 0.025)),
                       float(np.quantile(fold_aucs, 0.975))],
            "n_folds": len(fold_aucs), "folds": folds,
        }
    return out, te, y, score, model


def family_idx_probe(rows, seed=C.AUDIT_SEED):
    """40-way family classification with probe (a).

    NOTE: family-held-out evaluation is vacuous for ID prediction (an unseen
    family can never be predicted), so we use a seeded CARD-level split
    (train/test both see all 40 families) to ask whether cards carry
    family-specific surface fingerprints at all. Expected to be high for
    A11/A01 (same-family cards share the task's entity names by construction)
    -- entities are instance parameters, not part of the program class."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(rows))
    n_te = len(rows) // 4
    te = [rows[i] for i in idx[:n_te]]
    tr = [rows[i] for i in idx[n_te:]]
    model = build_probe_a()
    model.fit([r["text"] for r in tr], [r["family_idx"] for r in tr])
    pred = model.predict([r["text"] for r in te])
    y = np.asarray([r["family_idx"] for r in te])
    # per-cell accuracy: which cells leak family identity
    per_cell = {}
    for cell in sorted({r["cell"] for r in te}):
        m = np.asarray([r["cell"] == cell for r in te])
        per_cell[cell] = float((pred[m] == y[m]).mean()) if m.sum() else None
    acc = float((pred == y).mean())
    return {"accuracy": acc, "per_cell_accuracy": per_cell,
            "chance": 1.0 / 40, "n_test": len(te),
            "split": "card-level 75/25 seeded split (family-held-out is "
                     "vacuous for ID prediction)"}


# ---------------------------------------------------------------------------
# (d) LLM probe
# ---------------------------------------------------------------------------

LLM_PROMPT_TMPL = """A data-operations agent working in a relational database is given this task:

=== TASK ===
{instruction}
=== END TASK ===

It has retrieved the following memory card from a past episode:

=== MEMORY CARD ===
{memory}
=== END MEMORY CARD ===

Question: does this memory card describe exactly the same procedure the task requires -- the same operations, in the same order, with the same decision condition, the same comparison direction, and the same write targets -- where only surface details (entity names, domain nouns, exact wording) may differ?
Answer with exactly one word: yes or no."""

LLM_SYSTEM = ("You are a meticulous procedure auditor. You compare procedures "
              "by their underlying operation sequence, not by wording. You "
              "answer with exactly one word: yes or no.")


def run_llm_probe(cfg_model_id, gpu_util=0.4, max_pairs=None):
    """Zero-shot yes/no judge on (task, memory) pairs from the S1 and S0
    subsets. Score = renormalised P(yes) from first-token logprobs."""
    from vllm import LLM, SamplingParams

    fams = C.load_families()
    tasks = C.load_tasks_sealed()
    t_by_key = {(t["family_idx"], t["sibling_idx"], t["seed"]): t
                for t in tasks if t["kind"] == "sibling"}
    mems = [m for m in C.load_memories() if m["cell"] in C.A_CELLS]
    pairs = []
    for m in mems:
        t = t_by_key.get((m["family_idx"], m["target_sibling"], 0))
        if t is None:
            continue
        pairs.append({
            "family_idx": m["family_idx"], "sibling": m["target_sibling"],
            "cell": m["cell"], "P": int(m["P"]), "S": int(m["S"]),
            "memory_id": m["memory_id"],
            "instruction": t["instruction"], "memory": m["text"],
        })
    if max_pairs:
        pairs = pairs[:max_pairs]

    llm = LLM(model=cfg_model_id, gpu_memory_utilization=gpu_util,
              max_model_len=4096, seed=C.AUDIT_SEED, enforce_eager=False)
    tok = llm.get_tokenizer()
    prompts = []
    for p in pairs:
        msgs = [{"role": "system", "content": LLM_SYSTEM},
                {"role": "user", "content": LLM_PROMPT_TMPL.format(
                    instruction=p["instruction"], memory=p["memory"])}]
        prompts.append(tok.apply_chat_template(msgs, tokenize=False,
                                               add_generation_prompt=True))
    sp = SamplingParams(temperature=0.0, max_tokens=1, logprobs=20)
    outs = llm.generate(prompts, sp)

    def yes_no_score(out):
        lp = out.outputs[0].logprobs[0]  # first generated position
        p_yes = p_no = 0.0
        for tid, lobj in lp.items():
            w = tok.decode([tid]).strip().lower()
            if w == "yes":
                p_yes += float(np.exp(lobj.logprob))
            elif w == "no":
                p_no += float(np.exp(lobj.logprob))
        if p_yes + p_no <= 0:
            return None, out.outputs[0].text
        return p_yes / (p_yes + p_no), out.outputs[0].text

    scored, n_unparsed = [], 0
    for p, out in zip(pairs, outs):
        s, raw = yes_no_score(out)
        if s is None:
            n_unparsed += 1
            continue
        scored.append({**{k: p[k] for k in ("family_idx", "sibling", "cell",
                                            "P", "S", "memory_id")},
                       "p_yes": s, "verdict_yes": bool(s >= 0.5), "raw": raw})

    res = {"model": cfg_model_id, "n_pairs": len(pairs),
           "n_unparsed": n_unparsed, "subsets": {}, "pairs": scored}
    for subset, cells, pos in [("S1_P1_vs_P0", ("A11", "A01"), "A11"),
                               ("S0_P1_vs_P0", ("A10", "A00"), "A10")]:
        rows_ = [s for s in scored if s["cell"] in cells]
        units = [{"family_idx": r["family_idx"], "y": 1 if r["cell"] == pos else 0,
                  "s": r["p_yes"]} for r in rows_]

        def stat(sub):
            return C.auc_scores([u["y"] for u in sub], [u["s"] for u in sub])

        pt, lo, hi, _ = C.family_cluster_bootstrap(units, stat,
                                                   seed=C.AUDIT_SEED + 11)
        admit = {c: float(np.mean([r["verdict_yes"] for r in rows_
                                   if r["cell"] == c])) for c in cells}
        res["subsets"][subset] = {"auc": pt, "ci": [lo, hi], "n": len(rows_),
                                  "positive_cell": pos,
                                  "admit_rate": admit}
    return res


def gate_capture(llm_res, rollout_rows):
    """How much of the P-contrasts could an LLM-probe-only admission gate
    already capture (both models)?"""
    out = {}
    for model in ("qwen3b", "qwen7b"):
        mr = [r for r in rollout_rows if r["model"] == model]
        rates = {c: C.rate([r for r in mr if r["cell"] == c])
                 for c in C.ALL_CELLS}
        m = {}
        for subset, cpos, cneg, raw_name in [
                ("S1_P1_vs_P0", "A11", "A01", "P_gap_at_S1 (A11-A01)"),
                ("S0_P1_vs_P0", "A10", "A00", "tau_struct (A10-A00)")]:
            ss = llm_res["subsets"][subset]
            p_pos, p_neg = ss["admit_rate"][cpos], ss["admit_rate"][cneg]
            e_pos = p_pos * rates[cpos] + (1 - p_pos) * rates["N"]
            e_neg = p_neg * rates[cneg] + (1 - p_neg) * rates["N"]
            raw = rates[cpos] - rates[cneg]
            gated = e_pos - e_neg
            m[subset] = {
                "raw_contrast": raw_name, "raw_gap": raw,
                "gated_gap": gated,
                "gate_captured_fraction": (gated / raw) if raw else float("nan"),
                "admit_rate_pos": p_pos, "admit_rate_neg": p_neg,
            }
        out[model] = m
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "..", "configs",
                                                     "pilot.yaml"))
    ap.add_argument("--llm", action="store_true",
                    help="also run the vllm LLM probe (needs a GPU)")
    ap.add_argument("--llm-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--gpu-util", type=float, default=0.4)
    ap.add_argument("--max-pairs", type=int, default=None)
    args = ap.parse_args()

    from generate_families import load_config
    cfg = load_config(args.config)
    model_id = cfg["models"].get(args.llm_model, args.llm_model)

    rows = load_probe_frame()
    print("[probes] %d labelled cards (P in {0,1}) over %d families"
          % (len(rows), len({r["family_idx"] for r in rows})))

    result_path = os.path.join(C.RESULTS_DIR, "probes.json")
    if os.path.exists(result_path):
        with open(result_path) as f:
            result = json.load(f)
    else:
        result = {"env": C.env_block(), "surface_probes": {}, "notes": {
            "P_tasks": {"P_all": "A00/A01 vs A10/A11",
                        "P_S1": "A01 vs A11 (tau_trap plane)",
                        "P_S0": "A00 vs A10 (tau_struct plane)"},
            "evaluation": "family-held-out 30/10 + leave-2-schemas-out; "
                          "AUC CI = family-cluster bootstrap on test set"}}

    embedder = None
    embedding_lookup = None

    def get_embedding_lookup():
        nonlocal embedder, embedding_lookup
        if embedding_lookup is None:
            from sentence_transformers import SentenceTransformer
            print("[probes] loading bge-small-en-v1.5 (cpu); encoding %d "
                  "cards once ..." % len(rows))
            embedder = SentenceTransformer("BAAI/bge-small-en-v1.5",
                                           device="cpu")
            vecs = embedder.encode([r["text"] for r in rows], batch_size=64,
                                   normalize_embeddings=True,
                                   show_progress_bar=False)
            embedding_lookup = {r["memory_id"]: v
                                for r, v in zip(rows, vecs)}
        return embedding_lookup

    subsets = {
        "P_all": rows,
        "P_S1": [r for r in rows if r["cell"] in ("A01", "A11")],
        "P_S0": [r for r in rows if r["cell"] in ("A00", "A10")],
    }

    for kind in ("a", "b", "c"):
        print("[probes] === probe (%s) ===" % kind)
        emb = get_embedding_lookup() if kind == "c" else None
        for sname, srows in subsets.items():
            res, te, y, score, _ = eval_task_subset(srows, kind,
                                                    embedding_lookup=emb)
            result["surface_probes"].setdefault(kind, {})[sname] = res
            fh = res["family_holdout"]
            print("[probes] (%s) %-6s family-holdout AUC=%.3f [%0.3f,%0.3f]%s"
                  % (kind, sname, fh["auc"], fh["ci"][0], fh["ci"][1],
                     ("  brier=%.4f" % fh["brier"]) if "brier" in fh else ""))
            if "archetype_holdout" in res:
                ah = res["archetype_holdout"]
                print("[probes] (%s) %-6s archetype-holdout meanAUC=%.3f "
                      "fold-q [%.3f,%.3f] over %d folds"
                      % (kind, sname, ah["mean_auc"], ah["fold_q"][0],
                         ah["fold_q"][1], ah["n_folds"]))
        if kind == "a":
            famres = family_idx_probe(rows)
            result["surface_probes"][kind]["family_idx_40way"] = famres
            print("[probes] (a) family_idx 40-way acc=%.3f (chance %.3f) "
                  "per-cell=%s" % (famres["accuracy"], famres["chance"],
                                   {k: (round(v, 3) if v is not None else None)
                                    for k, v in
                                    famres["per_cell_accuracy"].items()}))

    if args.llm:
        print("[probes] === probe (d) LLM zero-shot judge, model=%s ==="
              % model_id)
        llm_res = run_llm_probe(model_id, gpu_util=args.gpu_util,
                                max_pairs=args.max_pairs)
        rollout_rows, _ = C.load_rollout_rows()
        llm_res["gate_capture"] = gate_capture(llm_res, rollout_rows)
        result["llm_probe"] = llm_res
        for sname, ss in llm_res["subsets"].items():
            print("[probes] (d) %-14s AUC=%.3f [%.3f,%.3f] n=%d admit=%s"
                  % (sname, ss["auc"], ss["ci"][0], ss["ci"][1], ss["n"],
                     {k: round(v, 3) for k, v in ss["admit_rate"].items()}))
        for model, m in llm_res["gate_capture"].items():
            for sname, g in m.items():
                print("[probes] (d) gate-capture %s %s: raw=%.3f gated=%.3f "
                      "frac=%.2f" % (model, sname, g["raw_gap"],
                                     g["gated_gap"],
                                     g["gate_captured_fraction"]))

    result["env"] = C.env_block({"llm_model": model_id})
    C.write_result("probes.json", result)


if __name__ == "__main__":
    main()
