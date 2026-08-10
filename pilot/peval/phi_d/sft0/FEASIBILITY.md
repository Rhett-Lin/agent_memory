# SFT-extractor data pipeline (φ+d lane C, step 0) — feasibility verification

**Verdict: YES — unlimited (text → gold IR) minting is feasible with the current generator
via a deterministic renderer-alignment mechanism (proven end-to-end on 20 pairs, 355/355
self-consistency checks pass). One dimension is PARTIAL: the renderer does not natively
record per-clause text spans, so evidence offsets are recovered by verified exact-match
alignment instead of being emitted at render time. The smallest generator addition that
closes this natively is specified below (~1.5–2.5 eng-days); it is NOT required to start
minting. SFT data minting can start this week.**

Method: read-only inspection of `pilot/generate_families.py`, `pilot/program_dsl.py`,
`pilot/peval/phi_d/SPEC.md`, `out/guided/faithfulness_audit.json`, `out/extractions_v2.jsonl`;
a regeneration probe proving byte-equality with the sealed artifacts; and the mint20
prototype in this directory. No generator edits, no GPU, no model runs, no labels into any
model prompt.

---

## (a) Does the renderer retain per-clause/sentence provenance?

**Instructions: no provenance retained; spans must be recovered post-hoc.** Each
`build_*` function composes the instruction as one flat f-string and returns only the
final string — see `finish_instance` (generate_families.py:208-219) which stores
`instruction` with no slot/offset record, and e.g. the crm_escalate rule construction at
:384-386 interpolated into 3 style wrappers at :387-400. However, every interpolated slot
(entity mention, rule clause, cmp phrase, theta phrase, conseq/alt, verify cue) is a
deterministic function of `program_params` + `meta` + `(near_miss, style)`, and the 3
instruction styles per schema are assigned by a fixed rotation (`(fam_idx+sib)%3` at
:1704; near-miss style `fam_idx%3` at :1708) — so every clause string is re-derivable
exactly and then located by exact substring alignment.

**Memory cards: provenance implicitly retained, recoverable bit-for-bit.** Cards are
rendered from a STRUCTURED intermediate — the `roles` dict {goal, preconds, steps,
postconds, guards} (e.g. `p1_roles`, :236-266) — through 6 pure join/numbering templates
(`CARD_STYLES`, :1384-1434). Every roles element appears verbatim in the rendered text.
The roles dict is NOT persisted to sealed artifacts (the memories row keeps only `text`
and `embed_core`, :1822-1828; `tasks_sealed` rows likewise lack it, :1959-1967), but it is
regenerable deterministically (same seed streams) — verified by byte-equality below.
`pad_to_tokens` (:1601-1613) appends task-neutral filler lines (`"\nNote: " + FILLERS`,
:1542-1562) that carry NO program content: evidence must be cut at the first `"\nNote: "`
(the mint enforces this; HEADER_LINE :1370 is likewise boilerplate).

