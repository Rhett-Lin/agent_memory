"""H3 stage A: outcome-blind feature annotation of the canonical cards
(GATE_PROTOCOL.md Part III sec.14.6 + acceptance item sec.15.5).

Every feature is computed DETERMINISTICALLY (regex/lexicon over the card
text; coverage flags from cards_map.jsonl canonical metadata).  No LLM is
used: imperative density and ordered-step count are lexicon-computable and
the postcondition / write-decision / finish flags are exact anchors or
canonical-prop metadata.  llm_used="none" is recorded per row, satisfying
sec.14.6's blind-annotation requirement without a model call (features are
never used for tuning/selection).

Features per card (from blind text + cards_map only; outcomes untouched):
  imperative_density     fraction of non-empty lines whose first content
                         word is an imperative verb (lexicon below)
  ordered_steps          count of enumerated step markers (r'^step k:' or
                         r'^k. ')
  explicit_postcondition 1 iff a "Postconditions:" section header is present
  has_write_decision     canonical-prop flag from cards_map.jsonl
  has_finish             canonical-prop flag from cards_map.jsonl
  token_count            Qwen2.5-1.5B count from cards_map.jsonl

Outputs:
  pilot/h3/blind_features.jsonl       one row per card (2560)
  pilot/h3/blind_features_summary.tsv per-arm summary (tab-separated)
  pilot/h3/blind_separation.json      Mann-Whitney U transcript vs script
                                      (2x2 arms) per numeric feature;
                                      sec.15.5 passes iff any p < 0.01

Run: python pilot/h3/blind_annotate.py
"""

import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
CARDS_MAP = os.path.join(_HERE, "cards_map.jsonl")
OUT_FEATURES = os.path.join(_HERE, "blind_features.jsonl")
OUT_TSV = os.path.join(_HERE, "blind_features_summary.tsv")
OUT_SEP = os.path.join(_HERE, "blind_separation.json")

IMPERATIVE_VERBS = {
    "read", "set", "insert", "delete", "compute", "check", "finish", "apply",
    "confirm", "aggregate", "update", "verify", "count", "list", "write",
    "move", "remove", "add", "record", "report", "ensure", "use", "keep",
}
STEP_RE = re.compile(r"^\s*(?:step\s+\d+\b|\d+\.)", re.IGNORECASE)
POSTCOND_RE = re.compile(r"^postconditions\s*:", re.IGNORECASE | re.MULTILINE)
ARMS_2X2 = ["transcript_complete", "transcript_prefix",
            "script_complete", "script_prefix"]


def first_word(line):
    s = line.strip().lstrip("-*#>)(")
    s = re.sub(r"^\d+[.)]\s*", "", s)          # drop enumerations
    m = re.match(r"[A-Za-z]+", s)
    return m.group(0).lower() if m else ""


def annotate(text):
    lines = [l for l in text.splitlines() if l.strip()]
    imp = sum(1 for l in lines if first_word(l) in IMPERATIVE_VERBS)
    return {
        "imperative_density": round(imp / max(1, len(lines)), 4),
        "ordered_steps": sum(1 for l in lines if STEP_RE.match(l)),
        "explicit_postcondition": int(bool(POSTCOND_RE.search(text))),
        "n_lines": len(lines),
    }


def main():
    rows = []
    with open(CARDS_MAP) as f:
        maps = [json.loads(l) for l in f]
    cards_root = os.path.join("/work1/zixuan/data/agent_memory/h3",
                              "public_view", "cards")
    for r in maps:
        p = os.path.join(cards_root, r["arm"], r["memory_id"] + ".json")
        with open(p) as f:
            text = json.load(f)["text"]
        feat = annotate(text)
        rows.append({"memory_id": r["memory_id"], "arm": r["arm"],
                     "form": r["form"], "coverage": r["coverage"],
                     "cell": r["cell"], "family_idx": r["card_family_idx"],
                     "has_write_decision": int(r["has_write_decision"]),
                     "has_finish": int(r["has_finish"]),
                     "token_count": r["token_count"],
                     "llm_used": "none", **feat})
    with open(OUT_FEATURES, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    arms = ["transcript_complete", "transcript_prefix",
            "script_complete", "script_prefix", "eco"]
    with open(OUT_TSV, "w") as f:
        f.write("arm\tn\timperative_density\tordered_steps\tpostcondition_frac"
                "\twrite_decision_frac\tfinish_frac\ttoken_mean\n")
        for arm in arms:
            sub = [r for r in rows if r["arm"] == arm]
            n = len(sub)
            f.write("%s\t%d\t%.4f\t%.2f\t%.4f\t%.4f\t%.4f\t%.1f\n" % (
                arm, n,
                sum(r["imperative_density"] for r in sub) / n,
                sum(r["ordered_steps"] for r in sub) / n,
                sum(r["explicit_postcondition"] for r in sub) / n,
                sum(r["has_write_decision"] for r in sub) / n,
                sum(r["has_finish"] for r in sub) / n,
                sum(r["token_count"] for r in sub) / n))

    # ---- sec.15.5: transcript vs script separation (2x2 arms, pooled) ----
    from scipy.stats import mannwhitneyu
    t_rows = [r for r in rows if r["arm"] in ARMS_2X2[:2]]
    s_rows = [r for r in rows if r["arm"] in ARMS_2X2[2:]]
    sep = {}
    for feat in ("imperative_density", "ordered_steps",
                 "explicit_postcondition"):
        x = [r[feat] for r in t_rows]
        y = [r[feat] for r in s_rows]
        u, p = mannwhitneyu(x, y, alternative="two-sided")
        sep[feat] = {"U": float(u), "p": float(p),
                     "transcript_mean": sum(x) / len(x),
                     "script_mean": sum(y) / len(y),
                     "pass_0.01": bool(p < 0.01)}
    verdict = any(v["pass_0.01"] for v in sep.values())
    with open(OUT_SEP, "w") as f:
        json.dump({"test": "mannwhitneyu two-sided, 2x2 arms pooled",
                   "n_transcript": len(t_rows), "n_script": len(s_rows),
                   "features": sep, "sec15_5_pass": verdict}, f, indent=1)
    print("[blind] %d cards annotated (llm_used=none) -> %s"
          % (len(rows), OUT_FEATURES))
    print("[blind] separation (transcript vs script, 2x2 arms):")
    for k, v in sep.items():
        print("  %-24s transcript=%.3f script=%.3f  U=%.0f p=%.2e %s"
              % (k, v["transcript_mean"], v["script_mean"], v["U"], v["p"],
                 "PASS" if v["pass_0.01"] else ""))
    print("[blind] sec.15.5 (>=1 feature separates, p<0.01): %s"
          % ("PASS" if verdict else "FAIL"))


if __name__ == "__main__":
    main()
