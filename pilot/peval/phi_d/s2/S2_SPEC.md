# S2_SPEC — S2-rc1 comparator, frozen rule text (φ+d line)

**Status: RELEASE CANDIDATE 1 — FROZEN BEFORE ANY 640-PAIR EXECUTION.** Rules below
are the entirety of what the rc1 comparator implements. Any change after this freeze
is rc2 business and requires a new freeze hash plus re-adjudication.

**Authority (in precedence order):**

1. Adjudicated truth table (Codex thread 019fe66c rounds), as restated in the rc1
   tasking: completeness certificate (valid IR + fields present + evidence nonempty
   + evidence verbatim + no unknown-in-used-fields + branch predicates/effects
   populated + subgraph connected from an evidenced root op to an evidenced
   verify/finish or supported termination); predicate as canonical decision function
   (aligned attribute anchor + normalized operator + branch effects; complementation
   `{>↔<=, >=↔<, ==↔!=}` + effect swap = equivalent; complement without swap =
   contradiction); non-compensatory contradiction; three-verdict
   {match, contradict, unknown}; NO continuous score; match requires every
   task-required component comparable+matching; any unresolved required component →
   unknown; ABSENT on memory = contradiction only with complete(memory), else
   unknown; extra effectful ops contradiction; benign extras = non-mutating
   read/verify/report.
2. SFT-era veto eligibility (S2_PREP_REPORT §6 + `sft2_eval/audit_sft_canonical.json`):
   10/11 HARD VETO (pred_op, pred_value, pred_polarity, branch_effects, direction,
   archive_capture, roles_required, termination, pred_attribute, pred_all) with the
   **dual-tokcov** attribute anchor (sealed-anchor ∩ OR all IR-attribute tokens ⊆
   text tokens; fallback dual-verbatim); `scope` **permanently excluded** (documented
   `agg:open` FK-anchor artifact, 53 rows, plus 21 paraphrase contradictions); UNMEAS
   never counts as mismatch; full-640 denominator (zero extraction-side eligibility
   loss: all 640 pairs both-valid + both-side-JOINT 1.000).
3. comparator_v0 legal baseline (`pilot/peval/phi_d/comparator_v0/comparator.py`):
   structural mechanics (resolve_role α-renaming, certificate shape, effect pairing,
   greedy node pairing, ordering/direction/termination scaffolding) reused read-only.
   Its DEMOTE-era audit demotions are NOT inherited — eligibility changed with SFT.

**Discipline invariant:** the comparator NEVER reads P/cell/family/archetype/domain
labels, sealed truth, or pair metadata. Inputs are exactly two IRs and two source
texts. Determinism: no randomness, no time, no network, no I/O inside `compare`;
iteration order is file order everywhere; greedy matchings are first-fit in node
order.

---

## 1. Input contract

```
compare(ir_i, text_i, ir_m, text_m, require_branch=True) -> verdict record
```

- `ir_i`, `ir_m`: objects in the frozen `phi_ir/v0` schema (`common.py`:
  `validate_ir`, `IR_GUIDE_SCHEMA`). Wrapper discipline exactly as validated there:
  roles = canonical 6 × `{status, surface, evidence}`; nodes carry
  `{id, op, status, evidence, args, depends_on, commutes_with}`; branch args carry
  `predicate = {attribute, op, value, polarity}` of F-wrappers
  `{status, value, evidence}` plus `then_effects` / `else_effects` lists of
  `{action, target, value}`.
- `text_i`, `text_m`: the raw source strings the IRs were extracted from (used ONLY
  for evidence-verbatim certificate clauses and for the attribute-anchor token
  coverage tests; never for content inference).
- For the 640-pair stage (post-round-3 only): join `pairs.jsonl` rows to
  `sft2_eval/canonical_sft.jsonl` IRs by `instruction:<sha256(text)[:16]>` /
  `memory:<sha256(text)[:16]>` (the extraction worklist keys). rc1 ships NO 640 run.

Output record (machine-readable, deterministic):

```
{"verdict": "match"|"contradict"|"unknown",
 "reasons": [{"component", "code", "level", "detail"}, ...],   # append order = eval order
 "components": {name: {"level", "codes", ...}},                # per-component rollup
 "certificates": {"instruction": cert, "memory": cert},
 "rule_version": "s2-rc1"}
```

Reason levels: `contradict` | `unknown` | `benign` | `note`. Only `contradict` and
`unknown` gate the verdict (§11). `benign` and `note` are trace-only.

