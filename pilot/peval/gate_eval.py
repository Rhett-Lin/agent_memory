#!/usr/bin/env python
"""Offline admission-policy (gate) evaluation on existing pilot rollouts. No new rollouts.

Deployment simulation per target instance (family_idx, sibling_idx, seed):
  1. memory store candidates = the 4 A-cell memories for (family_idx, target_sibling=sibling_idx)
  2. retriever: top-1 by sim_embed (deterministic tie-break: higher sim_tf, then memory_id)
  3. gate: admits the top-1 memory or abstains
  4. outcome = rollout success of the chosen cell for (family, sibling, seed);
     abstain -> N-arm (no-memory) success for the same instance

Policies: always_admit, never_admit, s_gate (admit iff sim_embed >= threshold),
phat_gate at several thresholds, oracle_p (admit iff sealed P==1 of the top-1 candidate;
ceiling reference only, not deployable).

P-hat scores: out-of-fold family-CV scores (phat_oof_family from pair_scores.jsonl), i.e.
each candidate pair is scored by a model that never trained on its family. This avoids
train/eval leakage in the gate simulation.

Honesty: if a (family, sibling, cell, seed) instance has no matching rollout row, the
instance is dropped from ALL policies and the drop count is reported (expected 0:
the pilot grid is complete at 160 (family,sibling) x 4 seeds x 6 cells per model).

Writes pilot/peval/GATE_EVAL.json.
"""
import argparse
import collections
import glob
import json
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROLLOUT_DIR = pathlib.Path('/work1/zixuan/outputs/agent_memory/pilot')
SEED = 42
CELLS_A = ('A00', 'A01', 'A10', 'A11')


def load_rollout_success(model: str):
    """{(family, sibling, cell, seed): success} for all rows of the given model."""
    files = sorted(glob.glob(str(ROLLOUT_DIR / f'rollouts_{model}_shard*-of-*.jsonl')))
    assert files, f'no rollout files for model={model}'
    success = {}
    n_rows = 0
    for fn in files:
        for line in open(fn):
            r = json.loads(line)
            n_rows += 1
            m = r['meta']
            key = (int(m['family_idx']), int(m['sibling_idx']), m['cell'], int(m['seed']))
            assert key not in success, f'duplicate rollout for {key}'
            success[key] = bool(r['success'])
    return success, n_rows


def top1_by_sim(cands):
    """argmax sim_embed; deterministic tie-break: sim_tf desc, then memory_id asc."""
    return sorted(cands, key=lambda c: (-c['sim_embed'], -c['sim_tf'], c['memory_id']))[0]


