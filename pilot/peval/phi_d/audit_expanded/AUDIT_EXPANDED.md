# AUDIT_EXPANDED — φ-extracted IR faithfulness audit (v2 corpus, 532/532)

**Status.** Mandatory step 3-4 of the adjudicated ordering (Codex thread 019fe66c,
round 2, RESEARCH_LEDGER 2026-08-10: rescue → merge → **expanded faithfulness audit** →
S2-rc1 → round-3 review → final hash → one 640-run). This audit decides **which
veto-bearing fields may be hard vetoes** in the upcoming comparator. CPU-only,
deterministic (stdlib, seed 42), no prompts, no GPU, no extractor changes, no git
mutations. Sealed truth (`/work1/zixuan/data/agent_memory/sealed/*`) was used ONLY to
define truth targets and score — never as model input (there is no model here).

**Verdict up front.** Under the frozen gate (overall ≥0.90 / per-archetype ≥0.80 /
false-ABSENT ≤0.05), **no veto-bearing field passes on this corpus. Only
`pred_op` reaches content agreement ≥0.90 where asserted (0.908) and is therefore
eligible for positive-only, soft-evidence use. Everything else must be demoted to soft
evidence or excluded.** Details + comparator tolerances below.

## 1. Inputs

| input | role |
|---|---|
| `pilot/peval/phi_d/out/extractions_v2.jsonl` | 532/532 valid IRs (canonical v2 merge; 160 instruction + 372 memory texts) |
| `pilot/peval/pairs.jsonl` | 640 pairs (cells A00/A01/A10/A11) — cell attribution for stratification |
| `sealed/families.jsonl` / `tasks_sealed.jsonl` / `memories_sealed.jsonl` | sealed truth (audit-only access) |
| `pilot/peval/phi_d/out/guided/faithfulness_audit.json` (+ `.py`) | prior 30-sample audit; join machinery and the two pre-declared exceptions re-used |

## 2. Method (pre-registered; full rules in `audit_expanded.py` header)

- **Join.** Instruction text → all sealed sibling tasks with identical text. Memory
  text → all non-`sham` sealed memory rows with identical text, each mapped to its
  truth task (`sibling_same_family` → sibling task; `near_miss` → near-miss task of the
  family, the 4 per-family nm tasks are dimension-identical — verified; `cross_domain_pair` /
  `unrelated` → sibling task of `source_family`). `sham` (cell `Q`, 160 rows) has 0 text
  intersection with the corpus and is excluded explicitly. **532/532 joined, 0
  archetype conflicts.**
- **Partial-consensus per dimension.** If candidate tasks disagree on a normalized
  truth dimension, that dimension is **UNMEASURABLE** for that sample (excluded from
  numerator and denominator; counted). Conflicts corpus-wide: `pred_value` 36 texts,
  `scope` 11 texts, signature/op/effects/roles 0.
- **IR predicate carrier.** First node (id order) with non-null `args.predicate`, ANY
  op — the nullable-args guide schema lets predicate/effect payloads migrate onto
  read/aggregate nodes; carrier op is recorded, and branch-node presence is measured
  separately (context field `branch_presence`).
- **Truth per archetype** from `program_params`/signature: P1 `(cond_field, cond_op,
  theta, write_a/b sets; +policy_row iff J2)`, P2 `(guard fields, op∈{>=,<=},
  {min_a,cap_b}, transfer direction via the a/b where-discriminator, decrease/increase
  effects)`, P3 `(child table count anchor, check.op/value, parent-status + log-etype
  effects, scope=(child table, filter triple))`, P4 `(check field/op/'cold',
  {archive→audit_sink if required}+delete child+subject, archive_required = not
  skip_archive)`.
- **Pre-declared exceptions (evidence-backed from the previous audit, re-used
  verbatim):** (E1) polarity clause-artifact — else-path guard fragment re-targeting;
  (E2) value-as-stated — when the truth number's digits appear nowhere in the
  condition window, symbolic references score as faithful (J2 `policy_value_field`
  tokens; P2 MIN/CAP concept sets; P3 ZERO/ONE concept sets). Undecidable values
  (join conflicts + digit-absent texts with no symbolic handle) are **UNMEASURABLE,
  never wrong**.
