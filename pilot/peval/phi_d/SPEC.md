# φ+d P-estimation evaluator — S0 freeze skeleton (v0)

Scope: this document freezes the **S0/S1 surface** of the φ+d pipeline per
`pilot/peval/PHI_D_EVALUATOR_PLAN.md` §8: input, extractor (model/prompt/decode/retry),
IR semantics, decomposed-judge baseline, cache keys, and the failure→abstain rule.
Everything needed only by the **comparator stage (S2+) is marked `TODO-FREEZE`** and is
deliberately NOT frozen here — no comparator rule, weight, or threshold exists yet.

The `.py` files in this directory are the executable source of truth for the two prompts;
their sha256 is recorded in every output row (`prompt_sha`). This document copies the
prompts verbatim for review; if the copies drift, the scripts + `prompt_sha` win.

## 0. Hashes / versions

| item | value |
|---|---|
| benchmark input | `pilot/peval/pairs.jsonl`, sha256 `aa33ea61935dc9c4a516bce77c0db7a6a9e0c32338e871b6c5b955a2d45b44bf` (640 rows) |
| family metadata (join-check only) | `/work1/zixuan/data/agent_memory/sealed/families.jsonl`, sha256 `75138655563614faffbab0785dbf4631132f3f424c0d1c5f6218567e88ccef89` |
| model | `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`, fp16, vLLM 0.6.6.post1, `gpu_memory_utilization=0.85`, `max_model_len=4096`, `seed=42` |
| python | `/work1/zixuan/envs/conda_envs/causalmemagent/bin/python` |
| prompt hashes | recorded per-row as `prompt_sha` in `out/extractions.jsonl` / `out/judgments.jsonl` |
| code freeze | `out/freeze_v0.sha256` holds the live sha256 of all four code files at freeze time; every output row also carries `prompt_sha` + `decode` + `guided` provenance, so a post-run file mutation cannot silently change what the numbers mean. Run history: v1 (prefill anchor) and v2-spaced (guided, default whitespace → pervasive 768-token truncation) are preserved under `out/dev_smoke/`; canonical outputs are v2-compact (`whitespace_pattern=""`). A v3c rescue variant (`maxLength`-bounded strings, re-run of the 151 still-invalid keys) hung the outlines guide builder for hours and was abandoned without touching canonical rows |
| guided FSM cache | `OUTLINES_CACHE_DIR=/work1/zixuan/cache/outlines`; one-time FSM build ~10 min per distinct schema/regex (measured), cached afterwards |

## 1. Input freeze

- **Model-input whitelist**: only `instruction` and `memory_text` may appear in any model
  prompt. `cell`, `P`, `S`, `family_idx`, `target_sibling`, `archetype`, `domain`,
  `sim_tf`, `sim_embed`, `memory_id` are **eval/join-only** and never enter a prompt.
  `archetype` is already present on every row (verified 640/640); the `families.jsonl`
  join is therefore a consistency check, not a dependency.
- Pair key: `memory_id` (unique per row, verified 640/640). Extraction key: text sha
  (160 unique instructions + 372 unique memory texts = 532 unique texts).
- Row canonical order: file order of `pairs.jsonl`.

## 2. IR JSON schema v0 (`phi_ir/v0`)

Typed program-sketch graph. Semantics of every field: **`present`** (explicitly stated;
a verbatim evidence span from the text MUST be attached), **`absent`** (a complete
procedure that genuinely omits this element — an active omission, usable as contradiction
evidence by a later comparator), **`unknown`** (ambiguous / cannot tell; abstain fuel).
ABSENT ≠ UNKNOWN is load-bearing: conflating them either misses skip-archive near-misses
or destroys coverage.

```json
{"schema": "phi_ir/v0",
 "roles": {"subject_row"| "policy_row"|"source"|"destination"|"child_set"|"audit_sink":
            {"status": "present|absent|unknown", "surface": "<verbatim entity name>|null",
             "evidence": "<verbatim span <=15 words>|null"}},
 "nodes": [{"id": "n1", "op": "read|list|aggregate|branch|write|verify|finish",
            "status": "present|absent|unknown", "evidence": "<span>|null",
            "args": {...}, "depends_on": ["n0"], "commutes_with": ["n2"]}],
 "termination": {"status": "...", "evidence": "..."}}
```