**Latent structure that rendering flattens:** `program_dsl.py` carries the partial order
(`depends_on` per step, e.g. P1 :76-102) and commutation (P2's two reads/writes unordered,
:144-151; P3's two writes unordered, :197-204). The text renders one linear order;
explicit commutation is only labelable where the TEXT states it ("either order" in P2
cards :550, P3 cards :793) — z alone cannot justify `commutes_with` otherwise.

**Regeneration proof (the foundation everything stands on):** re-running the frozen code
path (`plan_families` → `build_instances_for_family` → `CARD_STYLES` + `pad_to_tokens`
with sealed config) reproduces sealed artifacts byte-for-byte: instructions 5/5
(tasks_sealed, seed 0), cards 6/6 incl. tokenizer-dependent padding (memories_sealed by
`opaque_id`), A10 partners recomputed (0→1, 17→24). In the full mint run this grew to
**20/20 byte-equal texts**.

## (b) Per-IR-field feasibility map (z + renderer → target)

| IR field | mechanically from z+renderer? | textual-support check needed |
|---|---|---|
| roles: status (present/absent) | yes — fixed skeleton per archetype (+join_depth for `policy_row`) | absent-vs-unknown: corpus texts are complete procedures ⇒ non-applicable roles are ABSENT by construction |
| roles: surface | yes | **card surfaces are entity-GENERIC** ("the customer", not "Lena Lindqvist") — projection must take the generic phrase from the roles dict, not the concrete entity from z |
| roles: evidence | recoverable (exact alignment, see (c)) | offset must land in core region (pre-`"\nNote: "`) |
| nodes: op sequence | yes — signature expansion (pre-registered in faithfulness_audit.py header): READ/READ+POLICY→read ×1/2, AGG→aggregate, CHECK→branch, BRANCHWRITE→absorbed into branch effects, WRITE/WRITEx2/ARCHIVE/DELx2→write ×n, VERIFY→verify | per-KIND decision: J2 instruction texts do NOT state a policy lookup step (only a pointer) ⇒ no policy-read node; J2 cards DO state it ("Find the applicable…"). Documented projection rule |
| nodes: depends_on | yes — rendered (numbered) order | DSL partial order is latent; linear-in-text convention used |
| nodes: commutes_with | only where text states "either order" (P2/P3 write/read pairs) | phrase-presence check; P2 membership predicate {>=,<=} is composite (two guards in one check) — needs a per-archetype rule |
| branch predicate: attribute, op | yes — per-schema cmp phrase table (above→`>`, at or below→`<=`; near-miss flips come from `program_params.cond_op`) | locate phrase inside the condition clause |
| branch predicate: value | **the critical projection** — see (d) | **yes**: numeric only if `str(theta)` occurs in the CONDITION CLAUSE (bidirectionally asserted), else symbolic reference as rendered |
| branch predicate: polarity | mostly mechanical per renderer template, but… | must run the negation-cue rule on the rendered clause (P3 cards/instructions are negated: "If no subtask … is still open" → negative; same rule the audit pre-registered, faithfulness_audit.py:60-70) |
| then/else effects | yes — conseq/alt vocab; effect values are quoted in text ("'escalated'") | span per effect group |
| termination | yes — read-back/confirm cue per style (3 instruction styles) / final card step | span |
| ABSENT / UNKNOWN / absent-with-evidence | absent = omitted-by-archetype (verifiable); **absent-with-evidence** where text explicitly states an omission: P4 near-miss "No archival copy is required for this request." (:1106) | z alone cannot decide UNKNOWN; in this generator genuine textual ambiguity outside theta never occurs, so UNKNOWN appears in gold only as… never (statuses are present/absent; the value field carries the symbolic load) |
| boilerplate (HEADER_LINE, fillers, style scaffolding) | never labeled | core-region cut (see (c)) |

**Bottom line for (b): every IR field has a mechanical target from z + renderer mode;
exactly three places need a check on the rendered text that z alone cannot decide —
(1) numeric-vs-symbolic predicate value, (2) polarity (negation phrasing), (3) evidence
span offsets. All three are implemented in `mint_spec.py` with hard assertions.**

## (c) Evidence spans: emit vs recover — is post-hoc alignment safe?

The renderer cannot emit spans today (see (a)); they are recovered by exact substring
alignment. It is deterministic and safe under the mint's discipline:

1. Clause expectations are the exact strings the renderer interpolates (mirrored per
   schema/kind/style/join_depth/near_miss in `mint_spec.py::p1_vocab`/`expected_rule`)
   and are HARD-ASSERTED verbatim — any renderer drift raises `MintError`, it cannot
   silently mislabel (this fired twice during prototyping and was fixed by re-reading
   the renderer, exactly the intended behavior).
2. Every evidence span is located with an anchor (search starts inside the condition
   clause), must start before the filler region (`text.find("\nNote: ")` for cards),
   and is capped at SPEC's ≤15 words with a verbatim head-clip.
3. An independent re-verification pass re-slices `text[start:end] == span` for all
   offsets: **235/235 pass** in mint20 (355 checks total = 120 per-pair + 235 span checks).
4. Cards additionally inherit positional provenance from the roles dict (step k ↔ IR
   node), with content assertions at each position (`startswith` checks).

So: spans come from *renderer alignment*, not invention — the mechanism knows every
substring it looks for because the renderer put it there. Native renderer-emitted spans
would remove the alignment code (~40% of the mint) but add nothing the verification
doesn't already guarantee.

**Smallest generator addition that closes provenance natively (OPTIONAL, not on the
critical path):** let each `build_*` return `instruction_segments` (list of
{slot_name, text}) beside `instruction`, and have the 6 `CARD_STYLES` render from the
roles dict through a span-tracking join that emits {roles_path → (start,end)}; assert
byte-identity of the concatenated text against the current sealed artifacts
(800 tasks + 800 memories) so the S0 freeze is untouched. ~8 builders × 3 styles + 6 card
templates: **1.5–2.5 eng-days** including the byte-identity regression proof.

## (d) Symbolic-value (hidden theta) policy — implemented in mint_spec.py

Modes the renderer produces today (verified against code + sealed texts):

- **J1 instruction (numeric):** theta printed in the condition clause ("... is above 5,
  ..."). Label: `value = str(theta)`, status present, evidence = cmp+number span. Guard:
  assert `str(theta)` ∈ condition clause. (5/20 minted pairs.)
- **J2 instruction (policy indirection):** "the overstock limit for category 'hardware'
  in the inv_policies table (column overstock_limit)". Number NEVER in text. Label:
  `value = "overstock_limit"` (policy column, verbatim in text), status present,
  evidence = the pointer span. Guard: assert `str(theta)` ∉ condition clause. (5/20.)
  This matches the audit's faithful classification (faithfulness_audit.json
  `pred_value_textually_indirect`, e.g. rows scoring `value: "escalate_threshold"` as
  text-faithful).
- **Memory cards (J1+J2, both):** theta_phrase is "complaint threshold stated in the
  request" / "escalation threshold from the sla_policies table" — again no number, so
  `value` = the as-stated reference (J2: the policy column; J1: the threshold phrase),
  status present. Guard: assert `str(theta)` ∉ the If-sentence (scoped: card texts
  contain digits in "Step 5:" numbering, so whole-text checks would false-positive).
  (10/10 minted cards.)

Resulting mix in mint20: 5 numeric / 15 symbolic, and 0 numeric leaks — enforced by
assertion, per-pair, in both directions (stated ⇔ numeric). The adjudication's rule
"hidden values stay SYMBOLIC when text doesn't state them" is therefore the DEFAULT code
path, and any future renderer variant that prints the number in cards would flip the
label automatically (the check is on the text, not on a hardcoded mode).

## (e) UNMEASURABLE fraction on the current 640-pair corpus vs the audited 12/372

Measured read-only this session (scripts over pairs.jsonl + sealed artifacts):
- 73/372 unique memory texts join to >1 sealed source row — **matches the audit amendment
  (73) exactly** (entity-generic cards needing no filler padding collide across A11/A10/A00).
- **12/372 have conflicting scalar P1 theta across sources — reproduces the audit's 12
  exactly** (e.g. one overstock card text maps to θ ∈ {38, 75, 77}).
- Broadening to all numeric parameters adds 24 more conflicting texts (ALL
  two_row_transfer cards: `cap_b` is per-sibling state for cal_move), i.e. 36/372 = 9.7%
  with cross-source numeric ambiguity.
- Symbolic-value share under policy (d) (single-source texts included): P1+P2 cards
  137/372 = 36.8% of memory texts; J2 instructions 20/160 = 12.5%; combined
  **157/532 = 29.5%** of corpus texts get a "numeric UNMEASURABLE → symbolic" mark.
  None get `value.status = unknown`: every symbolic case still NAMES the quantity
  (pointer phrase), so it is present-symbolic, not unknown.
- **The audit's 12/372 join-conflict is fully dissolved by this pipeline:** it existed
  only because auditing joined text → z through ambiguous sealed rows. The mint goes
  z → text → IR in one deterministic pass and never writes the numeric theta into
  symbolic labels, so identical texts receive identical gold IRs — no conflict can arise.

## Mint20 prototype result (`mint_spec.py` → `mint20.jsonl`, `mint20_report.json`)

- 20 pairs: families 0 (crm_escalate J1, numeric θ=5) + 17 (inv_overstock J2, θ=38
  policy-indirect) × {4 sibling instructions + 1 near-miss instruction} + {A11×2, A01×2,
  A10×1 cards per family}; 12 correct-program + 2 cross-domain-correct + 6 near-miss.
- **355/355 checks pass**: 20/20 byte-equality vs sealed; 20/20 `validate_ir`; op
  sequence vs signature expansion (per-kind policy-read rule); gold op == program
  cond_op including near-miss flips (`op<=` on all 6 near-miss pairs); policy_row
  presence ⇔ J2; value policy per (d); 235/235 evidence re-slice.
- sha256 `ff87563a…0eaee`, byte-identical across re-runs; styles covered: instruction styles 0/1/2; card styles
  terse_note, runbook_bullets, training_qa, postmortem, checklist, formal_sop.
- Spot inspection (instr:f17:s0, mem:f0:s0:A01): symbolic value + pointer evidence
  correct; near-miss predicate `<=` correct; filler/`Note:` lines carry no evidence.

## Residual risks / honesty notes

1. **Shortcut risk in the CURRENT renderer:** all P1/P2 memory cards are symbolic-valued
   and all J1 instructions numeric — a model could learn kind⇒value-mode instead of
   reading text. Production mint SHOULD add a card variant that prints the number (new
   renderer mode — a lever that needs building, see DATA_SPEC.md).
2. Prototype covers 1/4 archetypes (2/8 schemas). P2 (composite guard predicate,
   op-set {>=,<=}), P3 (aggregate node, negative polarity, audit_sink role, two-writes
   commutation), P4 (absent-with-evidence archive node in near-miss) are designed but
   not yet coded — the mechanism is identical (clause tables + roles positional maps).
3. Sham (Q) cards describe non-DB procedures: not mappable into the op algebra; excluded
   from minting (or labeled all-roles-absent/unknown) — decision deferred to comparator.
4. The minted gold uses the audit's BRANCHWRITE-absorbed node convention (effects inside
   the branch node) rather than the SPEC format example's separate write node; consistent
   with the faithfulness audit's pre-registered expectation — flag for S2 freeze to keep
   gold and comparator on one convention.
