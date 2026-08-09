#!/usr/bin/env python
"""Build pilot/peval/pairs.jsonl: one row per (memory_id, family_idx, target_sibling) A-cell pair.

Inputs (read-only):
  - /work1/zixuan/data/agent_memory/sealed/sim_report.csv      (cell, P, S, sim_tf, sim_embed)
  - /work1/zixuan/data/agent_memory/sealed/tasks_sealed.jsonl  (instruction per task)
  - /work1/zixuan/data/agent_memory/sealed/families.jsonl      (archetype/domain per family_idx)
  - /work1/zixuan/data/agent_memory/public_view/memories/<memory_id>.json  (memory card text)
  - /work1/zixuan/data/agent_memory/public_view/tasks/<task_id>.json       (cross-check only)

Instruction mapping assumption (verified here, documented in README.md):
  The target task of a pair (family_idx, target_sibling) is the benchmark's
  kind=='sibling' task for that (family, sibling). Within each such group the
  instruction is INVARIANT across the 4 seeds (verified over all 640 sibling
  tasks: exactly 1 distinct instruction per (family, sibling)); the database
  state / entity distractors vary by seed, but the instruction text does not.
  Each sibling task's sealed instruction is additionally cross-checked for
  string equality against its public task file (matched by task_id), so the
  instruction used here is publicly observable.

Validations enforced:
  - exactly 640 A-cell rows (160 per cell, Q rows skipped)
  - P == 1 iff cell in {A10, A11}; S == 1 iff cell in {A01, A11}
  - no missing/empty instruction or memory text
  - unique (memory_id, family_idx, target_sibling) keys
"""
import collections
import csv
import json
import pathlib

ROOT = pathlib.Path('/work1/zixuan')
SEALED = ROOT / 'data/agent_memory/sealed'
PUBLIC = ROOT / 'data/agent_memory/public_view'
OUT = pathlib.Path(__file__).resolve().parent / 'pairs.jsonl'


def main() -> None:
    # --- families: archetype/domain per family_idx ---
    fams = {}
    with open(SEALED / 'families.jsonl') as f:
        for line in f:
            d = json.loads(line)
            fams[int(d['family_idx'])] = d
    assert len(fams) == 40, f'expected 40 families, got {len(fams)}'

    # --- instruction mapping: (family_idx, sibling_idx) -> unique seed-invariant instruction ---
    instr_variants = collections.defaultdict(set)
    n_sibling_tasks = 0
    with open(SEALED / 'tasks_sealed.jsonl') as f:
        for line in f:
            t = json.loads(line)
            if t['kind'] != 'sibling':
                continue  # near_miss tasks are memory-episode sources, not target tasks
            n_sibling_tasks += 1
            key = (int(t['family_idx']), int(t['sibling_idx']))
            instr_variants[key].add(t['instruction'])
            # cross-check sealed instruction == public instruction (same task_id)
            pub = json.load(open(PUBLIC / 'tasks' / f"{t['task_id']}.json"))
            assert pub['instruction'] == t['instruction'], (
                f"public/sealed instruction mismatch for task_id={t['task_id']}")
    assert n_sibling_tasks == 640, f'expected 640 sibling tasks, got {n_sibling_tasks}'
    assert len(instr_variants) == 160, f'expected 160 (family,sibling) pairs, got {len(instr_variants)}'
    varying = [k for k, v in instr_variants.items() if len(v) != 1]
    assert not varying, f'instruction varies by seed for: {varying}'
    instruction = {k: next(iter(v)) for k, v in instr_variants.items()}

    # --- sim_report A rows -> pairs ---
    rows = []
    with open(SEALED / 'sim_report.csv') as f:
        for r in csv.DictReader(f):
            if not r['P']:  # Q rows carry no labels; skip
                continue
            fam, sib, cell = int(r['family_idx']), int(r['target_sibling']), r['cell']
            P, S = int(r['P']), int(r['S'])
            assert cell in ('A00', 'A01', 'A10', 'A11'), f'unexpected cell {cell}'
            assert P == (1 if cell in ('A10', 'A11') else 0), f"P/cell mismatch: {r}"
            assert S == (1 if cell in ('A01', 'A11') else 0), f"S/cell mismatch: {r}"
            mem_path = PUBLIC / 'memories' / f"{r['memory_id']}.json"
            assert mem_path.exists(), f'missing memory file {mem_path}'
            mem = json.load(open(mem_path))
            assert mem['memory_id'] == r['memory_id']
            text = mem['text']
            assert isinstance(text, str) and text.strip(), f"empty memory text {r['memory_id']}"
            rows.append({
                'memory_id': r['memory_id'],
                'family_idx': fam,
                'target_sibling': sib,
                'cell': cell,
                'P': P,
                'S': S,
                'instruction': instruction[(fam, sib)],
                'memory_text': text,
                'sim_tf': float(r['sim_tf']),
                'sim_embed': float(r['sim_embed']),
                'archetype': fams[fam]['archetype'],
                'domain': fams[fam]['domain'],
            })

    assert len(rows) == 640, f'expected 640 pair rows, got {len(rows)}'
    keys = {(r['memory_id'], r['family_idx'], r['target_sibling']) for r in rows}
    assert len(keys) == 640, 'duplicate (memory_id, family_idx, target_sibling) keys'
    cells = collections.Counter(r['cell'] for r in rows)
    assert len(cells) == 4 and all(v == 160 for v in cells.values()), f'cell counts off: {cells}'

    rows.sort(key=lambda r: (r['family_idx'], r['target_sibling'], r['cell']))
    with open(OUT, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')

    nP = sum(r['P'] for r in rows)
    print(f'wrote {OUT} : {len(rows)} rows')
    print(f'cells: {dict(sorted(cells.items()))}')
    print(f'P=1: {nP}  P=0: {len(rows) - nP}   S=1: {sum(r["S"] for r in rows)}')
    print('archetypes:', dict(collections.Counter(r['archetype'] for r in rows)))
    print('domains:', dict(collections.Counter(r['domain'] for r in rows)))


if __name__ == '__main__':
    main()