def bootstrap_ci(values, rng, n_boot=2000):
    """95% CI on the mean via instance-level bootstrap."""
    values = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def evaluate_policy(name, admit_fn, instances, outcomes_n, outcomes_cell):
    """admit_fn(candidate) -> bool. Returns metrics dict."""
    chosen_outcomes, accepted_cells, top1_cells = [], [], []
    n_admit = 0
    for inst, cand in instances:
        top1_cells.append(cand['cell'])
        if admit_fn(cand):
            n_admit += 1
            accepted_cells.append(cand['cell'])
            chosen_outcomes.append(outcomes_cell[(inst, cand['cell'])])
        else:
            chosen_outcomes.append(outcomes_n[inst])
    n = len(chosen_outcomes)
    exp_success = float(np.mean(chosen_outcomes))
    per_cell = {}
    for cell in CELLS_A:
        n_top1 = sum(1 for c in top1_cells if c == cell)
        n_acc = sum(1 for c in accepted_cells if c == cell)
        per_cell[cell] = {'n_top1': n_top1, 'n_accepted': n_acc,
                          'accept_rate': (n_acc / n_top1) if n_top1 else None}
    return {
        'policy': name,
        'n_instances': n,
        'n_admitted': n_admit,
        'accept_rate_overall': n_admit / n,
        'expected_success': exp_success,
        'accept_rate_by_cell': per_cell,
        'a01_accept_rate': per_cell['A01']['accept_rate'],
        '_outcomes': chosen_outcomes,  # popped before write
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='qwen7b', choices=['qwen7b', 'qwen3b'])
    ap.add_argument('--sim-threshold', type=float, default=0.80)
    ap.add_argument('--phat-thresholds', type=float, nargs='+',
                    default=[0.3, 0.4, 0.5, 0.6, 0.7])
    args = ap.parse_args()

    rng = np.random.default_rng(SEED)

    # --- candidates: the 4 A-cell pairs per (family, sibling) ---
    scores = {}
    for line in open(HERE / 'pair_scores.jsonl'):
        s = json.loads(line)
        scores[(s['family_idx'], s['target_sibling'], s['cell'])] = s
    assert len(scores) == 640
    by_group = collections.defaultdict(list)
    for (fam, sib, _cell), s in scores.items():
        by_group[(fam, sib)].append(s)
    assert len(by_group) == 160 and all(len(v) == 4 for v in by_group.values())

    # --- rollout outcomes ---
    success, n_rows = load_rollout_success(args.model)
    cells_found = collections.Counter(k[2] for k in success)

    # --- build instances; drops counted honestly ---
    instances, outcomes_n, outcomes_cell = [], {}, {}
    n_dropped = 0
    for (fam, sib), cands in sorted(by_group.items()):
        top1 = top1_by_sim(cands)
        for i in range(4):
            inst = (fam, sib, i)
            need = [(fam, sib, 'N', i)] + [(fam, sib, top1['cell'], i)]
            if any(k not in success for k in need):
                n_dropped += 1
                continue
            instances.append((inst, top1))
            outcomes_n[inst] = success[(fam, sib, 'N', i)]
            for cell in CELLS_A:
                outcomes_cell[(inst, cell)] = success[(fam, sib, cell, i)]

    policies = []
    policies.append(evaluate_policy('never_admit', lambda c: False,
                                    instances, outcomes_n, outcomes_cell))
    policies.append(evaluate_policy('always_admit', lambda c: True,
                                    instances, outcomes_n, outcomes_cell))
    policies.append(evaluate_policy(f's_gate_sim>={args.sim_threshold}',
                    lambda c: c['sim_embed'] >= args.sim_threshold,
                    instances, outcomes_n, outcomes_cell))
    for t in args.phat_thresholds:
        policies.append(evaluate_policy(f'phat_gate>={t}',
                        lambda c, t=t: c['phat_oof_family'] >= t,
                        instances, outcomes_n, outcomes_cell))
    policies.append(evaluate_policy('oracle_p', lambda c: c['P'] == 1,
                                    instances, outcomes_n, outcomes_cell))

    # --- uplift vs never_admit + bootstrap CIs ---
    never_outcomes = policies[0]['_outcomes']
    base = float(np.mean(never_outcomes))
    for p in policies:
        oc = p.pop('_outcomes')
        lo, hi = bootstrap_ci(oc, rng)
        p['expected_success_ci95'] = [lo, hi]
        uplift = p['expected_success'] - base
        p['uplift_vs_never_admit_pp'] = round(100 * uplift, 2)
        dl, dh = bootstrap_ci(np.asarray(oc, dtype=float) - np.asarray(never_outcomes, dtype=float), rng)
        p['uplift_ci95_pp'] = [round(100 * dl, 2), round(100 * dh, 2)]

    top1_dist = collections.Counter(c['cell'] for _, c in instances)
    report = {
        'config': {
            'model': args.model, 'seed': SEED,
            'retriever': 'top-1 by sim_embed (tie-break: sim_tf desc, memory_id asc)',
            'phat_score': 'phat_oof_family (family-CV out-of-fold; no train/eval leakage)',
            'sim_threshold': args.sim_threshold,
            'phat_thresholds': args.phat_thresholds,
            'abstain_outcome': 'N-arm (no-memory) rollout success, same (family,sibling,seed)',
        },
        'grid_check': {
            'rollout_rows_loaded': n_rows,
            'rows_per_cell': dict(sorted(cells_found.items())),
            'retriever_top1_cell_distribution': dict(sorted(top1_dist.items())),
            'n_instances_total_possible': 4 * len(by_group),
            'n_instances_evaluated': len(instances),
            'n_instances_dropped': n_dropped,
        },
        'policies': policies,
    }
    out = HERE / 'GATE_EVAL.json'
    # multi-model runs share one file, keyed by model name
    db = json.load(open(out)) if out.exists() else {'by_model': {}}
    db['by_model'][args.model] = report
    with open(out, 'w') as f:
        json.dump(db, f, indent=1)

    # --- stdout table ---
    print(f"model={args.model}  instances={len(instances)} dropped={n_dropped} "
          f"top1_dist={dict(sorted(top1_dist.items()))}")
    print(f"{'policy':<22} {'exp_succ':>8} {'uplift_pp':>9} {'accept':>6} "
          f"{'A00':>5} {'A01':>5} {'A10':>5} {'A11':>5}")
    for p in policies:
        pc = p['accept_rate_by_cell']
        def fmt(cell):
            r = pc[cell]['accept_rate']
            return f"{r:5.2f}" if r is not None else '    -'
        print(f"{p['policy']:<22} {p['expected_success']:8.4f} "
              f"{p['uplift_vs_never_admit_pp']:9.2f} {p['accept_rate_overall']:6.3f} "
              f"{fmt('A00')} {fmt('A01')} {fmt('A10')} {fmt('A11')}")
    print(f'-> {out}')


if __name__ == '__main__':
    main()