- **Canonical role vocabulary (frozen 6)**: `subject_row` (the single row the task acts
  on) / `policy_row` (row storing policy/threshold data) / `source` / `destination`
  (transfer endpoints) / `child_set` (enumerated/aggregated related rows) / `audit_sink`
  (archive/log/notification receiver). Entities are α-renamed onto this vocabulary via
  `surface`; extra entity detail stays in node args as short strings.
  `TODO-FREEZE`: whether any extra open-vocabulary roles are allowed in the comparator,
  and the exact α-renaming/alignment rule between two IRs.
- **Op algebra (frozen 7)**: `read` (single-row lookup), `list` (enumerate a set),
  `aggregate` (`function ∈ count|sum|min|max|avg|exists|other` over a set), `branch`
  (conditional policy check), `write` (`action ∈ set|insert|delete|move|notify|archive|
  report|other`), `verify` (read-back/confirm), `finish` (terminate/report).
  `TODO-FREEZE`: strict vs non-strict operator semantics, negation normalisation, and
  which op mismatches are hard contradictions vs soft.
- **Branch predicate** carries per-field wrappers `F={"status","value","evidence"}` for
  `attribute` / `op ∈ {>,>=,<,<=,==,!=}` / `value` / `polarity`:
  `polarity` is `positive`, or `negative` ONLY when the condition is stated as a negation
  ("no rows remain", "nobody has declined"). Branch effects: `then_effects`/`else_effects`
  lists of `{action,target,value}` (write-shaped).
  `TODO-FREEZE`: comparator truth table for predicate equivalence (e.g. `>5` vs `at or
  below 5` flipped branches), including how polarity enters it.
- **Dependencies**: `depends_on` = must-precede edges; validated acyclic.
  `commutes_with` = order-free siblings (independent writes / "either order").
  `TODO-FREEZE`: exact graph-equality rule (which reorderings are benign) in the comparator.
- **Termination**: how the procedure ends / what "done" means (status + evidence).
- **Hard validation** (`common.validate_ir`): enums, types, 1–16 nodes, unique ids,
  known dependency targets, acyclicity, predicate keys exactly
  {attribute,op,value,polarity}. Evidence-span **presence/verbatimness is a soft quality
  metric** (reported per field), never a validity condition.

## 3. Extraction prompt v0 (full text)

System: `You are a precise program-extraction engine. You output only valid JSON.`

User (verbatim from `extract_phi.py::EXTRACTION_PROMPT_V0`; `{TEXT}` is the only slot):

