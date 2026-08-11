# S2_RC2_SPEC — S2-rc2 comparator, frozen rule text (φ+d line, post-round-3 candidate)

**Status: RELEASE CANDIDATE 2 — FROZEN BEFORE ANY 640-PAIR EXECUTION, behind the
Codex round-3 ruling.** rc1 (`pilot/peval/phi_d/s2/`, rc1_hash
`96901e3dfc8346073dfc936ec27a795bde6cfa6fababdd93918a2dfd1184c416`) is
**permanently locked for evidence**: no rc1 file is edited by anything in
`s2_rc2/`; rc2 reads rc1 only as a hash-pinned import (certificate, value marks).
Every rule below is frozen text; any change is rc3 business with a new hash.

## 0. Estimator contract (controlling definition; every rule serves this)

The estimand is the registered P-relation of `pilot/program_dsl.py` (hash-pinned
in `freeze_rc2.json` as the estimand contract):

> Two tasks are "program match" (P=1) iff they share the same abstract signature —
> **the same abstract step set with the same partial order, operator polarity and
> write-target roles** — regardless of surface entities, wording or business-domain
> rendering. **Concrete thresholds / entity values are instance parameters**, not
> part of the equivalence class.

Operational reading for the comparator (contract C-0):

- **REGISTERED (may decide match/contradict):**
  1. the abstract step **multiset** (per present non-finish node: op; for writes
     the action; for checks the branch placement; multiplicity counts);
  2. **write-target roles** α-renamed onto the canonical six
     (`subject_row, policy_row, source, destination, child_set, audit_sink`);
  3. the **partial order** over the step set (depends_on reachability quotiented
     by explicit `commutes_with` independence);
  4. **operator polarity where registered** — the comparison operator (IR
     `predicate.op`, complementation-normalized per the adjudicated truth table),
     NOT the IR `polarity` field; corresponding DSL-registered anchors: P1
     `cond_op`, P2 `class_tag` transfer orientation, P3 `check.op`, P4 ordering
     class (`archive_then_delete` vs `delete_only`);
  5. the aggregate's child-set **scope** where a canonical representation can be
     honestly registered (§8.5); required scope must match or abstain.
- **NOT REGISTERED (inefficacious for the verdict — note-only diagnostics):**
  concrete threshold literals, entity/surface strings, predicate attribute
  phrases, predicate `polarity` field, effect literal values, aggregate function
  (`other`/explicit both), finish nodes and op-count incidentals. None of these
  may veto and none may license a match.
- **Benign supersession is NOT P-match.** Amendment A: any extra op (even a
  non-mutating read/verify/report) under complete(memory) is a signature
  mismatch. A lenient "compatible-with" label would be a separate compatibility
  verdict label; this comparator ships the three-verdict P-estimand only and
  therefore does not emit it (§13, open O-2).

Three-verdict output {match, contradict, unknown}; NO continuous score; verdict
aggregation is non-compensatory in contradiction.

## 1. Authority and rc1 relationship

1. Codex round-3 ruling: NO_GO-unlock on rc1; mandatory amendments A–G (restated
   and specialized below); R1–R9 dispositions (§2). The adjudicated truth table
   (thread 019fe66c) remains base law where the ruling does not amend it: 7-clause
   completeness certificate, complementation equivalence
   (`{>↔<=, >=↔<, ==↔!=}` + effect swap = equivalent; complement without swap =
   contradiction), non-compensatory contradiction, ABSENT-on-memory only under
   complete(memory), UNMEAS ≠ mismatch, three-verdict no-score.
2. SFT-era measurement status (unchanged): extraction 532/532 valid,
   both-side-JOINT 1.000 on all 640 pairs (full denominator, zero eligibility
   loss); veto-eligibility audit informs which channels may contradict
   (pred_op/branch_effects/direction/archive_capture/roles_required/termination
   HARD per audit; predicate value/attribute/polarity remain diagnostic under the
   estimand regardless of their audit eligibility — the estimand dominates).
