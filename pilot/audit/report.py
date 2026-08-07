"""Gate B audit: aggregate results -> AUDIT_RESULTS.json + markdown summary.

Reads pilot/audit/results/{probes,difficulty_robust,continuous_s,
equivalence}.json (run the four scripts first) and writes
pilot/audit/AUDIT_RESULTS.json, printing a markdown table summary to stdout.

Usage:  python report.py
"""

import datetime
import json
import os

import common as C

RESULTS = C.RESULTS_DIR
OUT_JSON = os.path.join(C.AUDIT_DIR, "AUDIT_RESULTS.json")


def load(name):
    path = os.path.join(RESULTS, name)
    if not os.path.exists(path):
        print("[report] WARNING: missing %s" % path)
        return None
    with open(path) as f:
        return json.load(f)


def fmt_ci(blk, key="auc"):
    return "%.3f [%.3f, %.3f]" % (blk[key], blk["ci"][0], blk["ci"][1])


def main():
    probes = load("probes.json")
    diff = load("difficulty_robust.json")
    cont = load("continuous_s.json")
    equiv = load("equivalence.json")

    out = {"generated": datetime.datetime.utcnow().strftime(
               "%Y-%m-%d %H:%M:%S UTC"),
           "env": C.env_block({"hf_home": os.environ.get("HF_HOME")}),
           "audit_seed": C.AUDIT_SEED,
           "sections": {}}
    md = []
    md.append("# Gate B causal-validity audit -- mini-pilot")
    md.append("")

    # ---------------------------------------------------------------- probes
    if probes:
        sp = probes.get("surface_probes", {})
        md.append("## 1. Leakage probes (predict P from memory text alone)")
        md.append("")
        md.append("Family-held-out (train 30 fam / test 10 fam) AUC "
                  "[family-cluster bootstrap 95% CI]; archetype-held-out = "
                  "leave-2-of-8-schemas-out mean AUC over 28 folds.")
        md.append("")
        md.append("| probe | P_S0 = A00 vs A10 (tau_struct plane) | "
                  "P_S1 = A01 vs A11 (trap plane) | P_all |")
        md.append("|---|---|---|---|")
        names = {"a": "(a) char 3-5g TF-IDF + LR",
                 "b": "(b) length/style features + LR",
                 "c": "(c) bge-small emb + LR"}
        for kind in ("a", "b", "c"):
            blk = sp.get(kind, {})
            row = [names[kind]]
            for subset in ("P_S0", "P_S1", "P_all"):
                fh = blk.get(subset, {}).get("family_holdout")
                if fh:
                    ah = blk[subset].get("archetype_holdout")
                    cell = fmt_ci(fh)
                    if ah:
                        cell += "<br>arch: %.3f" % ah["mean_auc"]
                    row.append(cell)
                else:
                    row.append("--")
            md.append("| " + " | ".join(row) + " |")
        fa = sp.get("a", {}).get("P_all", {}).get("family_holdout", {})
        if "brier" in fa:
            md.append("")
            md.append("Probe (a) Brier (P_all, family holdout): **%.4f**"
                      % fa["brier"])
        fidx = sp.get("a", {}).get("family_idx_40way")
        if fidx:
            md.append("family_idx 40-way probe: acc=%.3f (chance %.3f), "
                      "per-cell %s" % (fidx["accuracy"], fidx["chance"],
                                       {k: (round(v, 3) if v is not None else None)
                                        for k, v in
                                        fidx["per_cell_accuracy"].items()}))
        lp = probes.get("llm_probe")
        if lp:
            md.append("")
            md.append("### (d) zero-shot LLM probe (%s)" % lp["model"])
            md.append("")
            md.append("| subset | AUC (soft p_yes) | admit(pos) | admit(neg) |")
            md.append("|---|---|---|---|")
            for sname, ss in lp["subsets"].items():
                admit = ss["admit_rate"]
                md.append("| %s | %s | %.3f | %.3f |" % (
                    sname, fmt_ci(ss),
                    admit.get(ss["positive_cell"], float("nan")),
                    admit[[k for k in admit if k != ss["positive_cell"]][0]]))
            md.append("")
            md.append("LLM-probe-only admission gate (hard verdict; fallback "
                      "= no memory): fraction of the raw P-contrast it would "
                      "already capture:")
            md.append("")
            md.append("| model | subset | raw gap | gated gap | captured |")
            md.append("|---|---|---|---|---|")
            for model, m in lp.get("gate_capture", {}).items():
                for sname, g in m.items():
                    md.append("| %s | %s (%s) | %+.3f | %+.3f | %.2f |" % (
                        model, sname, g["raw_contrast"], g["raw_gap"],
                        g["gated_gap"], g["gate_captured_fraction"]))
            md.append("")
            md.append("Verdict note: the 1.5B judge's hard verdict admits "
                      "everything at S=1 (admit=1.0 for both cells) -- its "
                      "S=1 AUC lives entirely in soft probabilities.")
        out["sections"]["probes"] = probes

    # ------------------------------------------------------- difficulty robust
    if diff:
        md.append("")
        md.append("## 2. Difficulty-robustness attack on tau_struct")
        md.append("")
        d7 = diff["models"]["qwen7b"]
        bt = d7["baseline_tost"]
        md.append("7B baseline TOST (+/-7pp): mean=%.3f CI=[%.3f, %.3f] "
                  "-> **fails** (known Gate-A caveat)." % (
                      bt["mean_pair_diff"], bt["ci"][0], bt["ci"][1]))
        tr = d7.get("trimming_attack")
        if tr:
            md.append("")
            md.append("**(i) trimming**: dropped %d worst sibling pairs "
                      "(%d/%d sibling units removed) until TOST passes; "
                      "final TOST mean=%.3f CI=[%.3f, %.3f]." % (
                          tr["n_pairs_dropped"], tr["n_units_dropped"],
                          tr["total_units"],
                          tr["final_tost"]["mean_pair_diff"],
                          tr["final_tost"]["ci"][0], tr["final_tost"]["ci"][1]))
            tt = tr["taus_trimmed"]
            md.append("")
            md.append("| 7B trimmed | point | 95% CI | SIG |")
            md.append("|---|---|---|---|")
            for k in ("tau_struct", "tau_trap", "replay_premium", "tau_PxS"):
                b = tt[k]
                md.append("| %s | %+.3f | [%+.3f, %+.3f] | %s |" % (
                    k, b["point"], b["ci"][0], b["ci"][1], b["sig"]))
        md.append("")
        md.append("**(ii) per-family demeaning** (both models): %s" %
                  d7["demeaned"]["identity_note"])
        for model in ("qwen7b", "qwen3b"):
            dm = diff["models"][model]["demeaned"]
            st = dm["difficulty_stratified_tau_struct"]
            md.append("")
            md.append("- %s identity max|diff|=%.1e; stratified tau_struct: "
                      "hard %.3f [%+.3f,%+.3f] vs easy %.3f [%+.3f,%+.3f]" % (
                          model, dm["identity_max_abs_diff"],
                          st["hard_half"]["point"], st["hard_half"]["ci"][0],
                          st["hard_half"]["ci"][1],
                          st["easy_half"]["point"], st["easy_half"]["ci"][0],
                          st["easy_half"]["ci"][1]))
        md.append("")
        md.append("**(iii) per-schema tau_struct** (5 families each):")
        md.append("")
        md.append("| schema | archetype | 7B tau_struct | 3B tau_struct |")
        md.append("|---|---|---|---|")
        for schema in sorted(diff["models"]["qwen7b"]["per_archetype"]):
            b7 = diff["models"]["qwen7b"]["per_archetype"][schema]
            b3 = diff["models"]["qwen3b"]["per_archetype"][schema]
            md.append("| %s | %s | %+.3f [%+.3f,%+.3f] | %+.3f [%+.3f,%+.3f] |"
                      % (schema, b7["archetype"],
                         b7["tau_struct"]["point"], b7["tau_struct"]["ci"][0],
                         b7["tau_struct"]["ci"][1],
                         b3["tau_struct"]["point"], b3["tau_struct"]["ci"][0],
                         b3["tau_struct"]["ci"][1]))
        out["sections"]["difficulty_robust"] = diff

    # ----------------------------------------------------------- continuous S
    if cont:
        md.append("")
        md.append("## 3. Continuous-S sensitivity (per-unit uplift vs N)")
        md.append("")
        md.append("| model | stratum | slope(sim_tf) | slope(sim_embed) |")
        md.append("|---|---|---|---|")
        for model in ("qwen7b", "qwen3b"):
            regs = cont["strata"][model]["regressions"]
            for sname in ("P1 (A11+A10)", "S1 (A11+A01)", "S0 (A10+A00)"):
                a = regs[sname]["sim_tf"]
                b = regs[sname]["sim_embed"]
                md.append("| %s | %s | %+.3f [%+.3f,%+.3f]%s | "
                          "%+.3f [%+.3f,%+.3f]%s |" % (
                              model, sname.replace("|", "\\|"),
                              a["slope"], a["slope_ci"][0], a["slope_ci"][1],
                              "*" if a["slope_sig"] else "",
                              b["slope"], b["slope_ci"][0], b["slope_ci"][1],
                              "*" if b["slope_sig"] else ""))
        md.append("")
        md.append("\\* slope CI excludes 0. Overlap-band P-contrasts at "
                  "matched continuous S:")
        md.append("")
        md.append("| model | band | uplift diff (P1 - P0) in band |")
        md.append("|---|---|---|")
        for model in ("qwen7b", "qwen3b"):
            bands = cont["strata"][model]["overlap_band_contrasts"]
            for tag, b in bands.items():
                if b.get("overlap_band"):
                    md.append("| %s | %s [%0.3f,%0.3f] n=%d | %+.3f "
                              "[%+.3f,%+.3f]%s |" % (
                                  model, tag.replace("|", "\\|"),
                                  b["overlap_band"][0], b["overlap_band"][1],
                                  b["n_in_band"], b["uplift_diff_in_band"],
                                  b["ci"][0], b["ci"][1],
                                  " *SIG*" if b["sig"] else ""))
                else:
                    md.append("| %s | %s | %s |" % (
                        model, tag.replace("|", "\\|"), b.get("note", "--")))
        out["sections"]["continuous_s"] = cont

    # ------------------------------------------------------------- equivalence
    if equiv:
        md.append("")
        md.append("## 4. Program-equivalence audit (independent 7B judge)")
        md.append("")
        n_sig = sum(1 for s in equiv["signature_check"] if s["signatures_equal"])
        md.append("Sampled 8 families (1/schema, seed %d). A10-partner "
                  "abstract signatures equal: **%d/%d**." % (
                      equiv["env"].get("sample_seed", -1), n_sig,
                      len(equiv["signature_check"])))
        j = equiv.get("judge")
        if j:
            ag = j["agreement"]
            md.append("")
            md.append("| wording | agreement | A10 (same-program) | "
                      "A01 (near-miss) |")
            md.append("|---|---|---|---|")
            for w in ("A_same", "B_different", "C_cot"):
                if w not in ag:
                    continue
                b = ag[w]
                md.append("| %s | %.3f (%d) | %.3f | %.3f |" % (
                    w, b["agreement"], b["n"], b["per_pair_type"]["A10"],
                    b["per_pair_type"]["A01"]))
            md.append("")
            md.append("Overall agreement (one-shot wordings) **%.3f** over "
                      "%d judgements (target >= 0.85: %s). Mismatch %.1f%%; "
                      "disagreements file: %s" % (
                          ag["overall"]["agreement"], ag["overall"]["n"],
                          "MET" if j.get("target_met") else "NOT MET",
                          j.get("mismatch_fraction", float("nan")) * 100,
                          j.get("disagreements_file", "none (<=15% mismatch)")))
        o = equiv.get("oracle_recheck")
        if o:
            md.append("")
            md.append("Executable re-check: oracle walker re-run on the 8 "
                      "families: **%d/%d** plans reach a legal terminal "
                      "(%s)." % (o["n_ok"], o["n_checked"],
                                 "PASS" if o["pass"] else "FAIL"))
        out["sections"]["equivalence"] = equiv

    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=1)
    print("\n".join(md))
    print("")
    print("[report] wrote %s" % OUT_JSON)


if __name__ == "__main__":
    main()