```
Extract the program sketch of the TEXT below as ONE compact JSON object and nothing else.

Required top-level keys, exactly these, in this order: "schema", "roles", "nodes", "termination".

Template to fill:
{"schema":"phi_ir/v0","roles":{"subject_row":R,"policy_row":R,"source":R,"destination":R,"child_set":R,"audit_sink":R},"nodes":[NODES],"termination":T}

Definitions:
- R = {"status":"present|absent|unknown","surface":<verbatim entity name from the text, else null>,"evidence":<verbatim quote, <=15 words, copied from the text, else null>}.
  Roles: subject_row = the single row the task acts on; policy_row = a row holding policy/threshold data; source / destination = origin / target of a transfer; child_set = the set of related rows that is listed or aggregated; audit_sink = archive/log/notification receiver.
- NODES = the procedure steps in execution order, at most 12, each:
  {"id":"n1","op":"read|list|aggregate|branch|write|verify|finish","status":"present|absent|unknown","evidence":<quote or null>,"args":{...},"depends_on":["nX"],"commutes_with":["nY"]}
  op meanings: read = look up one row; list = enumerate a set of rows; aggregate = compute count/sum/min/max/avg/exists over a set; branch = a conditional policy check; write = any state change; verify = read-back/confirm; finish = terminate/report.
  args by op:
    read/list/verify: {"target":"subject_row"}  (canonical role or short entity string)
    aggregate: {"over":"child_set","function":"count|sum|min|max|avg|exists|other"}
    write: {"action":"set|insert|delete|move|notify|archive|report|other","target":"customers.status","value":"'escalated'"}
    branch: {"predicate":{"attribute":F,"op":F,"value":F,"polarity":F},"then_effects":[E],"else_effects":[E]}
      F = {"status":"present|absent|unknown","value":"...","evidence":"..."}; predicate op value in >,>=,<,<=,==,!=;
      polarity value "positive", or "negative" ONLY when the condition is phrased as a negation ("nobody has declined");
      E = {"action":"...","target":"...","value":"..."} shaped like a write.
    finish: {}
  depends_on = ids that must run before; commutes_with = ids whose relative order is free ("either order", or different rows/fields touched).
- T = {"status":"present|absent|unknown","evidence":<quote or null>} describing what "done" means.

Status rules (critical):
- "present" = the text explicitly states it (verbatim evidence quote REQUIRED).
- "absent" = the procedure is complete AND genuinely omits this element.
- "unknown" = ambiguous or unclear. When unsure choose "unknown"; never invent content to reach "present".

Do NOT copy the TEXT into the JSON. Do NOT invent keys. Compact JSON without indentation.

FORMAT EXAMPLE (invented entities; follow its shape, not its content):
Example TEXT: "Workshop note: item GH-221 (brass hinge) is in the parts table, shelf 'north'. Rule: when the on-hand count of GH-221 is at least 15, mark reorder as 'no'; when it is below 15, mark reorder as 'yes' and quantity_due to 20. Check the shelf count first, then update, then read the row back."
Example output:
{"schema":"phi_ir/v0","roles":{"subject_row":{"status":"present","surface":"parts row GH-221","evidence":"item GH-221 (brass hinge) is in the parts table"},"policy_row":{"status":"absent","surface":null,"evidence":null},"source":{"status":"absent","surface":null,"evidence":null},"destination":{"status":"absent","surface":null,"evidence":null},"child_set":{"status":"absent","surface":null,"evidence":null},"audit_sink":{"status":"absent","surface":null,"evidence":null}},"nodes":[{"id":"n1","op":"read","status":"present","evidence":"Check the shelf count first","args":{"target":"subject_row"},"depends_on":[],"commutes_with":[]},{"id":"n2","op":"branch","status":"present","evidence":"when the on-hand count of GH-221 is at least 15","args":{"predicate":{"attribute":{"status":"present","value":"on-hand count","evidence":"on-hand count of GH-221"},"op":{"status":"present","value":">=","evidence":"at least 15"},"value":{"status":"present","value":"15","evidence":"15"},"polarity":{"status":"present","value":"positive","evidence":"at least 15"}},"then_effects":[{"action":"set","target":"reorder","value":"no"}],"else_effects":[{"action":"set","target":"reorder","value":"yes"},{"action":"set","target":"quantity_due","value":"20"}]},"depends_on":["n1"],"commutes_with":[]},{"id":"n3","op":"write","status":"present","evidence":"then update","args":{"action":"set","target":"subject_row","value":"reorder and quantity_due per branch"},"depends_on":["n2"],"commutes_with":[]},{"id":"n4","op":"verify","status":"present","evidence":"read the row back","args":{"target":"subject_row"},"depends_on":["n3"],"commutes_with":[]}],"termination":{"status":"present","evidence":"read the row back"}}

Now do the same for the real TEXT below. Output only the JSON object, nothing else.

TEXT:
<<<{TEXT}>>>
```

No benchmark examples appear anywhere in the prompt: the single FORMAT EXAMPLE uses
invented entities (part GH-221 / shelf 'north') and encodes no benchmark content
(frozen discipline per plan §8). Format anchoring is **decode-side**: guided JSON
decoding against `IR_GUIDE_SCHEMA` (§5), no assistant prefill.

**Repair prompt (one retry)**: `The JSON you emitted for the TEXT below was invalid.
Problem: {ERROR}` + re-emit instruction restating the exact top-level keys + same TEXT
(verbatim in `extract_phi.py::REPAIR_PROMPT_V0`). `{ERROR}` is a sanitized message
(parse position for syntax errors; a generic "schema/keys mismatch" for validation
errors — validator detail is never fed back, to avoid parroting).

## 4. Decomposed-judge prompt v0 (full text; plan §4 ablation baseline)

System: `You are a precise semantic-comparison engine. You output only valid JSON.`

User (verbatim from `decomposed_judge.py::JUDGE_PROMPT_V0`; slots `{INSTRUCTION}`/`{MEMORY}`; the trailing `The answer must continue directly from: ...` line shown in older copies was removed when prefill was dropped in favor of guided decoding — the .py file is canonical):