3. Frozen imports (read-only, hash-pinned): `common.validate_ir` + role
   vocabulary; `audit_expanded.toks` (attribute diagnostic tokenizer);
   `comparator_v0` mechanics (norm_text, resolve_role, write_action,
   agg_function, branch_pred, pred_populated, branch_effects, OP_COMPLEMENT,
   action-class constants, direction/termination scaffolding);
   **rc1 `s2_comparator.certificate` + `value_mark`/`_first_number`** (the 7-clause
   certificate is reused bit-for-bit — R8 sustained).

## 2. R1–R9 dispositions (implemented exactly; fixtures pin each)

| rc1 ruling | rc2 disposition |
|---|---|
| R1 anchor gate (unknown on misalignment) | attribute = **text diagnostic only** (note + probe, dual-tokcov channels recorded); never vetoes, **never licenses match**; ambiguous multi-branch structure → unknown (§8.6 R5) |
| R2 polarity metadata-only | sustained (note-only) |
| R3 scope note-only non-gating | **void**: scope mismatch/unresolved ⇒ **unknown** (never match, never contradiction-without-audit); F25 precedent void (§8.5, fixture M5) |
| R4 threshold marks → UNMEAS/hard | literals **note-only**: no contradiction, no match-blocking; marks computed for the trace only |
| R5 halt-on-unaligned-anchor | halt ONLY when structural correspondence itself is ambiguous (§8.6: >1 present branch per side); never on attribute |
| R6 agg-function hard veto | mismatch ⇒ **unknown at most** (unaudited channel); no hard veto |
| R7 effect values strict | compare effect **action / target role / multiplicity / branch placement** only; literal values never compared |
| R8 certificate clause split | sustained; rc1 certificate reused verbatim |
| R9 target conflict hard | conflict only when both targets resolve and differ, and only **after** the maximum bijection was attempted (§6) |

## 3. Input contract and output record

`compare(ir_i, text_i, ir_m, text_m, require_branch=True) -> verdict record`, same
schema hygiene as rc1 (`phi_ir/v0` on both sides; texts used ONLY for evidence
verbatim checks and the attribute diagnostic probe). No labels, no sealed truth,
no pair metadata. Deterministic: no randomness/clock/IO inside compare; all
iteration over fixed orders; the matching algorithm's tie-break is deterministic
by construction (§6.3).

Output: `{"verdict", "reasons": [{component, code, level, detail, probe?}],
"components": {per-component max-severity rollup}, "matching": {bijection dump},
"certificates", "rule_version": "s2-rc2"}`. Levels: `contradict | unknown |
benign | note`; only the first two gate the verdict.

## 4. Completeness certificate (R8 sustained; C invariant)

`certificate` = rc1's 7 clauses, reused verbatim:
valid / required_fields / evidence_nonempty / evidence_verbatim /
no_unknown_in_used_fields / branch_populated (under require_branch) / connected.

**C invariant (amendment C): an incomplete certificate on EITHER side makes
`match` unreachable.** The comparator records
`CERT_INCOMPLETE:{instruction|memory}` at unknown level whenever a side is
incomplete, so the abstention is trace-visible.

## 5. Abstract step signature (contract C-0.1)

Per side, from present nodes (`finish` excluded — DSL bookkeeping only, never a
signature element):

- step kind: `read | list | aggregate | branch | write | verify`;
- write steps key on `(write, action)` with action class unresolved if action
  null/`other`;
- branch steps key on `branch` (the CHECK; arm payloads compared in §8.3);
- target role: `resolve_role(args.target, side_roles)`; unresolved ⇒ the node's
  target-role is `None` (NOT an empty string; never silently coerced);
- roles with status `present` are requirements of the instruction side;
  termination is a requirement when present on the instruction side.

## 6. Structural matching (amendment B; replaces rc1 greedy pairing)

### 6.1 Compatibility graph

Bipartite graph between instruction steps U and memory steps V; edge (u,v) iff:

- same op; AND
- for writes: actions equal, OR either action unresolved (None/`other`) — action
  mismatch of two resolved actions is disqualifying; AND
- for read/list/verify/write: target roles **not** (both resolved AND different)
  (R9: conflict requires both-resolved-unequal, and only matters after the max
  bijection is attempted); AND