- **Gate (frozen from adjudication).** Per field: overall all-rows agreement ≥0.90
  (missing counts as disagreement; UNMEASURABLE/NA excluded), worst per-archetype
  all-rows ≥0.80, false-ABSENT-on-truth-present ≤0.05. **Veto rule:** PASS → HARD
  VETO; FAIL & present-only ≥0.90 → positive-only veto / soft evidence
  (unknown-if-absent); FAIL & present-only <0.90 → excluded.
- **V1.1 measurement corrections** (bugfixes found on the first implementation run;
  each implements semantics already declared in v1.0 — no rule was changed to make a
  field pass; v1.0 numbers quoted where they differ): B1 numeric probe of truth values
  int-normalized with word boundaries; B2 archive ordering at effect granularity
  (within-carrier list order); B3 P2 effects matched after role α-renaming (canonical
  role names count, per the declared rule); B4 resolver action-aware default
  (notify/report → audit_sink); B5 termination verbatim evidence tightened (≥8 chars,
  ≥2 tokens, substring). Deltas: `archive_capture` all-rows 0.354→0.517 (B2);
  `branch_effects` 0.274→0.327 (B3); `termination` 0.545→0.468 present-only
  0.843→0.724 (B5, removing false passes from degenerate evidence `'none'`). Other
  fields unchanged within rounding.

## 3. Corpus context (regime the comparator must live in)

- **branch_presence (context field):** IRs with ≥1 `branch` node: **281/532 = 52.8%**
  (per archetype: conditional_write 73.2%, delete_after_capture 52.4%, two_row_transfer
  37.5%, aggregate_gate **36.7%**). Predicate carriers: `branch` 246, `read` 210,
  `aggregate` 40, `verify` 3, none 33 (6.2% of IRs have no predicate payload anywhere);
  253/532 = 47.5% of IRs carry their "branch predicate" on a **non-branch** carrier.
- **Effects payload location:** carrier+(extra) 307, carrier-only 164, write-nodes-only
  61, none 0 (by archetype in `field_metrics.json → corpus.effects_payload_location`).
- **Roles (all 6 slots, all rows):** present 19.9% / **absent 44.7%** / **unknown
  35.3%** — reproduces the registered 35.3% unknown share. Over **generator-required**
  slots (1237): present **41.4%**, unknown 39.0%, **false-ABSENT 19.6%** (worst
  delete_after_capture 29.6%).
- **Termination:** present 343 (64.5%), unknown 188 (35.3%), absent 1.
- **Value decidability:** 35 rows value-UNMEASURABLE via join conflict (of 36
  conflicting texts: 12 P1-theta — the documented "12/372" — plus 24 P2 guard-set
  conflicts, same phenomenon counted uniformly) + 63 rows where the text itself is
  value-abstracted ("the complaint threshold stated in the request"; J1 symbolic
  styles) → **98/532 (18.4%) of rows cannot yield a numeric theta from text alone**;
  D3: 100% of those 63 rows' IRs emit a symbolic non-numeric reference (text-faithful;
  no numeric fabrication).

## 4. FIDELITY GATE TABLE (n_app = applicable rows; allR = all-rows; pres = present-only; worstA = worst per-archetype all-rows; fABS = false-ABSENT rate)

| field | n_app | unmeas | allR | pres | worstA | fABS | gate | veto eligibility |
|---|---|---|---|---|---|---|---|---|
| pred_attribute | 532 | 0 | 0.355 | 0.564 | 0.094 (P2) | 0.0075 | FAIL | **excluded** |
| pred_op | 532 | 0 | 0.558 | **0.908** | 0.398 (P3) | 0.0113 | FAIL | **positive-only veto / soft evidence** |
| pred_value | 434 | 98 | 0.479 | 0.846 | 0.320 (P3) | 0.0138 | FAIL | excluded |
| pred_polarity | 532 | 0 | 0.477 | 0.777 | 0.070 (P3) | 0.0113 | FAIL | excluded |
| pred_all (4-way) | 472 | 60 | 0.269 | 0.435 | 0.021 (P2) | 0.0000 | FAIL | excluded |
| branch_effects | 532 | 0 | 0.327 | 0.349 | 0.047 (P2) | 0.0000 | FAIL | excluded |
| direction (P2) | 64 | 0 | 0.266 | 0.288 | 0.266 | 0.0000 | FAIL | excluded |
| scope (P3/P4) | 304 | 11 | 0.497 | 0.651 | 0.145 (P3) | 0.0000 | FAIL | excluded |
| archive_capture (P4) | 147 | 0 | 0.517 | 0.517 | 0.517 | 0.0000 | FAIL | excluded |
| roles_required | 532 | 0 | 0.320 | 0.320 | 0.048 (P4) | **0.3271** | FAIL | excluded |
| termination | 532 | 0 | 0.468 | 0.724 | 0.266 (P2) | 0.0019 | FAIL | excluded |