```
You are given an INSTRUCTION describing a target task and a MEMORY describing a retrieved past procedure. Judge whether the memory's procedure semantically matches the procedure the instruction asks for. Compare meaning, not surface wording: the two texts may use different entity names for the same role.

Compare these atomic aspects, and for each aspect follow its comparison rule:
- goal: what the procedure is trying to achieve, compared at role level (entity names may differ across domains).
- roles: which ROLES the entities fill (the row acted on, the policy/threshold row, the origin/destination of a move, the set being aggregated, the archive/log sink). Different entity names can fill the same role.
- branch_predicates: FIRST map each side's conditional check to (attribute role, comparator direction, outcome per branch). Comparator mapping: "above X"/"more than X"/"exceeds X" = >, "at least X" = >=, "at or below X"/"no more than X" = <=, "below X"/"fewer than X"/"under X" = <, "exactly X" = ==, "none remain"/"no X left" = zero-check. Attribute names and threshold NUMBERS may legitimately differ across domains; a different comparator DIRECTION, or a different outcome attached to the same branch, = contradict.
- transfer_direction: which role is decreased (origin) and which is increased (destination); amounts may differ; swapped origin/destination = contradict.
- aggregation_scope: exactly WHICH set of rows is listed/counted/aggregated, compared via the filter criteria (prefix, status, topic, relation); a different filter or subset = contradict.
- required_operations: whether the memory contains EVERY operation the instruction requires (lookups, policy checks, updates, archive/delete/notify steps, read-back verification). An operation required by the instruction but missing from the memory is a contradiction, not a minor difference.
- write_effects: whether the two texts' writes produce the same end state per condition (same fields, same outcome values), compared at role level.

Then output EXACTLY one JSON object (compact, no prose, no markdown fences):
{"schema":"phi_judge/v0",
 "fields":{"goal":V,"roles":V,"branch_predicates":V,"transfer_direction":V,"aggregation_scope":V,"required_operations":V,"write_effects":V},
 "verdict":"match|contradict|unknown"}
where V = {"instruction_says":"<=15 words","memory_says":"<=15 words","verdict":"match|contradict|unknown|not_applicable","note":"<=20 words"}.
For EVERY aspect: first write what each side says (short quote or tight summary; null if that side lacks the aspect), then judge. Never judge from overall impression.
- "match": the two texts agree on this aspect UNDER its comparison rule (role-level entity match counts as agreement). "contradict": they explicitly conflict under the rule (comparator direction flipped, swapped origin/destination, different aggregation filter, a required operation missing in the memory, different end state).
- "unknown": the texts are too vague or incomplete to tell. "not_applicable": this aspect appears in neither text.
- final "verdict": "contradict" if ANY applicable field contradicts; "match" only if every applicable field matches; otherwise "unknown".

Do NOT invent keys. Compact JSON without indentation.

FORMAT EXAMPLE (invented entities; follow its shape, not its content):
Example INSTRUCTION: "Workshop note: item GH-221 (brass hinge) is in the parts table, shelf 'north'. Rule: when the on-hand count of GH-221 is at least 15, mark reorder as 'no'; when it is below 15, mark reorder as 'yes' and quantity_due to 20. Check the shelf count first, then update, then read the row back."
Example MEMORY: "Retrieved experience: for parts row GH-221, rule: when the on-hand count is at least 15, mark reorder as 'yes'; otherwise mark reorder as 'no' and quantity_due to 0. Check the count, update, read the row back."
Example output:
{"schema":"phi_judge/v0","fields":{"goal":{"instruction_says":"maintain reorder fields of GH-221","memory_says":"same","verdict":"match","note":"same maintenance goal"},"roles":{"instruction_says":"parts row GH-221","memory_says":"parts row GH-221","verdict":"match","note":"same subject row"},"branch_predicates":{"instruction_says":"on-hand count at least 15 -> reorder 'no'","memory_says":"on-hand count at least 15 -> reorder 'yes'","verdict":"contradict","note":"same comparator, opposite outcome per branch"},"transfer_direction":{"instruction_says":null,"memory_says":null,"verdict":"not_applicable","note":"no transfer in either"},"aggregation_scope":{"instruction_says":null,"memory_says":null,"verdict":"not_applicable","note":"no aggregation in either"},"required_operations":{"instruction_says":"check count, update, read back","memory_says":"check, update, read back","verdict":"match","note":"same operations"},"write_effects":{"instruction_says":"reorder 'no' when >=15","memory_says":"reorder 'yes' when >=15","verdict":"contradict","note":"opposite end state under same condition"}},"verdict":"contradict"}

Now do the same for the real pair below. Output only the JSON object, nothing else.

INSTRUCTION:
<<<{INSTRUCTION}>>>
MEMORY:
<<<{MEMORY}>>>
```

The example output demonstrates the quote-then-compare discipline: each aspect quotes
both sides BEFORE judging. Format anchoring is decode-side (guided JSON against
`JUDGE_GUIDE_SCHEMA`, §5). The format example uses invented entities only (part GH-221),
no benchmark content.

Repair retry analogous (`decomposed_judge.py::REPAIR_PROMPT_V0`). Judgments are ablation
evidence only: per plan §4, judge errors MUST NOT be used to iterate the comparator.

