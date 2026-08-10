# DATA_SPEC — SFT-extractor training corpus (φ+d lane C): 4,000 texts / 200 families

Production plan for scaling the mint20 prototype (`mint_spec.py`, feasibility verdict:
YES — see FEASIBILITY.md) to the adjudicated pool: ≥4,000 texts, ≥200 latent families,
families split BEFORE rendering, balanced across archetypes / domains / renderer styles /
program relations, with 300/1k/3k learning-curve subsets. No generator edits; new
per-schema clause tables live in the mint, not in `generate_families.py`. Training view =
`{text, gold_ir}` only; everything else (family/cell/style/signature/evidence offsets) is
provenance sidecar for audits and slicing, eval/join-only (SPEC.md §1 whitelist carries
over: only the text ever enters a prompt).

## 1. Family plan and group split (BEFORE any rendering)

- 200 families = 25 per schema × 8 schemas (interleaved, same `plan_families` algorithm:
  `sample(rngf, j)` per family with `rngf = sha_int("fam", gs_mint, idx)`), giving
  exactly 50 families per archetype and 50 per domain. P1 join-depth split extended from
  the generator's pattern: crm_escalate 15 J1 + 10 J2; inv_overstock 10 J1 + 15 J2.
- **New mint seed `gs_mint` ≠ the sealed benchmark seed (20260807)** so no family params
  — hence no texts — collide with the evaluation benchmark. Decontamination gate: zero
  sha-overlap between minted texts and the 532 benchmark texts (`pairs.jsonl` +
  `tasks_sealed` instructions). The feasi probe confirms params re-derive texts exactly,
  so a param-hash plus text-hash check is airtight.
- Group split computed from the family PLAN ENTRY ONLY, before `build_*` is ever called:
  `bucket = int(sha1(f"{gs_mint}|group|{family_idx}")[:8], 16) % 10` →
  0–7 train (160 fam), 8 dev (20 fam), 9 test (20 fam). All 20 texts of a family stay in
  its group (no family leakage across splits; mirrors the family-cluster bootstrap of the
  eval protocol).

## 2. Per-family text quota (20 texts/family → 4,000 total)

| slice | per family | total | notes |
|---|---|---|---|
| instructions: 4 siblings (styles rotate `(fam+sib)%3`) | 4 | 800 | correct program |
| instructions: 1 near-miss (style `fam%3`) | 1 | 200 | flipped program |
| cards A11 (sibling programs, 1/sibling) | 4 | 800 | same-program positive |
| cards A10 (cross-domain same-signature partner) | 2 | 400 | P=1,S=0 positive |
| cards A01 (near-miss programs) | 4 (even fam) / 5 (odd fam) | 900 | calibration negative |
| cards A00 (unrelated-program partner) | 5 (even) / 4 (odd) | 900 | calibration negative |

Program-relation mix: same-program 1,200 (40%) / near-miss 900 (30%) / unrelated 900
(30%). Card style assignment reuses the generator's Latin square
(`style_idx = (fidx·n_sib + s + CELL_RANK[cell]) % 6`) with the generator's balance audit
(max–min ≤ 2 per cell) re-asserted. Archetype/domain: exactly balanced by the family plan
(§1). Near-miss kind per archetype is fixed by construction (flip_polarity /
reverse_direction / wrong_child_set / skip_archive).

**Near-miss inclusion policy:** A01 cards and near-miss instructions are first-class SFT
inputs WITH their own faithful gold IRs (the flipped/mutated program as rendered — never
re-labeled to the correct program). The comparator needs exactly these as negatives to
calibrate; the extractor must learn to carry the mutation into the IR (e.g.
`op: "<="` on flipped P1, absent-with-evidence archive node on P4 near-miss). No
down-weighting; cell tag stays in the provenance sidecar for later stratified analysis.
Sham (Q) cards are excluded from the mint (non-DB procedures, no op-algebra mapping);
revisit only if the comparator wants explicit "no-program" negatives.

## 3. Learning-curve subsets (300 / 1,000 / 3,000, nested, frozen)

From the 3,200 train texts: order key `sha1(gs_mint|"curve"|pair_id)`; LC300 = first 300,
LC1000 ⊇ LC300, LC3000 ⊇ LC1000. At each level assert per-archetype share within ±5pp of
the global mix (12.5%/25%-target checks) — re-draw rule documented if violated (expected
unnecessary at these sizes, but the gate freezes the decision before looking). Dev/test
fixed at 400/400 for all curves. The pair order key is frozen in the run manifest with
the output sha256 (as the prototype already does).