- aggregates pair by op alone (scope is NOT a matching poison: scope is §8.5's
  abstain channel, never a signature veto; fn is R6's unknown-only channel);
- branches pair with branches.

### 6.2 Full/maximum bijection first

   K = maximum cardinality matching (Kuhn augmenting paths, deterministic
ordered iteration). Then the lexicographic-preferred maximum matching M:
iterate U in fixed node-id order; for each candidate v ∈ V in preference order
(role-exact pairs before role-unresolved pairs, then node-id order) fix (u,v)
iff the remaining graph can still attain K. Any target conflict, any extra/missing
verdict is emitted ONLY from/after this M — never from first-fit order.

### 6.3 Tie-break discipline

Semantic compatibility is maximized FIRST (= cardinality K, then maximal
role-exact placements via candidate preference); only then the id-lexicographic
tie-break. Node LIST ORDER has zero influence (metamorphic fixture M1 pins
invariance); node IDs are semantics-free tie-breakers only.

### 6.4 Outcomes of the bijection

- full bijection (|U| == |V| == |M|): proceed to per-node channels and §7 closure.
- unpaired instruction nodes: `REQ_TARGET_UNRESOLVED:{op}` (unknown) if the
  instruction node's own target-role does not resolve; else
  `REQ_OP_MISSING_UNDER_COMPLETE:{op}` (contradiction) under complete(memory),
  else `REQ_OP_MISSING_INCOMPLETE:{op}` (unknown). Same ABSENT doctrine as
  adjudication.
- unpaired memory nodes: extras policy §8.7 (incl. the control-branch rule).
- unresolved-action write that DID pair: `WRITE_ACTION_UNRESOLVED` (unknown) —
  the step-class identity cannot be certified.

## 7. Partial-order closure comparison (contract C-0.3; amendment B)

Runs only when a full bijection exists. Let R_i, R_m be depends_on reachability
over mapped present non-finish nodes (transitive closure, each side's own graph).
For every ordered pair (a,b) of mapped instruction steps: constraint holds iff
R(a,b) AND NOT commuted(a,b), where commuted(a,b) = b ∈ a.commutes_with OR
a ∈ b.commutes_with, recalled per side with that side's own flags. Compare:

- instruction-constrained pair with no memory constraint ⇒ `ORDER_EDGE_MISSING`;
- memory-constrained pair with no instruction constraint ⇒ `ORDER_EDGE_EXTRA`;
- both at level **contradict under complete(memory)**, else **unknown**
  (memory's structural claims are untrustworthy without its certificate);
- full closure equality ⇒ note `ORDER_CLOSURE_ALIGNED`. Commuting/independent
  operations are honored exactly by the commutation quotient (fixture M2).

## 8. Component channels

### 8.1 roles (roles_required)

As adjudicated: required role present/memory-present ⇒ note; present/absent under
complete(memory) ⇒ contradiction `ROLE_OMITTED_UNDER_COMPLETE:{r}`; under
incomplete memory ⇒ unknown; memory role status unknown ⇒ unknown; extra memory
role ⇒ benign note. Surfaces never compared (α-renaming).

### 8.2 unresolved required target (C invariant)

Paired node whose INSTRUCTION-side target-role is unresolved ⇒
`REQ_TARGET_UNRESOLVED:{op}` (unknown); whose memory-side target-role is
unresolved ⇒ `TARGET_UNRESOLVED_MEMORY:{op}` (unknown). Both-resolved-equal ⇒
note. Both-resolved-unequal cannot occur post-§6 (the edge would not exist).
Fixture M7: an unresolved target blocks match even on identical structure.

### 8.3 predicate / branch channel (operator registered; attributes diagnostic)

Runs when each side has exactly one present branch and the branches are paired.
If either side has >1 present branches ⇒ `STRUCT_AMBIGUOUS_BRANCH` (unknown;
the R5 halt — structural correspondence itself ambiguous) and the channel halts.
Attribute misalignment NEVER halts.

Per matched branch pair (both predicates fully populated, else
`PRED_{INSTRUCTION|MEMORY}_UNPOPULATED` unknown + halt):

1. `ATTR_PROBE` (note; dual-tokcov decision probe recorded; R1 — diagnostic only).
2. `POLARITY_ALIGNED`/`POLARITY_DIVERGENT` (note; R2).
3. **Operator mapping** with the P2 projection carve-out (amendment C):
   - `oi == om` ⇒ direct arm mapping, note `OP_ALIGNED:branch`;
   - `complement(oi) == om` (distinct) ⇒ swapped arm mapping, note
     `PRED_COMPLEMENT_SWAP_EQUIV`;
   - **transfer-shaped** (source or destination role present on either side) AND
     `{oi, om} ⊆ {">=", "<="}` AND `oi != om` ⇒ `P2_PROJECTION_UNRESOLVED`
     (unknown) + halt: both are faithful single-guard projections of the
     registered composite transfer guard (audit_expanded.py header: P2
     truth op SET = {">=","<="}); comparing them as whole guards is a false
     contradiction (fixture M8);
   - otherwise ⇒ `PRED_OP_MISMATCH` (contradiction) + halt.
4. **Branch-arm effects (R7)**: per mapped arm pair compare the multiset of
   `(action-normalized, target-role-or-None)` — action classes, target roles,
   multiplicity, and placement (arm identity under the operator mapping) — NEVER
   literal values. Any unequal arm multiset ⇒ `FX_ARM_MISMATCH` (contradiction,
   observed on both-sides-present payloads; non-compensatory). All equal ⇒
   `FX_ALIGNED` note. Instruction both arms empty ⇒ `EFFECTS_INSTRUCTION_EMPTY`
   note (degenerate; unreachable for match since require_branch completeness
   fails anyway).
5. **Threshold literals (R4)**: `VALUE_NOTE` (note) with the rc1 marks probe
   (NUMERIC/LITERAL/SYMBOLIC, first numbers, normalized equality). Never gates,
   in either direction.

### 8.4 aggregate function (R6) and aggregate steps

Paired aggregates: both fn explicit and different ⇒ `AGG_FN_MISMATCH` (**unknown**
— unaudited channel, unknown at most); explicit on exactly one side ⇒
`AGG_FN_UNRESOLVED` (unknown); otherwise `AGG_FN_ALIGNED` note.

### 8.5 scope (amendment D; F25 precedent void)

Canonical scope representation per aggregate step (registered honestly where the
IR carries it): `(over-role-resolved, filter-signature)` where filter-signature =
normalized string equality or token-set equality of `args.value`.

- over roles both resolved, equal ⇒ aligned-part; both resolved, different ⇒
  `SCOPE_OVER_MISMATCH` (unknown); either unresolved ⇒
  `SCOPE_OVER_UNRESOLVED` (unknown);
- filter strings both non-empty, equal under either equality ⇒ aligned-part;
  both non-empty, different ⇒ `SCOPE_FILTER_MISMATCH` (unknown); either empty ⇒
  `SCOPE_FILTER_UNRESOLVED` (unknown);
- all parts aligned ⇒ `SCOPE_ALIGNED` note.

Scope never contradicts (no audit-eligible cross-side measurement exists) and
**never goes silent**: every required scope must match or abstain — any scope
unknown blocks match. No surrogate signals (predicate operators, fn choices, or
other correlated features are banned as scope surrogates — D fingerprint clause).

### 8.6 direction where registered (P2 class_tag)

v0 mechanics under hard eligibility: transfer orientation resolvable on both
sides and reversed ⇒ `SRC_DEST_REVERSAL` (contradiction); inc/dec-role
opposition ⇒ `SRC_DEST_REVERSAL_INCDEC`; aligned ⇒ note; unresolvable ⇒ silent.
(The estimand registers transfer orientation; the IR polarity field does not
feed this channel.)

### 8.7 extras policy (amendment A: NO benign supersession in P-match)

Unpaired memory nodes, by kind:

- **control branch** (extra `branch`): `EXTRA_CONTROL_BRANCH` (**unknown**)
  unless proven *observationally empty* (no effectful action in either arm)
  AND *disconnected from required effects* (no mapped step transitively depends
  on it). Only then does the general extra-op rule apply:
  `EXTRA_OP_UNDER_COMPLETE:branch` contradiction / `EXTRA_OP_INCOMPLETE:branch`
  unknown. Functional or connected extra branches abstain even under complete
  memory (their semantic reach is undecidable).
- any other unpaired node (read/list/verify/write/report — **including the
  non-mutating class of rc1's "benign extras"**): `EXTRA_OP_UNDER_COMPLETE:{op}`
  (**contradiction**) under complete(memory); `EXTRA_OP_INCOMPLETE:{op}`
  (unknown) otherwise. Amendment A: under a certificate-complete memory, ANY
  surplus step is a signature mismatch of the P-estimand.

### 8.8 archive ordering, subject-bound (amendment C; augments §7)

For each instruction delete-step d with a **subject-bound capture** (a
capture-ish step — write action ∈ {archive, insert, report} or aggregate — whose
resolved target role equals d's, reaching d in R_i):

- delete unpaired ⇒ skipped (§6.4 already classified);
- mapped delete M(d) has a subject-bound capture reaching it in R_m ⇒
  `ORDER_CAPTURE_BOUND_OK` note;
- mapped delete has a subject-bound capture only FOLLOWING it ⇒
  `ORDER_CAPTURE_AFTER_DELETE` contradiction under complete(memory), else
  unknown — the binding is to the RELEVANT subject deletion (not the first
  delete in list order, not an arbitrary aggregate/report — rc1's un-bound
  variant);
- mapped delete has no subject-bound capture anywhere ⇒
  `ORDER_NO_BOUND_CAPTURE` unknown (the ordering requirement is unverifiable;
  not a fabricated contradiction). §7 closure usually catches the same fact
  structurally; this channel pins the subject binding semantically (fixture M9
  two-delete).

### 8.9 termination

v0 mechanics under hard eligibility: explicit halt/negation marker on exactly
one side ⇒ `TERM_INCOMPATIBLE` contradiction; instruction-present termination
absent under complete(memory) ⇒ `TERM_ABSENT_UNDER_COMPLETE` contradiction;
absent under incomplete memory ⇒ `TERM_ABSENT_INCOMPLETE` unknown; memory
termination status unknown ⇒ `TERM_MEMORY_UNKNOWN` unknown; extra memory-side
termination ⇒ benign note; else `TERM_ALIGNED` note.

## 9. Abstention invariants (amendment C, normative summary)

1. incomplete certificate either side ⇒ never match (`CERT_INCOMPLETE:*`);
2. unresolved required target ⇒ unknown (`REQ_TARGET_UNRESOLVED:*`);
3. extra control branch ⇒ unknown unless proven observationally empty AND
   disconnected from required effects (§8.7);
4. unresolved scope ⇒ unknown (§8.5); unresolved agg fn ⇒ unknown (§8.4);
5. P2 single-guard projection asymmetry ⇒ unknown, never contradiction (§8.3);
6. ABSENT on memory ⇒ contradiction ONLY under complete(memory); else unknown;
7. IR invalid either side ⇒ unknown (`IR_INVALID`); vacuous requirement set ⇒
   unknown (`VACUOUS_INSTRUCTION`, `VACUOUS_MEMORY`).

## 10. Verdict aggregation

`contradict` iff any contradiction-level reason fires (non-compensatory); else
`unknown` iff any unknown-level reason fires (including `CERT_INCOMPLETE:*`);
else `match` — every registered component compared, aligned, and both
certificates complete. UNMEAS/literal/attribute/polarity/agg-fn channels never
contradict; R4 literals never gate at all.

**Contradiction catalog (complete):** `ROLE_OMITTED_UNDER_COMPLETE:*`,
`REQ_OP_MISSING_UNDER_COMPLETE:*`, `EXTRA_OP_UNDER_COMPLETE:*`,
`ORDER_EDGE_MISSING`, `ORDER_EDGE_EXTRA`, `ORDER_CAPTURE_AFTER_DELETE`,
`PRED_OP_MISMATCH`, `FX_ARM_MISMATCH`, `SRC_DEST_REVERSAL`,
`SRC_DEST_REVERSAL_INCDEC`, `TERM_INCOMPATIBLE`, `TERM_ABSENT_UNDER_COMPLETE`.
**Abstain catalog (complete):** `IR_INVALID`, `VACUOUS_INSTRUCTION`,
`VACUOUS_MEMORY`, `CERT_INCOMPLETE:*`, `ROLE_OMITTED_INCOMPLETE:*`,
`ROLE_MEMORY_STATUS_UNKNOWN:*`, `REQ_TARGET_UNRESOLVED:*`,
`TARGET_UNRESOLVED_MEMORY:*`, `WRITE_ACTION_UNRESOLVED`,
`REQ_OP_MISSING_INCOMPLETE:*`, `EXTRA_OP_INCOMPLETE:*`,
`EXTRA_CONTROL_BRANCH`, `STRUCT_AMBIGUOUS_BRANCH`,
`PRED_INSTRUCTION_UNPOPULATED`, `PRED_MEMORY_UNPOPULATED`,
`P2_PROJECTION_UNRESOLVED`, `AGG_FN_MISMATCH`, `AGG_FN_UNRESOLVED`,
`SCOPE_OVER_MISMATCH`, `SCOPE_OVER_UNRESOLVED`, `SCOPE_FILTER_MISMATCH`,
`SCOPE_FILTER_UNRESOLVED`, `ORDER_NO_BOUND_CAPTURE`, `TERM_MEMORY_UNKNOWN`,
`TERM_ABSENT_INCOMPLETE`, plus order levels when memory incomplete.

## 11. rc1 defect → rc2 rule fix table (the ruling's charge sheet)

| rc1 defect (round-3 finding) | rc2 fix | rule |
|---|---|---|
| concrete thresholds fired contradictions (VALUE_LITERAL_MISMATCH) against the estimand | literals demoted to trace notes; numeric/literal/symbolic marks are diagnostic only | R4, §8.3.5, fixtures R7val/M4 |
| dual-tokcov acted as a match LICENSE (aligned anchor gated value compare) and as a near-veto | attribute reduced to a probe; verdict never reads it | R1, §8.3.1, fixtures A1/A2 |
| greedy first-fit pairing could emit spurious target conflicts / miss the full bijection | compatibility graph + maximum-cardinality lexicographic bijection, conflicts only after from it | B, §6, fixture B2 |
| "benign extras" (extra read/verify/report) left P-match reachable under complete memory | ANY surplus step under complete(memory) = signature mismatch; benign supersession pushed to a (not shipped) separate label | A, §8.7, fixture A3 |
| scope differences went note-only and MATCHED (F25 precedent) | scope must match or abstain: mismatch/unresolved ⇒ unknown, never match, no surrogates | D, §8.5, fixture M5 |
| rc1 ordering read the FIRST delete and any capture-ish placement | capture bound to the RELEVANT subject deletion (role-bound), two-delete aware | C, §8.8, fixture M9 |
| partial order never compared as a relation (only ad-hoc capture rule) | transitive-closure comparison after mapping, commutation-quotiented | B, §7, fixtures M2/M3 |
| incomplete certificates could still reach match | never-match invariant, trace-visible | C, §4/§9, fixture M6 |
| agg fn hard veto without audit | unknown at most | R6, §8.4, fixture R6agg |
| predicate evaluation halted on anchor misalignment | halt only on structural ambiguity (multi-branch); channel never reads attributes | R5, §8.3 |
| P2 projection pair {>=,<=} could false-contradict whole guards | projection abstention | C, §8.3.3, fixture M8 |

## 12. Determinism and hygiene

stdlib only; CPU only; no randomness/clock/IO in compare; matching is a fixed
lexicographic advance over ordered ids after semantic maximization; all set
operations enter only membership/equality tests or sorted dumps. The comparator
never reads P/cell/family/archetype/domain or rollout data. All imports are
hash-pinned (common, audit_expanded, comparator_v0, rc1 s2_comparator for the
certificate/value marks, plus program_dsl as the estimand CONTRACT — referenced,
not executed).

## 13. Open items for the narrow diff review (Codex round-4, pre-unlock)

- **O-1 (P2 abstention width).** The projection carve-out fires only for
  transfer-shaped pairs with BOTH ops inside the registered projection SET
  {">=","<="}. Out-of-set asymmetries (e.g. ">" vs ">=") still contradict under
  §8.3.3. Reviewer asks: (a) accept width; (b) widen to all transfer-shaped
  operator asymmetries → unknown; (c) drop polarity/operator from transfer
  signature entirely. Fixture M8 pins (a).
- **O-2 (compatibility label).** Amendment A contemplates permissive supersession
  as a SEPARATE verdict label; rc2 deliberately ships the strict three-verdict
  P-estimand and classifies every surplus-under-complete as mismatch. If the
  venue wants the lenient label, it arrives as rc3 with its own estimand
  statement; it must NOT be folded into this verdict space.
- **O-3 (scope equality bar).** §8.5's filter equality = normalized-string OR
  token-set equality (the only honestly-registered canonical form without a
  sealed anchor). Stricter (string-only) or looser (token-overlap) variants move
  pairs between unknown and note; none can produce contradiction. Fixture R13
  pins equality semantics.
- **O-4 (unresolved-target coverage).** C's "unresolved required target"
  applies to read/list/verify/write args.target. Effect-arm targets are covered
  by the arm multiset's None-role equality (R9-analog: unresolved never
  conflicts). Should arm-level unresolved targets also force unknown? Currently
  note-level; flagged.
- **O-5 (empty-arm instruction branch).** both-arms-empty instruction branch
  skips arm comparison with a note; unreachable for `match` under
  require_branch completeness, and fires no contradiction. Confirm that is the
  intended neutrality (vs an explicit unknown).
- **O-6 (commutation sampling).** the closure quotient reads each side's OWN
  commutes_with flags; if commutation is asserted on one side only, the pair
  compares per the missing side ⇒ ORDER_EDGE asymmetry (contradict/unknown per
  completeness). Fixture M2 covers mutual flags; the one-sided case is pinned
  in M2b — confirm the asymmetry behavior.
- **O-7 (multi-branch).** any side carrying >1 present branch ⇒
  STRUCT_AMBIGUOUS_BRANCH unknown (corpus is single-branch by audit). If
  multi-branch correspondence is wanted, it needs an explicit matching rule in
  rc3; attribute probes are banned from disambiguating (R1).
- **O-8 (policy gate τ and top-k).** the score harness fixes top-k = {1,2,4}
  and the frozen mapping "first match in sim_embed order (tie: sim_tf, then
  memory_id), else N fallback"; any τ>0 variant for sim/P̂ baselines imports
  gate_eval.py's frozen thresholds. Confirm before unlock.

## 14. Fixture inventory (test_s2_rc2.py; ≥30 pinned, all synthetic non-benchmark)

Metamorphic (amendment F): M1 node-list permutation invariance (match + a
contradiction case); M1b shuffled on both sides; M2 independent-op permutation
via mutual commutes_with ⇒ match; M2b one-sided commutation ⇒ ORDER_EDGE
asymmetry; M3 partial-order violation ⇒ ORDER_EDGE_* contradict; M4
entity/threshold/effect-literal α-renaming ⇒ match; M5 scope mismatch ⇒ unknown
(≠ match, F25 void); M6 incomplete certificate (either side) ⇒ never match; M7
unresolved required target ⇒ unknown; M8 P2 projection {">=","<="} ⇒
P2_PROJECTION_UNRESOLVED, not contradiction; M9 P4 two-delete capture ordering
(capture-after-subject-delete ⇒ contradict; capture bound only to children ⇒
contradict; correct subject binding ⇒ match); M10 extra control branch:
functional ⇒ unknown, empty+disconnected under complete ⇒ contradict, under
incomplete ⇒ unknown.

Regression/delta pins: VAL1 threshold 5-vs-6 ⇒ MATCH (estimand correction);
R7eff arm literal mismatch ⇒ MATCH; arm action mismatch ⇒ contradict; arm
multiplicity mismatch ⇒ contradict; arm placement swap without op complement ⇒
contradict; complement+swap ⇒ match; op non-complement ⇒ contradict; A3
extra READ under complete ⇒ contradict (rc1-benign killed); under incomplete ⇒
unknown; extra report-write under complete ⇒ contradict; EXTRAv extra effectful
write ⇒ contradict; B2 bijection preference (role-exact over first-fit) ⇒ match;
R6agg fn mismatch ⇒ unknown; scope aligned ⇒ match; direction reversal ⇒
contradict; ABSENT role/op under complete ⇒ contradict, under incomplete ⇒
unknown; termination halt split ⇒ contradict; polarity divergent ⇒ match (R2);
vacuity guards ⇒ unknown; invalid IR (either/both) ⇒ unknown; VALUE asymmetry
⇒ note-only still match-eligible; ATTR probe emitted with dual-tokcov channels
(accept + cross + unfaithful recorded, verdict unaffected); kitchen-sink
match-complete (equivalent programs under full structural noise) ⇒ match.

## 15. Scoring contract — the adjudicated five-gate battery (amendment E)

Implemented in score_s2_rc2.py, FROZEN OFF until final adjudication (§16).
Verdict score only for AUC ranking: fixed survey mapping {match: 1.0,
unknown: 0.5, contradict: 0.0}; the decision gate uses 1[verdict=match] with
full denominators (no ternary mean). All AUCs rank-based with ties; every pair
in every denominator (full-640 policy). Terminology: "per-registered-archetype
macro" (deterministic comparator; nothing trains).

- **G1 macro gate**: arch-macro S=1 AUC = mean over the four registered
  archetypes of per-archetype S=1 AUC; Δ vs P̂-v1's held-out score computed from
  `peval/pair_scores.jsonl::phat_oof_family` (the GroupKFold-family-40 protocol
  published in `P_EVAL_RESULTS.json` schemes.groupkfold_family_40; consistency
  print against that document). Pass: Δ ≥ +0.10 AND family-cluster bootstrap
  (resample family_idx clusters, seed fixed, B=5000) LB(Δ) > 0.
- **G2 catastrophe gate**: every archetype S=1 AUC > 0.50 AND min ≥ 0.60.
- **G3 decision gate**: match admission = mean 1[verdict=match] per cell with
  full denominators: A00/A01 ≤ 0.10; A10/A11 ≥ 0.50; overall and per-archetype.
- **G4 cross-surface gate**: S=0 AUC + A10 match retention reported (A10 ≥ 0.50
  re-asserted under the S=0 lens).
- **G5 policy gate**: deployment simulation on the existing 7B/3B rollouts
  (`/work1/zixuan/outputs/agent_memory/pilot/rollouts_{model}_shard*-of-*.jsonl`,
  schema per `peval/gate_eval.py`): candidate store = the 4 A-cell memories of a
  (family, sibling); comparator policy = **first candidate whose verdict is
  match in sim_embed order** (tie-break sim_tf desc, memory_id asc) for
  top-k ∈ {1, 2, 4}; abstain ⇒ N-arm. Baselines: never, always, sim, P̂
  (frozen thresholds from gate_eval), judge, oracle. Family-cluster bootstrap:
  superiority over sim (LB > 0) AND noninferiority to oracle at −5pp
  (LB(success_comparator − success_oracle) > −0.05). No new rollouts.
- **Judge comparisons**: paired-bootstrap on pair-aligned cells: ΔA01 safety
  UB < 0; ΔA10/A11 retention LB > 0; per-registered-archetype macro AUC diff —
  comparator vs frozen judge (`phi_d/out/judgments.jsonl`).

## 16. Freeze and harness lock (amendment G)

`freeze_rc2.json` pins sha256 of every rc2 artifact, the spec text, every import
dependency (incl. `pilot/program_dsl.py` as estimand contract), the rc1
integrity re-verification (rc1 files re-hashed against `s2/freeze_rc1.json`),
and the composite rc2 hash. score_s2_rc2.py refuses ANY 640/corpus execution
while `RULE_VERSION == "s2-rc2"` (same one-shot discipline as rc1: unlock
happens only after the diff review closes §13 and a FINAL hash is issued).
Synthetic fixtures are the only executed evaluation at rc2.