Per-archetype all-rows (P1/P2/P3/P4): pred_op .752/.453/.398/.545 · pred_value
.564/.439/.320/.561 · pred_polarity .778/.391/.070/.540 · pred_attribute
.418/.094/.125/.551 · branch_effects .771/.016/.125/.059 · scope —/.145/.717 ·
roles_required .791/.391/.117/.048 · termination .758/.469/.367/.519 ·
archive_capture —/—/.517. Per-kind all-rows: instructions score same-or-higher on
every content field except scope/archive (memory-side cells are harder:
direction .125 vs .350 on instructions).

## 5. Veto eligibility for the comparator (final list)

1. **`pred_op` — positive-only veto / soft evidence only.** Where a predicate carrier
   exists AND op is asserted (327/532 = 61.5%), exact op agreement with the family
   truth is 297/327 = **90.8%** (and the 30 misses are dominated by the P3
   anchor-drift pattern below, i.e. they are *not* random). It may be used as
   directional contradict-evidence when asserted; it must NOT produce contradictions
   when the carrier/op is absent or unknown, and it can never be the sole hard veto
   (all-rows 0.558, worst-archetype 0.398).
2. **Everything else — demoted.** pred_attribute, pred_value, pred_polarity, pred_all,
   branch_effects, direction, scope, archive_capture, roles, termination: excluded from
   hard veto (per the demotion rule; for fields whose failure is omission-dominated
   they may still feed UNKNOWN/abstain accounting — see tolerances).
3. **Roles: ABSENT is unusable as a veto reason in either direction** — false-ABSENT
   on required slots is 19.6% slot-level (32.7% row-level), 220× the 0.05 allowance.
   UNKNOWN shares stay abstain fuel: 39.0% of required slots.

## 6. What the comparator must tolerate (measured constraints)

1. **Branch-omission regime:** 47.2% of IRs have no branch node (aggregate_gate 63.3%
   missing, P2 62.5% missing); the predicate/effects payload sits on non-branch
   carriers (47.5%) or is absent entirely (6.2%). Any veto keyed on `branch` nodes
   covers ≤52.8% of the corpus — branch-dependent rules must have a carrier-agnostic
   reading or treat missing-branch as abstain, not as contradiction.
2. **Effects under-population/mislocation:** strict then/else set-equality with the
   family truth holds in only 32.7% overall (best P1 77.1%; P2 1.6%, P3 12.5%, P4 5.9%
   — payload dropped, moved to standalone write nodes, or emitted with `none`/
   placeholder targets). Branch-effect set equality cannot gate anything; at most soft
   evidence where both sides carry full payload.
3. **Roles collapse:** required slots only 41.4% present; false-ABSENT 19.6%; P4
   audit_sink routinely marked `absent` while `archived_leads` is named in the text
   (see `failed_examples/roles_required.jsonl`). Comparator's completeness-certificate
   clause ("absent 裸值永不成否决理由") is confirmed as load-bearing by measurement.
4. **Value indirection:** 18.4% of rows are text-undecidable or join-undecidable for
   numeric theta; symbolic policy/threshold references are the norm in memory texts
   (73/372 texts have >1 sealed row; 36 value conflicts). Threshold comparison must be
   symbolic (per the adjudicated 阈值符号化 clause) — and even symbolic, agreements are
   only 84.6% present-only.
5. **Polarity P3 systematic re-anchoring:** under the frozen truth rule, **100% of P3
   polarity disagreements (59/59)** are `ir positive / truth negative` — the IR
   re-anchors "if no subtask is open" to the positive count form (`count == 0`). Not
   noise; but unusable for veto: polarity excluded.
6. **Attribute is a surface concept:** 82.9% of attribute "disagreements" (121/146) are
   verbatim text substrings that simply use the text's vocabulary instead of the sealed
   field name (`on-hand quantity` vs `qty`). Attribute-level veto without a
   role/anchor mapping would fire on text-faithful extractions. Excluded.