## 4. Renderer diversity levers

**Available TODAY (used, zero new code):**
- 3 instruction styles per schema (formal request / casual ask / ops note), fixed rotation.
- 6 memory card styles (formal_sop, runbook_bullets, postmortem, terse_note, training_qa,
  checklist) with Latin-square counterbalancing.
- Entity pools: 32×32 names, e-mail domains, SKU/product/category vocab, ticket
  prefixes/topics, event words/rooms/dates, channels/queues/sources/teams.
- join_depth 1/2 for P1 (numeric theta vs policy-table indirection) — the symbolic-value
  lever.
- 4 near-miss mutation kinds (one per archetype), each executable and terminal-legal.
- Cross-domain P=1 pairing (A10) and unrelated pairing (A00) from the family class map.
- Length/noise: 18 fixed filler lines appended as "Note:" lines (task-neutral boilerplate
  the gold IR provably ignores — core-region cut verified in the prototype).
- 4 state seeds (initial DB variation; does not change text — irrelevant for SFT texts).

**Needs BUILDING (mint-side additions, no generator-file edits; est. each):**
- Card variant that PRINTS the numeric theta (and optionally a policy pointer) — closes
  the shortcut risk that kind⇒value-mode (all current P1/P2 cards are symbolic, all J1
  instructions numeric). Highest-priority addition. ~0.5–1 d incl. balance re-checks.
- More instruction styles (>3) and card templates (>6): ~0.5 d per style per archetype
  amortized (clause tables extend mechanically).
- Paraphrase/lexical diversity within a template (synonym tables for verbs/nouns): ~1 d.
- Interleaved distractor sentences inside the text body (fillers today append ONLY at the
  tail — a positional artifact a model can shortcut on): ~0.5–1 d.
- Negated-vs-affirmative phrasing mixtures where the archetype fixes polarity today:
  ~0.5 d per archetype (polarity must then flip per text via the cue rule — already
  implemented).
- New domains for existing archetypes: ~0.5–1 d per domain (new vocab/table names only);
  new archetypes: not in scope for lane C.
- Typo/format noise: not recommended before the comparator is frozen.

## 5. Pipeline steps and verification gates (production mint)

1. `plan_families` with gs_mint → family plan; group-split assignment; freeze plan JSON.
2. Per remaining archetype (P2/P3/P4 × 6 schemas): write clause tables + projection
   (same pattern as `p1_vocab`/`project_*`): P2 composite guard predicate (op-set
   {">=","<="}, membership values, stated commutation), P3 aggregate node + negative
   polarity + audit_sink + two-writes commutation + NM `>=1`-on-done-set, P4 guard
   predicate + archive/delete write chain + absent-with-evidence archive on NM.
3. Mint all texts + gold IRs (single CPU pass, minutes; tokenizer loaded once).
4. Gates (all hard-fail, as in the prototype): byte-determinism (re-run ⇒ identical
   sha256); `validate_ir` on every gold IR; op sequence vs signature expansion; op/value/
   polarity vs program_params under the symbolic policy (bidirectional theta check);
   policy_row/effects/termination consistency; 100% evidence re-slice with offsets, all
   inside the core region; quota/balance audits (§1–3); decontamination vs benchmark.
5. Emit `train_4000.jsonl` (+ group/subset manifests + report with sha256).

## 6. Effort estimate

- **Option A — mechanism over existing renderer hooks (recommended):** remaining
  clause tables + projections for 6 schemas ≈ 2.5–3.5 d (P1/2 schemas done & verified in
  the prototype; P3/P4 slightly cheaper than P2's composite guard); driver (family plan,
  split, quotas, nested subsets, manifests) ≈ 1 d; gates/report/docs ≈ 0.5–1 d.
  **Total ≈ 4–5.5 eng-days.** Zero freeze risk (sealed generator untouched); clause
  tables double as an executable renderer spec.
- **Option B — renderer provenance retrofit first:** span-tracking segments in the 8
  builders + 6 card templates with byte-identity regression against sealed artifacts
  ≈ 1.5–2.5 d; then projections for 3 more archetypes ≈ 1.5–2 d. **Total ≈ 3–4.5 d**
  but touches the frozen generator (process + byte-diff risk on 1,600 sealed files) and
  saves net effort only if many new schemas are expected.
- **Call: Option A. Minting can start this week** — P1 subset (200 J1/J2 P1 texts incl.
  near-miss + symbolic/numeric mix) is producible NOW from the verified prototype;
  full 4,000 lands within the Option-A estimate.
