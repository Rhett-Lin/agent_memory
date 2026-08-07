"""H3 (GATE_PROTOCOL.md Part III sec.14.1): generate 24 FRESH families,
disjoint from the pilot/H-C 40, with the pilot generator's quality gates.

This script does NOT modify any pilot file.  It imports the pilot generator
(generate_families.py) and runs its full main() pipeline (oracle 100% legal
terminal validation, isolation scan, sealed/public split) against the H3
config (configs/h3.yaml: new sealed generator seed 20260809, n_families=24,
paths under /work1/zixuan/data/agent_memory/h3/{sealed,public_view}).

Two monkeypatches are required (implemented here, pilot files untouched):
  * plan_families: the pilot J-split lists are hard-coded to 5 occurrences
    per schema (40 families).  For 24 (3/schema) or 32 (4/schema) families we
    recompute a balanced split so every P1 join-depth class still has
    families in BOTH domains (otherwise the generator's cross-domain A10
    pairing raises "no cross-domain partner").  Recorded in
    IMPLEMENTATION_NOTES.md.
  * build_inv_transfer: the pilot builder draws the west-row qty w0 from
    [5,60] without enforcing the transfer guard for the NEAR-MISS direction
    (west -> east moves `amount` out of the west row, which needs
    w0 >= amount + min_keep).  The pilot seed (20260807) happened to pass all
    5 draws; the H3 seed (20260809) hits the latent violation (fam 10
    near-miss, check returns B vs expected A).  The pilot's own
    cal_move_headcount builder documents the invariant ("Role-level values
    first (source must ALWAYS satisfy the guard, whether the source is the
    morning or the afternoon session)").  We wrap the builder with the same
    guard-satisfying draw for the near-miss source row ONLY; all other draws
    are untouched.  Recorded in IMPLEMENTATION_NOTES.md.

After generation this script verifies DISJOINTNESS vs the pilot benchmark
  * no shared (schema_key, params) program instance;
  * no shared task instruction string;
and writes pilot/h3/gen_report.json (seed, counts, disjointness, config
hash, commit).

Modes:
  --generate      run the generator + gates + disjointness check (default)
  --measure-n     run qwen7b on the N cells (fam x 4 sib x seeds 0..2) and
                  write pilot/h3/n_condition_stats.json; the rollout rows are
                  appended to output_root/rollouts_h3_qwen7b_ndiff.jsonl and
                  are REUSED by run_grid.py as the grid's N reference cells.
                  Exit code 2 if the aggregate N rate is outside [0.30, 0.70]
                  (then adjust distractor_rows_* within the pilot window
                  [8,20] in configs/h3.yaml, record the change, regenerate).

Run (from pilot/h3/):
  PY=.../causalmemagent/bin/python
  $PY gen_fresh_families.py --generate
  CUDA_VISIBLE_DEVICES=0 $PY gen_fresh_families.py --measure-n
"""

import argparse
import hashlib
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

import generate_families as gf  # noqa: E402
from generate_families import load_config, git_commit  # noqa: E402

DEFAULT_CONFIG = os.path.join(_HERE, "configs", "h3.yaml")
PILOT_SEALED = "/work1/zixuan/data/agent_memory/sealed"
N_BAND = (0.30, 0.70)          # GATE_PROTOCOL Part III sec.15.1 (+ sec.4.3)
GRID_SEEDS = [0, 1, 2]         # Part III sec.16: 3 seeds


# ---------------------------------------------------------------------------
# n-aware plan_families (only deviation from the pilot generator code path)
# ---------------------------------------------------------------------------

def h3_plan_families(cfg):
    """Identical to generate_families.plan_families except the P1 J-split is
    computed from n_per_schema so both join-depth classes keep families in
    both domains: crm gets J1 on the first ceil(k/2) occurrences then J2;
    inv gets J2 on the last ceil(k/2) occurrences (mirrors pilot's k=5:
    crm [1,1,1,2,2], inv [1,1,2,2,2])."""
    gcfg = cfg["generation"]
    n = gcfg["n_families"]
    gs = gcfg["generator_seed"]
    k = n // len(gf.SCHEMA_LIST)
    assert n % len(gf.SCHEMA_LIST) == 0, "n_families must be a multiple of 8"
    h1 = (k + 1) // 2
    j_split = {"crm_escalate": [1] * h1 + [2] * (k - h1),
               "inv_overstock": [1] * (k - h1) + [2] * h1}
    fams = []
    import random
    for i in range(n):
        smeta = gf.SCHEMA_LIST[i % len(gf.SCHEMA_LIST)]
        occ = i // len(gf.SCHEMA_LIST)
        rngf = random.Random(gf.sha_int("fam", gs, i))
        if smeta["key"] in j_split:
            j = j_split[smeta["key"]][occ % len(j_split[smeta["key"]])]
        else:
            j = smeta["j_levels"][0]
        params = smeta["sample"](rngf, j)
        fams.append({"idx": i, "schema_key": smeta["key"], "domain": smeta["domain"],
                     "archetype": smeta["archetype"], "params": params,
                     "occ": occ})
    return fams