7. **Direction (P2) unreliable:** 73.4% disagree (41 hard contradictions + 6
   omission-shaped out of 64); dominant failure = role evidence spans covering the
   whole "move from X to Y" sentence, leaking both descriptors into both channels, or
   degenerate bindings (source surface = the shared SKU). See
   `failed_examples/direction.jsonl`.
8. **Termination:** 35.3% unknown, 1 row false-absent; where present, 72.4% carry a
   verbatim quote. Unknown → abstain only; never evidence.

## 7. Top-3 measured extraction weaknesses

1. **Program-structure coverage of the conditional core.** Only 52.8% of IRs contain a
   branch node (worst archetypes ~37%); 38.5% of rows never assert the predicate op;
   full then/else effect sets match truth in 32.7%. The conditional payload is the
   single most-dropped structure (P3 aggregate steps: aggregate op exists in only
   84/532 IRs — the registered op-vocabulary drift persists).
2. **Roles discipline (ABSENT≠UNKNOWN collapse).** Required-role slots: 41.4% present /
   39.0% unknown / 19.6% false-ABSENT; P4 worst (present 30.9%, false-ABSENT 29.6%,
   row-level agreement 4.8%). Audit-sink/child-set bindings in P4/P3 are systematically
   absent-or-unknown even when the text names them.
3. **Condition anchoring drift on composite conditions (P3/P2).** P3 predicates are
   re-anchored from the required count-comparison (`count(non-done)==0`) to the raw row
   filter (`status!='done'`): op `!=` vs truth `==` and polarity normalized positive in
   100% of P3 polarity misses; P2 direction bindings are wrong/absent in 73.4% (evidence
   spans leak both endpoints; surfaces bind the shared entity, not the discriminator).
   Both are fatal for near-miss discrimination (wrong_child_set / reverse_direction),
   which depends on exactly these fields.

## 8. Failure-mode attribution summary (post-hoc diagnostics, non-gate)

- D1: attribute disagreements 146, of which 121 (82.9%) IR-attribute-verbatim-in-text.
- D2: polarity direction matrix: positive→negative 68, negative→positive 3, other 2;
  P3 ir+/truth− share 100% (59/59).
- D3: no-handle value UNMEASURABLE 63; IR value symbolic non-numeric in 63/63.
- pred_op contradictions (30) decompose into: P2 guard op written `==` instead of the
  threshold pair; P3 filter-op `!=` instead of count-op `==` (anchor drift);
  a small residue of genuine flips. Examples: `failed_examples/pred_op.jsonl`.

## 9. Stratified hand-audit sample

`stratified.jsonl` (seed 42): 56 examples = 4 per (archetype × {A01,A10,A11}) with
full coverage of all 12 buckets (pools 12–44 per bucket) + 8 instruction-side examples
(cell-free, tagged `(instruction)`). Each line carries the raw text, full IR, truth
excerpt, polarity clause, and every field score with failure mode — hand-verifiable
against the sealed source. Fields the automated join cannot cover per-example are
marked `UNMEAS`/`NA` (e.g. scope join conflicts 11 texts), stated plainly instead of
inflating a number.

## 10. Deliverables & repro

- `audit_expanded.py` (code sha `c80f481c964449bb…`, recorded in `run_receipt.json`;
  outputs byte-reproducible across runs — verified)
- `audit_expanded/field_metrics.json` — full per-field metrics, per-archetype rates,
  gate verdicts, diagnostics, corpus context
- `audit_expanded/per_sample.jsonl` — all 532 rows with per-field scores + payloads
- `audit_expanded/stratified.jsonl` — 56-example stratified review file
- `audit_expanded/failed_examples/<field>.jsonl` — every FAILED field: up to 12
  contradiction + 8 missing examples with raw texts
- repro: `cd pilot/peval/phi_d && /work1/zixuan/envs/conda_envs/causalmemagent/bin/python audit_expanded.py`

**Downstream read (for S2-rc1):** the comparator cannot be built on hard vetoes over
this extraction corpus; its design must follow §5–§6 (positive-only `pred_op` soft
evidence, ABSENT-never-veto, symbolic thresholds, branch-agnostic predicate reading,
mislocation-tolerant effects handling). The ~43%-branch-omission caveat from the prior
audit is refined to a measured 47.2% (per-archetype table above), and roles-unknown is
confirmed at 35.3% all-slots / 39.0% required-slots.