## 5. Decoding / cache keys / retry

| stage | decoding | guided schema | cache key | output |
|---|---|---|---|---|
| extraction | `temperature=0, top_p=1, max_tokens=768, seed=42` | `common.IR_GUIDE_SCHEMA` (guided JSON, outlines backend, `whitespace_pattern=""` compact) | `{kind}:{sha256(text)[:16]}` + `prompt_sha` + model rev | `out/extractions.jsonl` (one row per unique text) |
| judge | `temperature=0, top_p=1, max_tokens=512, seed=42` | `common.JUDGE_GUIDE_SCHEMA` (guided JSON, outlines backend) | `memory_id` + `prompt_sha` + model rev | `out/judgments.jsonl` (one row per pair) |

- Format enforcement is **decode-side guided JSON** (vLLM `GuidedDecodingParams`,
  backend `outlines` — the `xgrammar` default crashes in this env; nullable fields use
  `anyOf` because this outlines version requires string `type`). `IR_GUIDE_SCHEMA` (v2)
  pins: exact top-level keys, the 6 role keys, node key discipline (id/op/status/
  evidence/args/depends_on/commutes_with), enum values for op/status/termination, and a
  typed nullable-key superset `args` (target/over/function/action/value/predicate/
  then_effects/else_effects — FSM-enforced enums for write action, aggregate function,
  predicate op & polarity values, and predicate key discipline). `validate_ir` enforces
  per-op required contents afterwards (`null` effect lists count as empty); residual
  failures get one repair retry. `JUDGE_GUIDE_SCHEMA` pins all 7 field keys with
  quote/verdict/note keys and verdict enums. No assistant prefill is used; `raw` is the
  full generated JSON text. Guide schemas live in `common.py` and are part of the freeze.

- Resume-safe: jsonl append; keys already present are skipped (failures included — a
  recorded failure is final for v0; changing that is a version bump).
- Retry policy: exactly one JSON-repair retry (same decoding); `attempts` and
  `first_pass_error` recorded. No further retries, no fallback model.

## 6. Failure → abstain rule (frozen for S0/S1 scoring)

- Extraction: invalid JSON or hard schema violation after retry ⇒ row recorded with
  `valid=false`, `error_class` ∈ {`empty_output`, `json_parse_error`,
  `schema_validation_error`} (+ `finish_reason=length` truncation noted). Failures are
  **abstain-eligible and never dropped**.
- Judge: same failure classes. For scoring vs labels (only inside `score_baselines.py`):
  fixed mapping `match→1.0, unknown→0.5, contradict→0.0`; invalid judge ⇒ `0.5`
  (abstain), kept in all 640-pair metrics. Covered-only AUC/accuracy reported
  secondarily, always alongside coverage. No threshold tuning on labels.

## 7. TODO-FREEZE (mandatory before the comparator stage — nothing here is decided)

1. **Comparator rule set**: non-compensatory veto fields, contradiction truth table,
   benign reordering/extra-safe-addition allowances, alignment + tie-breaks; each clause
   hashed before any scoring run (plan §3, §8).
2. **Equivalence relation**: α-renaming allowance beyond the 6 roles, completeness
   requirement (ABSENT-on-one-side semantics), UNKNOWN handling inside comparison.
3. **Scores & decision**: bounded score shape, weights, coverage targets, thresholds,
   top-k rerank protocol, abstain policy at admission time.
4. **Calibration**: whether to Platt-scale; inner-fold-only fitting; degenerate folds.
5. **Evaluation protocol for S3**: per-archetype macro AUC, family-cluster bootstrap
   recipe, risk–coverage curves, horror-cell (A01/A10) decision rates —冻结口径 per
   plan §5/§6, not re-litigated here.
6. **Mechanism-audit sampling rule** (A11→A01 diffs must localize to registered semantic
   fields; A10/A11 normalize to compatible program signatures).
7. **Fifth mismatch-type challenge set** construction (post-freeze transfer test).
8. Any prompt/schema change after this freeze ⇒ bump `phi_ir/v0` / `phi_judge/v0` and
   `prompt_sha`; old outputs stay as dev-version artifacts, never silently reused.

## 8. Reproducibility

```bash
cd pilot/peval/phi_d
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
export CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1
$PY extract_phi.py          # ~532 unique extractions -> out/extractions.jsonl
$PY decomposed_judge.py     # 640 pair judgments      -> out/judgments.jsonl
$PY score_baselines.py      # labels read HERE only   -> out/summary.json, out/examples.jsonl
```