def build_inv_transfer_h3(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    """build_inv_transfer with the near-miss source-row guard repair (see
    module docstring).  Verbatim copy of the pilot builder except the single
    guarded w0 draw marked below."""
    import random as _random
    prm = fp["params"]
    rng_s = _random.Random(gf.sha_int("sib", gs, fp["idx"], sib_idx, "invtr"))
    rng_d = _random.Random(gf.sha_int("state", gs, fp["idx"], sib_idx, state_seed, "invtr"))
    sku = "%s-%04d" % (rng_s.choice(gf.SKU_ALPHA), rng_s.randint(1000, 9999))
    pname = "%s assembly" % rng_s.choice(gf.PRODUCT_WORDS)
    amount, min_keep, cap = prm["amount"], prm["min_keep"], prm["cap"]
    e0 = rng_s.randint(amount + min_keep + 5, amount + min_keep + 45)
    if near_miss:
        # REPAIR (H3-only): the near-miss moves `amount` OUT of the west row,
        # so the west row must satisfy the guard: w0 >= amount + min_keep.
        # Mirrors the invariant documented in build_cal_move_headcount.
        w0 = rng_s.randint(amount + min_keep + 1, 60)
    else:
        w0 = rng_s.randint(5, 60)
    # correct program: move 'amount' east -> west; near-miss: west -> east
    src_wh, dst_wh = ("west", "east") if near_miss else ("east", "west")
    eid, wid = rng_s.randint(100, 499), rng_s.randint(500, 899)
    stock = [
        {"id": eid, "sku": sku, "warehouse": "east", "qty": e0, "flag": "normal", "review": 0},
        {"id": wid, "sku": sku, "warehouse": "west", "qty": w0, "flag": "normal", "review": 0},
    ]
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    used = {sku}
    for i in range(n_dis):
        s2 = "%s-%04d" % (rng_d.choice(gf.SKU_ALPHA), rng_d.randint(1000, 9999))
        if s2 in used:
            s2 += "X"
        used.add(s2)
        stock.append({"id": 900 + i, "sku": s2,
                      "warehouse": rng_d.choice(["east", "west", "main"]),
                      "qty": rng_d.randint(0, 90), "flag": rng_d.choice(["normal", "ok"]),
                      "review": rng_d.randint(0, 1)})
    rng_d.shuffle(stock)
    products = [{"id": 10 + i, "sku": s2, "name": "%s unit" % rng_d.choice(gf.PRODUCT_WORDS),
                 "category": rng_d.choice(gf.CATEGORIES), "price": rng_d.randint(5, 400)}
                for i, s2 in enumerate(list(used)[:10])]
    restock = [{"id": 700 + i, "sku": rng_d.choice(list(used - {sku})),
                "qty": rng_d.randint(1, 30), "status": rng_d.choice(["pending", "done"]),
                "note": "auto reorder"} for i in range(rng_d.randint(2, 6))]
    tables = {"stock": stock, "products": products, "restock_orders": restock}
    qty_src = w0 if near_miss else e0
    qty_dst = e0 if near_miss else w0
    guard = {"kind": "transfer_guard",
             "a": {"table": "stock", "where": {"sku": sku, "warehouse": src_wh}, "field": "qty"},
             "b": {"table": "stock", "where": {"sku": sku, "warehouse": dst_wh}, "field": "qty"},
             "amount": amount, "min_a": min_keep, "cap_b": cap}
    program_params = {
        "class_tag": "transfer:target>origin" if near_miss else "transfer:origin>target",
        "read_a": {"table": "stock", "filter": {"sku": sku, "warehouse": src_wh}},
        "read_b": {"table": "stock", "filter": {"sku": sku, "warehouse": dst_wh}},
        "guard": guard,
        "write_a": {"tool": "update", "args": {"table": "stock",
                    "set": {"qty": qty_src - amount},
                    "where": {"sku": sku, "warehouse": src_wh}}},
        "write_b": {"tool": "update", "args": {"table": "stock",
                    "set": {"qty": qty_dst + amount},
                    "where": {"sku": sku, "warehouse": dst_wh}}},
        "verify": {"table": "stock", "where": {"sku": sku}},
    }
    terminal = [
        {"type": "field_cmp", "table": "stock", "where": {"sku": sku, "warehouse": src_wh},
         "field": "qty", "op": "==", "value": qty_src - amount},
        {"type": "field_cmp", "table": "stock", "where": {"sku": sku, "warehouse": dst_wh},
         "field": "qty", "op": "==", "value": qty_dst + amount},
    ]
    vocab = {"what": "stock", "src": "'%s' warehouse row" % src_wh,
             "dst": "'%s' warehouse row" % dst_wh, "table": "stock",
             "min_text": "the minimum keep level", "cap_text": "its capacity"}
    roles = gf.p2_roles(vocab, False)
    move_line = ("move %d units of SKU %s from warehouse '%s' to warehouse '%s'"
                 % (amount, sku, src_wh, dst_wh))
    if style == 0:
        instr = ("Inventory rebalancing request. In the stock table, %s. The '%s' row "
                 "must keep at least %d units afterwards; the '%s' side must not exceed "
                 "%d. Read both rows, check the guard, then apply both updates and "
                 "verify." % (move_line, src_wh, min_keep, dst_wh, cap))
    elif style == 1:
        instr = ("Hi, warehouse ops here — could you %s for us (%s, in the stock table)? "
                 "Guard: '%s' must stay at %d or more after the move; '%s' may not go over "
                 "%d. Check the numbers first, do both updates, then make sure the rows "
                 "look right." % (move_line, pname, src_wh, min_keep, dst_wh, cap))
    else:
        instr = ("Ops note: %s (stock table).\nGuard: '%s' >= %d after the move; '%s' <= "
                 "%d.\nRead both rows, check, update both, verify." % (move_line, src_wh,
                 min_keep, dst_wh, cap))
    return gf.finish_instance(
        "two_row_transfer", tables, program_params, {"branch": "A"},
        terminal, roles, instr,
        {"sku": sku, "amount": amount, "min_keep": min_keep, "cap": cap,
         "src_wh": src_wh, "dst_wh": dst_wh, "qty_src0": qty_src, "qty_dst0": qty_dst,
         "n_distractors": n_dis})


def patch_builders():
    for s in gf.SCHEMA_LIST:
        if s["key"] == "inv_transfer":
            s["build"] = build_inv_transfer_h3
    gf.SCHEMAS["inv_transfer"]["build"] = build_inv_transfer_h3


# ---------------------------------------------------------------------------
# disjointness vs the pilot benchmark
# ---------------------------------------------------------------------------

def disjointness_report(h3_sealed, pilot_sealed):
    """Instance-level disjointness.  NOTE: family params live in SMALL spaces
    (e.g. ticket_purge_spam has only the 8 prefix values; inv_transfer 39
    combos), so (schema, params) collisions occur under ANY seed and do NOT
    imply identical family instances -- the instance identity is the entity /
    initial-state draw keyed by (generator_seed, family_idx).  An H3 family is
    therefore counted as shared with a pilot family only when schema, params
    AND the sibling-0/seed-0 task fingerprint (tables digest + instruction)
    are all identical.  Task-instruction overlap is reported separately."""

    def load_fams(p):
        out = {}
        with open(os.path.join(p, "families.jsonl")) as f:
            for line in f:
                r = json.loads(line)
                out[r["family_idx"]] = r
        return out

    def load_tasks(p):
        rows = []
        with open(os.path.join(p, "tasks_sealed.jsonl")) as f:
            for line in f:
                rows.append(json.loads(line))
        return rows

    def fingerprints(sealed):
        fams = load_fams(sealed)
        tasks = load_tasks(sealed)
        fp = {}
        for r in tasks:
            if r["kind"] == "sibling" and r["sibling_idx"] == 0 and r["seed"] == 0:
                fam = fams[r["family_idx"]]
                fp[r["family_idx"]] = (
                    r["schema_key"],
                    json.dumps(fam["params"], sort_keys=True),
                    r["tables_digest"], r["instruction"])
        return fp

    h3fp, pfp = fingerprints(h3_sealed), fingerprints(pilot_sealed)
    h3_set, p_set = set(h3fp.values()), set(pfp.values())
    shared_instances = sorted(h3_set & p_set)
    h3_params = {(s, p) for (s, p, _, _) in h3_set}
    p_params = {(s, p) for (s, p, _, _) in p_set}
    h3_instr = {instr for (_, _, _, instr) in h3_set} | set()
    p_instr = {instr for (_, _, _, instr) in p_set}
    # instruction overlap across ALL tasks (not just sib0), stronger check
    def all_instructions(p):
        return {json.loads(l)["instruction"] for l in
                open(os.path.join(p, "tasks_sealed.jsonl"))}
    shared_instr = sorted(all_instructions(h3_sealed) & all_instructions(pilot_sealed))
    rep = {"n_h3_families": len(h3fp), "n_pilot_families": len(pfp),
           "shared_family_instances": len(shared_instances),
           "shared_instruction_strings_all_tasks": len(shared_instr),
           "param_only_collisions_expected": sorted(
               [list(x) for x in (h3_params & p_params)][:10]),
           "param_collision_note": "small parameter spaces make (schema,params) "
                "collisions expected under any seed; they are NOT shared "
                "family instances (entities/states differ by seed-keyed draws)",
           "shared_instance_examples": [list(x)[:2] for x in shared_instances[:5]],
           "shared_instruction_examples": shared_instr[:3],
           "disjoint": not shared_instances and not shared_instr}
    return rep


# ---------------------------------------------------------------------------
# generation entry
# ---------------------------------------------------------------------------

def do_generate(config_path, check_only=False):
    cfg = load_config(config_path)
    t0 = time.time()
    if not check_only:
        gf.plan_families = h3_plan_families        # monkeypatch (H3-only)
        patch_builders()                           # inv_transfer NM repair
        sys.argv = ["generate_families.py", "--config", config_path]
        gf.main()                                  # runs ALL pilot gates;
        # exits non-zero on oracle/isolation/similarity failure.
    rep = disjointness_report(cfg["paths"]["sealed"], PILOT_SEALED)
    with open(config_path, "rb") as f:
        chash = hashlib.sha1(f.read()).hexdigest()[:12]
    rep.update({
        "config": config_path, "config_hash": chash,
        "git_commit": git_commit(),
        "generator_seed": cfg["generation"]["generator_seed"],
        "pilot_generator_seed": 20260807,
        "n_families": cfg["generation"]["n_families"],
        "siblings_per_family": cfg["generation"]["siblings_per_family"],
        "state_seeds": cfg["generation"]["state_seeds"],
        "distractor_rows": [cfg["generation"]["distractor_rows_min"],
                            cfg["generation"]["distractor_rows_max"]],
        "created": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.gmtime()),
        "elapsed_sec": round(time.time() - t0, 1),
    })
    out = os.path.join(_HERE, "gen_report.json")
    with open(out, "w") as f:
        json.dump(rep, f, indent=1)
    print("[h3gen] disjointness: %s (shared instances=%d, shared instructions=%d, "
          "param-only collisions=%d)"
          % ("CLEAN" if rep["disjoint"] else "VIOLATION",
             rep["shared_family_instances"],
             rep["shared_instruction_strings_all_tasks"],
             len(rep["param_only_collisions_expected"])))
    print("[h3gen] report -> %s" % out)
    if not rep["disjoint"]:
        raise SystemExit("[h3gen] fresh families are NOT disjoint from pilot; "
                         "do not proceed")