---

## 2. Normalization primitives (all reused verbatim or frozen copies)

- `norm_text(s)` (v0): lowercase, de-quote possessives, non-alnum→space, squeeze.
- `norm_value(s)` (v0): literal normalization — strip quote/backtick edges,
  case/whitespace-insensitive; numerics canonicalized via `"%g" % float(t)` when
  parseable.
- `toks(s)` (audit_expanded, frozen): lowercase `[a-z0-9]+` tokens, trailing `s`
  stripped for tokens longer than 3 chars (`"seats"→"seat"`, `"status"→"statu"`).
  Imported read-only from `audit_expanded.py` — the exact tokenizer the dual-tokcov
  audit used; no reimplementation drift.
- `resolve_role(target, roles)` (v0): free-form target → canonical role via the
  side's own role surfaces (α-renaming); `None` if unresolvable.
- `anchors`: see §7. Operator complement table (frozen):
  `>↔<=, >=↔<, ==↔!=` (each its own inverse pair).

Action classes (frozen from v0):
- EFFECTFUL write actions: `{set, insert, delete, move, archive, notify}`.
- BENIGN write actions: `{report}` (non-mutating).
- NONMUTATING ops: `{read, list, verify}` (extra instances are benign).
- CAPTURE actions (writes that can carry a capture): `{archive, insert, report}`.
- Explicit aggregate functions: `{count, sum, min, max, avg, exists}`
  (`other`/null = not explicit).

---

## 3. Completeness certificate — exact clauses (7)

`certificate(ir, text, require_branch=True)` returns `{checks, stats, complete}`.
`complete` = AND of the clauses below. ABSENT on a side is a trustworthy active
omission only under `complete == True` of that side's certificate.

1. **valid** — `common.validate_ir(ir)` passes (schema `phi_ir/v0`, enums, arg
   discipline, unique ids, acyclic `depends_on`).
2. **required_fields** — top keys `{schema, roles, nodes, termination}` present and
   `nodes` non-empty.
3. **evidence_nonempty** — every present-status evidence slot (present roles,
   present nodes, present predicate subfields of present branch nodes, present
   termination) carries a non-empty evidence string.
4. **evidence_verbatim** — every non-empty evidence string on a present-status slot
   is a verbatim substring of the side's source text (whitespace-squeezed on both
   sides, case-sensitive, contiguous).
5. **no_unknown_in_used_fields** — zero `unknown` status among roles, nodes,
   predicate subfields of present branch nodes, and termination.
6. **branch_populated** (only when `require_branch=True`; otherwise clause absent
   and conjunctively neutral) — every present branch node has all four predicate
   subfields present-status AND non-empty `then_effects` AND non-empty
   `else_effects`.