# ---------------------------------------------------------------------------
# N-condition difficulty measurement (doubles as the grid's N reference cells)
# ---------------------------------------------------------------------------

def do_measure_n(config_path, model_key, batch_size):
    from harness import load_model, run_rollouts, build_episode
    from run_pilot import load_sealed, config_hash_cached
    cfg = load_config(config_path)
    cfg["_config_path"] = config_path
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    sealed = cfg["paths"]["sealed"]
    pub = cfg["paths"]["public_view"]
    out_path = os.path.join(cfg["paths"]["output_root"],
                            "rollouts_h3_%s_ndiff.jsonl" % model_key)
    os.makedirs(cfg["paths"]["output_root"], exist_ok=True)

    tasks, cells_map, fams = load_sealed(sealed)
    tasks_by_key = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
                    for r in tasks}
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            for line in f:
                try:
                    m = json.loads(line)["meta"]
                    done.add((m["family_idx"], m["sibling_idx"], m["seed"]))
                except Exception:
                    continue
    chash = config_hash_cached(config_path)
    commit = git_commit()
    env_versions = {"vllm": "unknown"}
    try:
        import vllm, torch
        env_versions = {"vllm": vllm.__version__, "torch": torch.__version__,
                        "gpu": torch.cuda.get_device_name(0)}
    except Exception:
        pass

    episodes = []
    for fi in sorted(fams):
        for sib in range(cfg["grid"]["n_target_siblings"]):
            for seed in GRID_SEEDS:
                if (fi, sib, seed) in done:
                    continue
                trow = tasks_by_key[(fi, sib, seed)]
                ep = build_episode(pub, trow, None, "N", seed,
                                   {"memory_id": None, "model": model_key,
                                    "arm": "N", "system": "h3",
                                    "config_hash": chash, "git_commit": commit,
                                    "env_versions": env_versions})
                episodes.append(ep)
    print("[h3gen] measure-n: %d N-condition rollouts to run (skipped %d done)"
          % (len(episodes), len(done)))
    if episodes:
        print("[h3gen] loading model %s ..." % cfg["models"][model_key])
        llm = load_model(cfg["models"][model_key], cfg)
        results = run_rollouts(llm, episodes, cfg, batch_size=batch_size)
        with open(out_path, "a") as out:
            for r in results:
                out.write(json.dumps(r) + "\n")
    # stats over the full file (fresh + resumed rows)
    rows = []
    with open(out_path) as f:
        for line in f:
            rows.append(json.loads(line))
    n_succ = sum(1 for r in rows if r["success"])
    tot_ok = sum(r["parse_ok"] for r in rows)
    tot_steps = sum(r["parse_ok"] + r["parse_fail"] for r in rows)
    per_fam = {}
    for r in rows:
        per_fam.setdefault(r["meta"]["family_idx"], []).append(bool(r["success"]))
    fam_rates = {str(k): sum(v) / len(v) for k, v in sorted(per_fam.items())}
    rate = n_succ / max(1, len(rows))
    stats = {
        "model": model_key, "n_rollouts": len(rows), "n_success": n_succ,
        "n_success_rate": rate,
        "band": list(N_BAND),
        "in_band": bool(N_BAND[0] <= rate <= N_BAND[1]),
        "parseable_action_rate": tot_ok / max(1, tot_steps),
        "per_family_rates": fam_rates,
        "grid_seeds": GRID_SEEDS,
        "config_hash": chash, "git_commit": commit,
        "env_versions": env_versions,
        "generator_seed": cfg["generation"]["generator_seed"],
        "distractor_rows": [cfg["generation"]["distractor_rows_min"],
                            cfg["generation"]["distractor_rows_max"]],
        "rollouts_file": out_path,
        "note": "rows in rollouts_file are the H3 grid's N reference cells "
                "(run_grid.py skips them on resume)",
        "created": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.gmtime()),
    }
    out_json = os.path.join(_HERE, "n_condition_stats.json")
    with open(out_json, "w") as f:
        json.dump(stats, f, indent=1)
    print("[h3gen] N rate = %.3f (%d/%d), band [%.2f, %.2f] -> %s; "
          "parseable = %.4f; per-family min..max = %.3f..%.3f"
          % (rate, n_succ, len(rows), N_BAND[0], N_BAND[1],
             "IN BAND" if stats["in_band"] else "OUT OF BAND",
             stats["parseable_action_rate"],
             min(fam_rates.values()), max(fam_rates.values())))
    print("[h3gen] stats -> %s" % out_json)
    if not stats["in_band"]:
        print("[h3gen] N rate outside 30-70%: adjust distractor_rows_* within "
              "[8,20] in configs/h3.yaml (record the change), regenerate "
              "families, re-run --measure-n")
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--check-only", action="store_true",
                    help="only re-run the disjointness report on existing data")
    ap.add_argument("--measure-n", action="store_true")
    ap.add_argument("--model", default="qwen7b")
    ap.add_argument("--batch-size", type=int, default=96)
    args = ap.parse_args()
    if args.measure_n:
        do_measure_n(args.config, args.model, args.batch_size)
    elif args.check_only:
        do_generate(args.config, check_only=True)
    else:
        do_generate(args.config)


if __name__ == "__main__":
    main()