7. **connected** — at least one present node exists, AND (an evidenced root op — a
   present node with no present-side dependencies and non-empty evidence — reaches,
   following `depends_on` edges forward, an evidenced `verify` or `finish` node)
   OR (termination is present with non-empty verbatim evidence = "supported
   termination").

Short-circuit: if clause 1 fails, `complete=False` and later clauses are not
asserted. All clause booleans and stats (evidence slot counts, unknown counts,
connectivity internals) are emitted in the verdict record.

---

## 4. SFT-era eligibility table (frozen for rc1)

| field | rc1 status | consequence |
|---|---|---|
| pred_op | HARD VETO | operator mismatch beyond complementation ⇒ contradiction |
| pred_value | HARD VETO | decidable threshold mismatch under aligned anchor ⇒ contradiction |
| pred_polarity | **metadata (note-only)** | divergence recorded, never gates (see §14 R2) |
| branch_effects | HARD VETO | effect-mapping mismatch under licensed mapping ⇒ contradiction |
| direction | HARD VETO | src/dest reversal (P2) ⇒ contradiction |
| archive_capture | HARD VETO | capture-after-delete ⇒ contradiction |
| roles_required | HARD VETO | required role ABSENT under complete(memory) ⇒ contradiction |
| termination | HARD VETO | explicitly incompatible termination ⇒ contradiction |
| pred_attribute | **anchor gate (never veto)** | dual-tokcov alignment gates the predicate decision; non-alignment ⇒ unknown (see §14 R1) |
| pred_all | composite | folds in; no independent channel |
| scope | **EXCLUDED — note-only** | child-scope signals recorded, ZERO verdict influence (see §14 R3) |
| agg_function | HARD VETO (carried from adjudicated round-1 veto list; not an audit gate field — see §14 R6) | both-explicit function mismatch ⇒ contradiction |

UNMEAS policy (frozen): any component value classed UNMEAS (§8 marks, join-conflict
analogs) is excluded from match support AND from contradiction: it emits
`unknown`-level reasons only, never `contradict`. UNMEAS never counts as mismatch;
it abstains.

Denominator policy (frozen): every pair receives a verdict; invalid/unknown pairs
stay in every scoring denominator (the full-640 rule). rc1 involves no
extraction-side eligibility loss (audit: all 640 pairs both-valid, both-side-JOINT
1.000).

---

## 5. Task-requirement derivation (instruction side)

The instruction IR defines the requirement set; the memory IR is the candidate. A
component is *task-required* iff the instruction side asserts it:

- each instruction-present canonical role (status `present`) — required;
- each instruction-present node except `finish` (finish is bookkeeping; a missing
  finish alone is never a veto) — required;
- instruction-present termination — required;
- for each instruction-present, fully-populated branch node: predicate channel
  (anchor + operator + effects + threshold value per §6.4) — required;
- ordering constraints materialized through instruction-side capture-before-delete
  structure (§6.6) and transfer orientation (§6.5) — required when resolvable.

Instruction-side `absent`/`unknown` items are not requirements. Memory-side items
beyond the requirement set go through the extra-op policy (§10). Vacuity guards
(§8) fire before any component comparison.

## 6. Per-component comparison semantics

### 6.1 roles (component `roles`, field roles_required: HARD VETO)

For each canonical role r, with instruction status si and memory status sm:

| si | sm | outcome |
|---|---|---|
| present | present | note `ROLE_ALIGNED:r` (surfaces α-renamed; surface strings never compared) |
| present | absent | complete(memory) ⇒ **contradict** `ROLE_OMITTED_UNDER_COMPLETE:r`; else unknown `ROLE_OMITTED_INCOMPLETE:r` |
| present | unknown | unknown `ROLE_MEMORY_STATUS_UNKNOWN:r` |
| absent | present | benign `ROLE_EXTRA_MEMORY:r` |
| absent | absent | silent (aligned omission; not a requirement) |
| unknown | any | silent on this channel (certificate clause 5 handles the side) |

### 6.2 required operations (component `ops`)

Present nodes (both sides) minus `finish` are paired greedily, instruction order,
first-fit: same `op`; `write` nodes additionally pair only within action class
(effectful action exact-match, non-effectful with non-effectful). Paired-node
checks:

- `read`/`list`/`verify`: both targets role-resolved and different ⇒ **contradict**
  `TARGET_CONFLICT:<op>`; else note `OP_ALIGNED:<op>`.
- `write`: same target-conflict rule ⇒ **contradict** `TARGET_CONFLICT:write`; else
  note `OP_ALIGNED:write`.
- `aggregate`: both functions explicit and different ⇒ **contradict**
  `AGG_FN_MISMATCH`; explicit on exactly one side ⇒ unknown `AGG_FN_UNRESOLVED`;
  the `over` binding and the filter content are SCOPE — notes `SCOPE_*` only,
  never gating (§6.8).
- `branch`: the predicate canonical decision function, §6.4.

Unpaired instruction nodes (requirement present, memory ABSENT):
complete(memory) ⇒ **contradict** `REQ_OP_MISSING_UNDER_COMPLETE:<op>`; else
unknown `REQ_OP_MISSING_INCOMPLETE:<op>`.

### 6.3 ABSENT-on-memory rule (global)

An ABSENT/memory-missing signal (role, op, termination) is a **contradiction only
under complete(memory)**; otherwise it is unknown. This is the adjudicated
"ABSENT = contradiction only with complete(memory)" clause; complete is the §3
7-clause AND.

### 6.4 predicate canonical decision function (component `predicate`)

Applies per paired branch node pair. Carrier-agnostic reading stays at
branch-node args only (guided-schema filler on other ops is ignored by schema
discipline, and only branch nodes carry predicate payloads in the SFT corpus).

Precondition: both predicates fully populated (all four F-wrappers
present-status); else unknown `PRED_INSTRUCTION_UNPOPULATED` /
`PRED_MEMORY_UNPOPULATED` and the channel halts.

1. **Aligned attribute anchor (§7)**: dual-tokcov. Aligned ⇒ note
   `ATTR_ANCHOR_ALIGNED`; NOT aligned ⇒ unknown (`ATTR_ANCHOR_CROSS` when both
   sides are own-text-faithful, `ATTR_ANCHOR_UNFAITHFUL` otherwise) and the whole
   predicate channel HALTS (operator/effects/value are not licensed across
   potentially distinct parameters). The anchor never contradicts (§14 R1).
2. **Polarity**: note only — `POLARITY_ALIGNED` / `POLARITY_DIVERGENT`. Never
   gates (§14 R2).
3. **Normalized operator + branch effects** — the adjudicated equivalence rule:
   - same operator: map then↔then, else↔else;
   - memory operator = complement(instruction operator), operators distinct: map
     then↔else, else↔then (complemented decision);
   - otherwise: **contradict** `PRED_OP_MISMATCH`, halt channel.
   Both effect lists are compared as multisets of EFFECTFUL effects
   (`{action, target-role, value}`; greedy first-fit pairing; action exact; target
   conflict iff both roles resolve and differ; value conflict iff both values
   non-empty and `norm_value` unequal). Mappings fully matched ⇒ note
   `PRED_OP_EFFECTS_MATCH` (same op) or `PRED_COMPLEMENT_SWAP_EQUIV`
   (complement+swap = equivalent, per adjudication). Any mismatch ⇒ **contradict**
   `PRED_EFFECT_MISMATCH` (same op) or `PRED_COMPLEMENT_NO_SWAP`
   (complement without swap = contradiction, per adjudication); halt channel.
   Degenerate case: the instruction branch carries NO then AND NO else effects ⇒
   mapping not applicable, note `PRED_EFFECTS_INSTRUCTION_EMPTY`, channel
   continues to value.
4. **Threshold value (pred_value: HARD VETO; §8 marks)**: evaluated only after 1–3
   pass. Asymmetric presence (exactly one side empties the literal) ⇒ unknown
   `PRED_VALUE_ASYMMETRIC`. Both present: NO aligned anchor is impossible here
   (channel halted at 1 otherwise); under the aligned anchor:
   - `norm_value` equal ⇒ note `VALUE_ALIGNED`;
   - marks differ (§8) ⇒ UNMEAS, unknown `VALUE_MARK_MISMATCH_UNMEAS`;
   - both NUMERIC, first numbers differ ⇒ **contradict**
     `VALUE_LITERAL_MISMATCH`; equal ⇒ note `VALUE_ALIGNED`;
   - both LITERAL (quote-wrapped) and unequal ⇒ **contradict**
     `VALUE_LITERAL_MISMATCH`;
   - both SYMBOLIC and unequal ⇒ UNMEAS, unknown `VALUE_SYMBOLIC_UNMEAS`.
   Without an aligned anchor (channel halted at 1), no literal comparison ever
   happens — the threshold-no-anchor abstention is realized as
   `ATTR_ANCHOR_*` unknown. (Fixture F11 pins: equal literals still cannot rescue
   a cross-anchor predicate.)

Contradiction inside this channel is NON-COMPENSATORY: no amount of agreement
elsewhere cancels it.

### 6.5 direction (P2; component `direction`, field direction: HARD VETO)

Active only when the instruction side is a transfer task (≥1 of roles
source/destination present on the instruction side). Orientation per side =
first resolvable move-pattern (`move ... from X to Y`) endpoint roles, or
increment/decrement role keywords on writes targeting source/destination.
Endpoints resolved on both sides and reversed (src↔dest) ⇒ **contradict**
`SRC_DEST_REVERSAL`; inc/dec roles opposite across sides ⇒ **contradict**
`SRC_DEST_REVERSAL_INCDEC`; aligned ⇒ note `DIRECTION_ALIGNED`; unresolvable on
either side ⇒ silent (no requirement decidable).

### 6.6 ordering: archive / capture-before-delete (component `ordering`, field archive_capture: HARD VETO)

Constraint activation: the instruction side has a delete-write for which a
capture-ish node (aggregate, or write with action ∈ {archive, insert, report})
transitively precedes the delete (plain read/list/verify do NOT capture — a
read-then-delete preserves nothing).

- constraint active, memory has no delete-write ⇒ unknown
  `ORDER_DELETE_MISSING_IN_MEMORY` (the missing delete itself is independently
  handled by §6.2);
- memory delete exists with a capture-ish node preceding it ⇒ note
  `ORDER_CAPTURE_BEFORE_DELETE_OK`;
- memory delete exists, no preceding capture-ish node, and a
  read/list/aggregate/verify/capture-write succeeds the delete ⇒ **contradict**
  `ORDER_CAPTURE_AFTER_DELETE`;
- memory delete exists with no capture-ish node anywhere ⇒ unknown
  `ORDER_NO_CAPTURE_IN_MEMORY`.

### 6.7 termination (component `termination`, field termination: HARD VETO)

| instruction | memory | outcome |
|---|---|---|
| not present | present | benign `TERM_EXTRA_MEMORY` |
| not present | not present | silent |
| present | unknown | unknown `TERM_MEMORY_UNKNOWN` |
| present | absent | complete(memory) ⇒ **contradict** `TERM_ABSENT_UNDER_COMPLETE`; else unknown `TERM_ABSENT_INCOMPLETE` |
| present | present | halt/negation marker (`stop|abort|halt|do not proceed|leave untouched|without updat/writ/sav/apply/chang/modif…`) on exactly one side ⇒ **contradict** `TERM_INCOMPATIBLE`; else note `TERM_ALIGNED` |

### 6.8 scope (component `scope`, field scope: EXCLUDED — note-only)

Anything about the aggregate's child-set selection — the `over` role binding and
the filter content (`args.value` on aggregate nodes) — is recorded as notes
(`SCOPE_OVER_NOTE`, `SCOPE_FILTER_NOTE`, `SCOPE_MISMATCH_NOTE` when the two sides'
resolved over-roles differ) at level `note`. It has ZERO influence on the verdict
in either direction (§14 R3).

---

## 7. Dual-tokcov attribute anchor (pred_attribute channel — the frozen SFT-era rule)

Let `ai`, `am` = the two predicate attribute strings, `ti = toks(ai)`,
`tm = toks(am)`, and `Xi = toks(text_i)`, `Xm = toks(text_m)` (full source texts).

- **cross-anchor ∩** (the comparator-side analogue of the audit's sealed-anchor
  agreement): `cross_anchor = (ti ∩ tm ≠ ∅)` — the two extractions share at least
  one anchor content token.
- **cross-text token coverage** (the comparator-side analogue of "all IR-attribute
  tokens ⊆ text tokens"): `cross_text = (ti ≠ ∅ ∧ ti ⊆ Xm) ∨ (tm ≠ ∅ ∧ tm ⊆ Xi)`
  — one side's attribute phrase is fully token-covered by the OTHER side's text
  (either direction; absorbs non-contiguous paraphrases, e.g. the audit's
  12-row `"stock level" ← "stock table" + "minimum keep level"` class).

**dual-tokcov (rc1 PRIMARY):** `aligned_tokcov = cross_anchor ∨ cross_text`.

**dual-verbatim (rc1 recorded FALLBACK, diagnostic only):**
`aligned_verbatim = cross_anchor ∨ (ai non-empty ∧ ai.strip().lower() ∈ text_m.lower())
∨ (am non-empty ∧ am.strip().lower() ∈ text_i.lower())`.
Contiguous verbatim implies token coverage, so `aligned_verbatim ⇒ aligned_tokcov`;
tokcov is the superset. The fallback is what adjudication adopts if it prefers the
stricter contiguous-evidence reading; rc1 computes and traces both flags but
GATES on dual-tokcov only.

**Side faithfulness:** `faith_i = (ti ≠ ∅ ∧ ti ⊆ Xi)`, `faith_m` likewise
(each side's attribute tokens ⊆ its OWN text tokens — the audit's own-text tokcov
faithfulness test, 1.000 on the canonical 532).

**Channel outcomes (§6.4 step 1):**
`aligned_tokcov` ⇒ note `ATTR_ANCHOR_ALIGNED` (detail records which channels
fired: cross_anchor / cross_text / verbatim / faith flags). Not aligned ⇒
unknown `ATTR_ANCHOR_CROSS` if `faith_i ∧ faith_m` (both anchors tethered to own
text; surfaces decisively disjoint but never a veto at rc1 — §14 R1), else
unknown `ATTR_ANCHOR_UNFAITHFUL` (an untethered attribute phrase cannot be
trusted to distinguish parameters).

## 8. Threshold value decidability marks (SPEC/IR notion)

Mark of a literal string `v` (after edge-whitespace strip):

- **NUMERIC** — `v` contains a digit AND a first number parses via
  `-?\d+(\.\d+)?`; comparison quantity = that first number as float.
- **LITERAL** — `v` is fully quote-wrapped (`'…'` or `"…"`); comparison quantity =
  `norm_value(v)` (quote/case/space-insensitive).
- **SYMBOLIC** — everything else (symbolic policy/threshold references such as
  "the minimum keep level", "none remain"; the audit's value-as-stated class).

Decidability (frozen): NUMERIC-both and LITERAL-both are DECIDABLE (mismatch
contradicts under an aligned anchor; the NUMERIC channel compares first numbers,
so a digit-string that fails first-number parse degrades to SYMBOLIC).
SYMBOLIC-anything is UNDECIDABLE comparator-side ⇒ UNMEAS (unknown): rc1 does NOT
apply the audit's truth-side concept handles (ZERO_SET/ONE_SET/MIN_KEEP/CAP) —
those need a sealed anchor the comparator lacks; see §14 R4. UNMEAS never counts
as mismatch (abstains); identical surfaces (`norm_value` equal) are a note-only
alignment regardless of marks; a bare-value asymmetry is unknown
(`PRED_VALUE_ASYMMETRIC`).

## 9. Vacuity and validity (component `ir`)

Evaluated before all other components, in this order; the first firing rule
returns immediately with verdict `unknown`:

1. either IR invalid (certificate clause 1) ⇒ `IR_INVALID` (unknown);
2. instruction vacuous (zero present non-finish nodes AND zero present roles AND
   termination not present) ⇒ `VACUOUS_INSTRUCTION` (unknown);
3. memory has zero present nodes ⇒ `VACUOUS_MEMORY` (unknown).

## 10. Extra-op policy (component `extras`)

Unpaired memory nodes:

- `write` with EFFECTFUL action ⇒ **contradict** `EXTRA_EFFECTFUL_OP:write:<action>`;
- `write` action `report` ⇒ benign `EXTRA_BENIGN:write:report`;
- `write` with unresolved action class (`other`/null) ⇒ unknown
  `EXTRA_OP_UNCLASSIFIED:write`;
- `branch` whose effects contain any EFFECTFUL action ⇒ **contradict**
  `EXTRA_EFFECTFUL_OP:branch`; else benign `EXTRA_BENIGN:branch`;
- any other op (`read`, `list`, `verify`) ⇒ benign `EXTRA_BENIGN:<op>`.

Benign extras are precisely the non-mutating read/verify/report class of the
adjudicated table. Extra memory-side ROLES are benign (`ROLE_EXTRA_MEMORY`,
§6.1) and extra memory-side termination is benign (`TERM_EXTRA_MEMORY`, §6.7).

## 11. Verdict aggregation, abstain catalog, non-compensation

Let `L` = the multiset of reason levels.

- any `contradict` ∈ L ⇒ verdict **contradict** (non-compensatory: no other
  component cancels it);
- else any `unknown` ∈ L ⇒ verdict **unknown** (every unresolved task-required
  component abstains the pair; UNMEAS contributes here);
- else ⇒ verdict **match** (every task-required component was comparable and
  matched; only notes/benigns fired).

There is NO continuous score at comparator level; the scoring stage maps
{match:1.0, unknown:0.5, contradict:0.0} exactly as v0 (SPEC.md §6) and keeps
every pair in every denominator.

**Abstain (unknown-level) reason catalog (complete at rc1):**
`IR_INVALID`, `VACUOUS_INSTRUCTION`, `VACUOUS_MEMORY`,
`ROLE_OMITTED_INCOMPLETE:*`, `ROLE_MEMORY_STATUS_UNKNOWN:*`,
`REQ_OP_MISSING_INCOMPLETE:*`, `EXTRA_OP_UNCLASSIFIED:write`,
`PRED_INSTRUCTION_UNPOPULATED`, `PRED_MEMORY_UNPOPULATED`,
`ATTR_ANCHOR_CROSS`, `ATTR_ANCHOR_UNFAITHFUL`,
`PRED_VALUE_ASYMMETRIC`, `VALUE_MARK_MISMATCH_UNMEAS`, `VALUE_SYMBOLIC_UNMEAS`,
`AGG_FN_UNRESOLVED`,
`ORDER_DELETE_MISSING_IN_MEMORY`, `ORDER_NO_CAPTURE_IN_MEMORY`,
`TERM_MEMORY_UNKNOWN`, `TERM_ABSENT_INCOMPLETE`.

**Contradiction catalog (complete at rc1):**
`ROLE_OMITTED_UNDER_COMPLETE:*`, `REQ_OP_MISSING_UNDER_COMPLETE:*`,
`TARGET_CONFLICT:*`, `AGG_FN_MISMATCH`,
`PRED_OP_MISMATCH`, `PRED_EFFECT_MISMATCH`, `PRED_COMPLEMENT_NO_SWAP`,
`VALUE_LITERAL_MISMATCH`,
`EXTRA_EFFECTFUL_OP:write:*`, `EXTRA_EFFECTFUL_OP:branch`,
`SRC_DEST_REVERSAL`, `SRC_DEST_REVERSAL_INCDEC`,
`ORDER_CAPTURE_AFTER_DELETE`,
`TERM_ABSENT_UNDER_COMPLETE`, `TERM_INCOMPATIBLE`.

## 12. Modify-vs-abstain matrix (component × signal ⇒ outcome)

| component | decisive mismatch signal | unresolved signal | benign class |
|---|---|---|---|
| roles | required role absent + complete(mem) ⇒ contra | absent + ¬complete; mem status unknown | extra mem role |
| ops (required) | required op absent + complete(mem) ⇒ contra | absent + ¬complete | — |
| ops (paired target) | role-resolved target conflict ⇒ contra | — | — |
| aggregate fn | both explicit, differ ⇒ contra | exactly one explicit ⇒ unknown | scope notes: no signal |
| predicate anchor | none at rc1 (gate only) | not aligned ⇒ unknown (+halt) | aligned ⇒ note |
| predicate polarity | none | none | divergence ⇒ note |
| operator | non-complement mismatch ⇒ contra | — | — |
| branch effects | mapping mismatch ⇒ contra | instr effects empty ⇒ note | — |
| threshold value | decidable marks + differ ⇒ contra | UNMEAS marks; asymmetric presence | aligned/equal ⇒ note |
| direction | src/dest reversal ⇒ contra | orientation unresolvable ⇒ silent | aligned ⇒ note |
| ordering | capture-after-delete ⇒ contra | delete missing; no capture node | capture-first ⇒ note |
| termination | absent + complete(mem) ⇒ contra; halt-marker split ⇒ contra | absent + ¬complete; mem unknown | extra mem termination |
| extras | effectful extra ⇒ contra | unclassified extra write ⇒ unknown | read/list/verify/report, benign branch |
| scope | none | none | all signals ⇒ note |

---

## 13. Determinism and hygiene guarantees

- stdlib only; CPU only; no randomness, no clock, no I/O inside `compare`.
- Every matching is greedy first-fit in IR node order; iteration follows Python
  list order of the IR files; set operations enter only membership tests whose
  boolean result is order-free (toks sets).
- The comparator reads ONLY the two IRs and the two texts. P/cell/family/
  archetype/domain labels, sealed truth, and pair metadata never enter the
  module (asserted by code review; the module has no path handles to them).
- Reused read-only: `common.validate_ir` + role vocabulary; `audit_expanded.toks`
  (frozen tokenizer); comparator_v0 mechanics (`resolve_role`, certificate shape,
  effect pairing, node pairing, ordering/direction/termination scaffolding).
  Dependencies are hash-pinned in `freeze_rc1.json`.

## 14. rc1 rulings on adjudication-open items (the Codex round-3 ambiguity list)

The adjudicated table + SFT audit left the following open; rc1 rules them as
below, conservatively (false-contradiction avoidance dominates lost veto power;
each ruling is pinned by fixtures F-numbers in test_s2.py). Round-3 reviewers:
these are THE decision points.

- **R1 — attribute anchor never vetoes.** The audit's pred_attribute HARD-VETO
  status sanctions trusting the extraction, but the comparator's cross-side
  question ("same parameter?") is not the audited question ("faithful read of
  THIS row?"): the 125-row sealed-anchor artifact class is exactly cross-anchor
  divergence on same-parameter rows, and the comparator has no sealed anchor to
  break ties. rc1: non-alignment ⇒ unknown + channel halt, never contradiction.
  Candidate rc2 resolutions: (a) keep; (b) harden to contradiction under
  faith_i ∧ faith_m (two engineers can read §7 and apply it deterministically —
  pinned variant fixture F4b records the would-be verdict); (c) window-anchored
  cross-text rule.
- **R2 — polarity is metadata.** The adjudicated decision function lists
  anchor+operator+effects only; SPEC's polarity TODO-FREEZE was never closed;
  folding polarity into operator complementation would misfire on the
  pre-registered E1 clause-reanchoring artifact (ir-positive/truth-negative).
  rc1: `POLARITY_DIVERGENT` is a note; verdict-neutral. If round 3 wants polarity
  inside the decision function, an exact negation-normalization rule must be
  written first.
- **R3 — scope is note-only EXCLUDED.** v0's "excluded→demote-to-unknown" would
  still let scope block match; rc1 strengthens to zero verdict influence
  (component list: "child-scope EXCLUDED"), matching "permanently excluded" in
  the audit. Both the over-binding and the filter content are covered.
- **R4 — no concept-set threshold normalization.** The audit's ZERO_SET/ONE_SET/
  MIN_KEEP/CAP handles are truth-side constructs; applying them symmetrically
  without an anchor risks equating "at least one" with 1. rc1: SYMBOLIC-anything
  ⇒ UNMEAS-unknown (fixtures F7, F8 pin). rc2 candidate: adopt the audit's frozen
  sets under an op-context rule, with a stated acceptance test.
- **R5 — halt-on-unaligned-anchor.** Operator/effects/value are not evaluated
  across a non-aligned anchor (they may bind different parameters). Cost: some
  true contradictions degrade to unknown. Benefit: no cross-parameter veto
  evidence. Alternatives: evaluate-but-discount (round-3 decision).
- **R6 — agg-function veto kept.** "aggregate-function mismatch when both
  explicit" is on the adjudicated round-1 veto list but is NOT an audit gate
  field (no extraction-faithfulness measurement exists). rc1 keeps it HARD per
  the older adjudication; round 3 should confirm or demote.
- **R7 — effect-value strictness.** Effect values conflict only when both
  non-empty and `norm_value`-unequal (blank values are lenient; quote/case
  tolerant). A stricter or looser (token-containment) reading changes
  branch_effects; pinned by F16/F17.
- **R8 — certificate clause split.** "evidence nonempty verbatim" is implemented
  as two clauses (nonempty ≠ verbatim; an empty span is not a verbatim failure,
  a wrong span is not a presence failure). Same AND, cleaner forensics.
- **R9 — target-conflict veto on paired ops** (read/write target role conflict)
  is carried from the adjudicated round-1 veto list ("conflicting action
  target/control dependency"); only role-RESOLVED conflicts fire.

No other interpretation points were found while implementing: every other rule
traces literally to the adjudicated table or the audit document.

## 15. Fixture inventory (rule → synthetic fixture; all non-benchmark, hand-written)

test_s2.py, fixtures F1–F28. Mapping: F1 match control; F2/F3 dual-tokcov accept
(cross-anchor / cross-text); F3b tokcov⊋verbatim separation; F4/F5 dual-tokcov
reject (faithful / unfaithful); F6 NUMERIC-NUMERIC veto; F7 NUMERIC-SYMBOLIC
UNMEAS; F8 SYMBOLIC-SYMBOLIC UNMEAS; F9 LITERAL-LITERAL veto; F10 LITERAL equal
note; F11 no-anchor equal-values abstain; F12 ABSENT under complete ⇒ contra;
F13 ABSENT under ¬complete ⇒ unknown; F14 complement+swap ⇒ match; F15
complement-no-swap ⇒ contra; F16 same-op effect mismatch ⇒ contra; F17 effect
target conflict ⇒ contra; F18 op non-complement ⇒ contra; F19 extra effectful ⇒
contra; F20 extra benign class ⇒ match-eligible; F21 direction reversal ⇒
contra; F22 capture-after-delete ⇒ contra (+ capture-first positive); F23
invalid IR(s) ⇒ unknown; F24 termination veto×2 + abstain; F25 scope note-only
non-gating ⇒ match; F26 agg-fn mismatch ⇒ contra; F27 polarity note-only ⇒
match; F28 vacuity guards; F29 kitchen-sink positive (match-complete positive
fix: complement-swap + benign extras + roles + termination ⇒ match).

## 16. Freeze

`freeze_rc1.json` pins sha256 of this spec (the spec-text hash), s2_comparator.py,
test_s2.py, score_s2.py, plus import dependencies (common.py, audit_expanded.py,
comparator_v0/comparator.py), plus the composite rc1 hash. Any bit change ⇒ new
release candidate, new hash, new adjudication. The 640-pair run happens ONLY
after Codex adversarial review round 3 closes the §14 list.
