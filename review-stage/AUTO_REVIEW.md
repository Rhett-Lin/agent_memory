# AUTO_REVIEW — H-DC Deployment Section Review Loop

- **Scope**: the newly added "H-DC deployment" section of the ICLR 2027 submission (`iclr2027/sections/deployment.tex`) and its supporting artifacts (Appendix `app:hdc`, figures `fig:hdc`/`fig:hdccards`, abstract deployment sentence, raw results `pilot/dslice/HDC_RESULTS.json`, pre-registration GATE_PROTOCOL Part IV/IV-A, builder/analyzer code). NOT the whole paper.
- **Backend**: codex MCP, model `gpt-5.6-sol`, `model_reasoning_effort=xhigh`, sandbox read-only, cwd = project root.
- **Difficulty**: medium. **MAX_ROUNDS** = 4. **POSITIVE_THRESHOLD**: score >= 6/10 AND verdict in {ready, almost} (both required).
- **Fix budget**: LaTeX reframing/clarification, analysis computable from `HDC_RESULTS.json` or rollout files, figure tweaks via `pilot/dslice/fig_hdc.py`. NO new GPU rollouts / new experiments — demands for new compute are documented as out-of-scope with justification.
- **Compile gate after each fix round**: `cd iclr2027 && pdflatex -interaction=nonstopmode main.tex` ×2, exit 0, no `^!` errors, no undefined references.
- **Started**: 2026-08-08 (baseline compile: 16 pages, clean).

---

---

## Round 1 (review 2026-08-08 21:11 JST; fixes resumed + completed 2026-08-08 22:5x JST — fix round was interrupted mid-application and resumed in a later session)

### Assessment (Summary)
- Score: **4/10** (weak reject)
- Verdict: **not ready** ("READY: No")
- Key criticisms (ranked by reviewer):
  1. Deployment result contaminated by **undisclosed oracle-fallback trajectories** (188/640 cards); on authentic model-generated trajectories 7B E1 collapses to +0.041 [−0.078,+0.149]. Positive 7B deployment interpretation does not survive on authentic sources.
  2. **3B trap noninferiority misreported** — table said "pass (+0.000; n.s.)" but lower95 = −0.072 < −0.05 margin; `ttrap_noninf_ok=false`. (Does not overturn GO: GO model is 7B, both 7B guardrails pass.)
  3. Implemented policy described inaccurately (deletion ladder drops finish *result* at stage ≥3 for 269 cards etc.; "keeps every action JSON" false as stated).
  4. "Pre-registered, then amended" not supported by repo history (builder 16:59 < plan commit 17:06; rollouts began ~17:01).
  5. "Capability gate" inferred from significant-vs-null without a registered cross-model interaction; 3B E1 CI mostly compatible with harm.
  6. A6 overclaimed — cited JSON lacks token-ID no-op result / snapshot evidence; analyzer keeps only first metadata row per arm.
  7. Secondary findings presented too strongly (raw(300) "significantly negative"; mechanism sentence exceeds package-level identification).
  8. Card-audit figure: overlapping bottom annotations; stages 1–5 unexplained.
- Reviewer conclusion: section salvageable within the loop as an honest mixed-source proof-of-concept; broad deployment claim would require new compute (fallback-free re-harvest) — **out of fix budget**, flagged as blocking follow-up.

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

Score: 4/10 for a top venue.
READY: No.

The aggregate 7B arithmetic is correct, but the section currently makes one false statistical claim and substantially overstates what the experiment validates. Most seriously, the apparent benefit is highly sensitive to undisclosed oracle-fallback trajectories.

## Direct audit

What matches the artifacts:

- All displayed A10/A11 rates, E1/E2 estimates, CIs, Holm-adjusted values, rollout counts, token statistics, and escalation counts match `HDC_RESULTS.json` or the card maps after rounding.
- The analyzer implements the amended primary family correctly: E1 one-sided positive, E2 two-sided, HFR noninferiority one-sided, Holm \(m=6\) ([analyze_dslice.py:274](/work1/zixuan/projects/agent_memory/pilot/dslice/analyze_dslice.py:274)).
- The \(\tau_{\mathrm{trap}}\) sign and \(-5\)pp noninferiority margin are implemented correctly as a secondary check.
- Exact paired card-token equality is real: 640/640 pairs have \(|\Delta|=0\).

What does not match:

- The 3B \(\Delta\tau_{\mathrm{trap}}\) noninferiority claim is false. Its one-sided lower bound is \(-0.0719\), below the \(-0.05\) margin, and `ttrap_noninf_ok=false` ([HDC_RESULTS.json:181](/work1/zixuan/projects/agent_memory/pilot/dslice/HDC_RESULTS.json:181), [HDC_RESULTS.json:392](/work1/zixuan/projects/agent_memory/pilot/dslice/HDC_RESULTS.json:392)). The table nevertheless says "pass (+0.000; n.s.)" ([deployment.tex:45](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:45)). Part IV-A explicitly forbids treating nonsignificance as noninferiority.
- This error does not overturn the registered GO decision, because the GO model is 7B and both 7B guardrails pass.

## Remaining weaknesses, ranked

| Rank | Weakness | Minimum fix | Constraint status |
|---:|---|---|---|
| 1 | **The "deployment" result is contaminated by undisclosed oracle-fallback trajectories.** The builder reconstructs oracle-plan trajectories whenever harvesting failed ([build_dslice_cards.py:107](/work1/zixuan/projects/agent_memory/pilot/dslice/build_dslice_cards.py:107)). This affects 188/640 cards: A00=52, A01=49, A10=43, A11=44. An exploratory existing-file sensitivity gives 7B E1 \(=+0.041\), CI approximately \([-0.078,+0.145]\), after excluding fallback cards cell-wise, versus \(+0.424\) \([+0.250,+0.613]\) on oracle-fallback cards. On 3B, the corresponding signs also reverse: model-generated \(-0.226\), oracle \(+0.297\). Thus the positive 7B deployment interpretation does not survive on authentic model-generated source trajectories. | Disclose all fallback counts; add a family-bootstrap fallback-stratified sensitivity; reframe the result as a mixed model/oracle-source benchmark comparison. Remove claims of validated deployment on past model episodes. | **Within constraints.** Retaining the stronger authentic-deployment claim would **require new compute**: reharvest without fallback and rerun. |
| 2 | **3B trap noninferiority is misreported.** "n.s." is used as a pass despite the preregistered bound rule. | Change the table to "not established; lower95 \(=-0.072<-0.05\)." State that HFR passes on both models, while \(\tau_{\mathrm{trap}}\) passes only on 7B. | Within constraints; LaTeX only. |
| 3 | **The implemented policy is described inaccurately.** The section says every action JSON and the finish result are retained ([deployment.tex:9](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:9)). In fact, stage \(\ge3\) drops the finish result for 269 cards, stage \(\ge4\) drops read/list actions for 261, and stage 5 drops aggregate actions for 9 ([build_dslice_cards.py:42](/work1/zixuan/projects/agent_memory/pilot/dslice/build_dslice_cards.py:42)). Also, 91 cards fall below the nominal 200-token floor. | Describe D1–D5 as the **base** card and enumerate the actual deletion ladder and counts. Replace "keeps every action JSON" and "keeps the finish result" with the actual invariants: write arguments, aggregate values, and finish action. | Within constraints; LaTeX plus figure-caption tweak. |
| 4 | **"Pre-registered, then amended" is not supported by the repository history.** `ca9c74d` committed the builder at 16:59; Part IV and IV-A were both first added in `b90e93d` at 17:06. Dslice outcome-bearing rollouts began around 17:01 JST. This does not prove outcomes were inspected, but it does mean the artifacts do not establish a separately timestamped original preregistration before implementation. | Call it a "timestamped pre-analysis plan amended during construction," disclose that dslice generation had begun but analysis had not, and avoid claiming independently verifiable preregistration unless an immutable earlier artifact is supplied. | Within constraints; LaTeX only. |
| 5 | **"Capability gate" is inferred from significant-versus-null results without a registered cross-model interaction.** The 3B estimate is not evidence of zero: E1 is \(-0.084[-0.177,+0.002]\), mostly compatible with harm. | Either say "positive evidence at 7B and no evidence of benefit at 3B," or add a clearly post-hoc direct model×policy contrast. My existing-file audit gives \(+0.230\), CI approximately \([+0.134,+0.333]\). Do not retroactively include it in the primary Holm family. | Within constraints; existing-rollout analysis. |
| 6 | **A6 is overclaimed.** The JSON confirms arm-level config hashes and environment versions, but contains no model snapshot ID, dirty-state record, or token-ID no-op result. The analyzer also retains only the first metadata row per arm ([analyze_dslice.py:88](/work1/zixuan/projects/agent_memory/pilot/dslice/analyze_dslice.py:88), [analyze_dslice.py:207](/work1/zixuan/projects/agent_memory/pilot/dslice/analyze_dslice.py:207)). Thus the appendix's complete "assertions passed" statement is not auditable from the cited JSON. | Narrow the appendix to what the JSON establishes. Archive the token-ID comparison and snapshot evidence if they already exist; otherwise state those checks as unverified rather than passed. | Within constraints through reframing; no rollout needed. |
| 7 | **Secondary findings are presented too strongly.** The raw(300) contrast and \(\tau_{\mathrm{trap}}\) check are explicitly secondary and outside Holm, yet the text calls the 3B raw(300) result "significantly negative." The sentence attributing reduced traps to "removing decision-irrelevant bulk" also exceeds the package-level causal identification admitted later. | Use "secondary unadjusted CI excludes zero"; label \(\tau_{\mathrm{trap}}\) secondary; replace the mechanism sentence with a package-level empirical statement. | Within constraints; LaTeX only. |

The card-audit figure also has visibly overlapping bottom annotations and does not explain what stages 1–5 delete. This can be fixed in [fig_hdc.py:90](/work1/zixuan/projects/agent_memory/pilot/dslice/fig_hdc.py:90) by moving notes into the caption, increasing the bottom margin, and adding concise stage labels.

## Scorecard

| Dimension | Score (1–5) | Evidence-based assessment |
|:---|:---:|:---|
| Novelty | 3 | Useful packaged-policy comparison, but no component attribution. |
| Soundness | 2 | Oracle-source dependence and false 3B noninferiority report materially affect interpretation. |
| Evidence | 2 | Large grid and fair token-matched control, but authentic-source sensitivity removes the positive 7B conclusion. |
| Significance | 3 | Potentially useful result, currently limited to one model and a mixed-source benchmark. |
| Clarity | 2 | Actual deletion policy and statistical status are misstated. |
| Reproducibility | 3 | Strong artifact volume, weakened by A6 and preregistration provenance gaps. |
| Limitations | 2 | The most decision-relevant limitation—29.4% oracle fallback—is absent. |

**Overall: 4/10, weak reject for this experiment as presented.**

The section can be salvaged within the loop as an honest mixed-source proof-of-concept. It cannot support its current broad deployment claim without new compute.

</details>

### Actions Taken
All within fix budget (LaTeX reframing, existing-file analysis, figure tweaks; no new rollouts):

1. **(W1) Provenance disclosure + stratified sensitivity**: computed `pilot/dslice/HDC_SENSITIVITY_FALLBACK.json` (post-hoc, family-cluster bootstrap 2000 reps, seed 1234, outside Holm family). `deployment.tex` now discloses 188/640 fallback counts (52/49/43/44 per cell) in §ssec:dctest; "Strength of evidence" reframed into "What the pooled result licenses" vs "What it does not license"; stratified numbers added to `appendix.tex` (app:hdc paragraph); abstract re-worded to bound the claim ("carried by oracle-reconstructed source episodes… we bound the deployment claim accordingly"); figure captions (`fig:hdc`, `fig:hdccards`) disclose provenance; `discussion.tex` marked the prescription "provisional".
2. **(W2)** Table tab:hdc now reads "not est. (+0.000; lower 95 −0.072)" for 3B Δttrap; caption defines "not est." and marks guardrails secondary/outside Holm; text states HFR passes both models, ttrap passes only 7B.
3. **(W3)** `deployment.tex` describes D1–D5 as base card + actual deletion ladder counts (14/76/281/8/252/9); invariants corrected to write-actions-verbatim / aggregate values / finish *action*; captions updated.
4. **(W4)** Preregistration claims corrected: deployment.tex "pre-registered" → "timestamped pre-analysis protocol"; `appendix.tex` discloses commit ordering explicitly (builder 16:59 JST, rollouts ≈17:01 JST, plan commit 17:06 JST; no outcomes analyzed at commit time; artifacts do not establish independently verifiable pre-implementation registration).
5. **(W5)** Post-hoc cross-model E1 difference computed (+0.230 [+0.131,+0.338], outside Holm family) — reported as post-hoc support for scale-dependent pooled effect; abstract/result text now say "positive at 7B, null at 3B" without claiming proven zero at 3B.
6. **(W6)** New artifact `pilot/dslice/A6_CHECKS.json` (+ `a6_checks.py`): full-row metadata scan per arm (config hash, env versions, git commits, row counts) + Qwen2.5 token-id no-op check (all_identical=true); appendix A6 sentence narrowed to exactly what the JSON establishes.
7. **(W7)** raw(300) 3B contrast phrased "secondary, unadjusted CI"; mechanism sentence replaced by package-level empirical statement ("secondary ttrap shift … in the protective direction").
8. **(Figure)** `pilot/dslice/fig_hdc.py`: bottom annotations moved into title/captions, deletion-stage labels added (0 base … 5 −agg act), invariant note added, ylim margin increased; both PNGs regenerated; `figures.tex` captions rewritten accordingly.
9. **Compile gate**: `pdflatex` ×2 after fixes — exit 0, 0 `^!` errors, no undefined references; main.pdf 17pp.

### Results
No new experiments (forbidden by fix budget). Paper now states the deployment claim at the level the artifacts support: pooled-grid benchmark contrast, OR carrying the 7B win, authentic-source question open; blocking follow-up = fallback-free re-harvest (new rollouts, out of loop scope, documented for manual decision).

### Status
- Continuing to round 2 (re-review of the fixed artifacts).
- Difficulty: medium. Backend: codex MCP gpt-5.6-sol xhigh, threadId 019fe135-a9a3-7993-9fb8-5f88f66ebfb7.

---

## Round 2 (review 2026-08-09 00:2x JST; fixes completed 2026-08-09)

Note: round-1 thread was lost in an MCP server restart; 2 fresh-thread attempts timed out (-32001) before round 2 succeeded on the 3rd attempt as a NEW thread (019fe1f2) with round-1 context carried in-prompt. Trace: .aris/traces/auto-review-loop/2026-08-08_run01/002-round-2-review.*.

### Assessment (Summary)
- Score: **5/10**
- Verdict: **Almost** (for an explicitly mixed-provenance benchmark section; not ready as authentic deployment validation) — stop condition (>=6 AND ready/almost) NOT met.
- Reviewer independently reproduced ALL numbers (primary H-DC, sensitivity fallback incl. all 2000-resample max discrepancy = 0, cross-model contrast, A6 checks) — high confidence.
- Round-1 disposition: W8 figure fully resolved; W2/W7 resolved-with-caveat; W1/W3/W4/W5/W6 partial → 7 new remaining weaknesses (all within fix budget, no new rollouts needed):
  1. False multiplicity statement (caption said all guardrails secondary, but HFR is primary Holm member) + blanket abstract guardrail claim.
  2. "3B null / adds nothing / capability gate" still invalid (no equivalence test).
  3. Provenance mechanism sentence invented; "carried by" needs archived direct interaction (reviewer's audit: +0.382/+0.523); appendix E1 denominators should be 233/87 cards.
  4. Policy description still not literal ("every action JSON" false w/ dedup; "verbatim"; "no new text" too absolute).
  5. A6 artifact incomplete (env values, missing-field counts, both-model multi-turn token checks).
  6. NEW layout regression: contrast table 52.96pt overfull.
  7. "Before any outcome was inspected" is author-asserted, not verifiable.

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

## Verdict

**Score: 5/10** for the scoped H-DC contribution at a top venue.
**READY: Almost** for an explicitly mixed-provenance benchmark section; **not ready** as an authentic deployment validation.
**Confidence: High.**

The revision is substantially better than round 1, and the new sensitivity analysis is technically reproducible. Remaining blockers are factual/statistical wording errors and artifact-reporting gaps that require no new GPU rollouts.

## Verification results

- I reproduced the primary H-DC estimates exactly from `HDC_RESULTS.json`.
- I reproduced every value in `HDC_SENSITIVITY_FALLBACK.json` exactly.
- `sensitivity_fallback.py` uses the same pooled-rate E1 statistic and aligned family-cluster resampling as `analyze_dslice.py`: maximum numerical discrepancy was exactly zero across all 2,000 resamples in all four model–provenance analyses.
- The sensitivity appropriately changes the family universe after provenance restriction: 36 families for model-generated A10/A11 cards and 20 for oracle-fallback A10/A11 cards.
- All 2,560 rollout units per model/system are unique; `dslice` and `raw_matched` units and memory IDs align exactly.
- The cross-model contrast reproduces exactly: \(+0.230\,[+0.131,+0.338]\).
- Both A6 checks reproduce exactly, including the Qwen-7B token-ID comparison.
- All displayed sensitivity estimates and CIs in the abstract, deployment text, appendix, and captions match the JSON after rounding.

One denominator description is misleading: E1 actually uses **233 model-generated A10/A11 cards and 87 oracle A10/A11 cards**—932 and 348 rollout rows per arm/model—not all 452/188 cards. The latter are four-cell stratum totals. The “36/20 families” are likewise A10/A11-family counts, while the four-cell totals span 39/31 families.

## Remaining weaknesses, ranked

| Rank | Remaining problem | Minimum fix |
|---:|---|---|
| 1 | **False multiplicity and guardrail statements.** The table caption says all guardrails are secondary and outside Holm, but HFR noninferiority is one of the six primary Holm tests ([deployment.tex:18](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:18), [appendix.tex:10](/work1/zixuan/projects/agent_memory/iclr2027/sections/appendix.tex:10)). The abstract says “without degrading trap guardrails” even though 3B \(\Delta\tau_{\rm trap}\) noninferiority is not established. | State: “HFR noninferiority is primary and Holm-adjusted; \(\Delta\tau_{\rm trap}\) is secondary and outside Holm.” Qualify the abstract to say both trap checks pass only at 7B, while only HFR passes at 3B. |
| 2 | **“3B null,” “adds nothing,” and “capability gate” remain invalid.** The pooled estimate is \(-0.084[-0.177,+0.002]\), with no equivalence test; authentic sources are significantly negative and oracle sources significantly positive. The direct model contrast supports a post-hoc pooled scale difference, not a capability mechanism ([deployment.tex:13](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:13), [figures.tex:42](/work1/zixuan/projects/agent_memory/iclr2027/sections/figures.tex:42), [main.tex:28](/work1/zixuan/projects/agent_memory/iclr2027/main.tex:28)). | Replace every H-DC “null/adds nothing/capability gate” with “no pooled evidence of benefit at 3B; point estimate −8.4pp, with opposite provenance-stratum effects.” Rename the subsection to “a post-hoc pooled scale difference.” |
| 3 | **The provenance interpretation again relies on separate-stratum inference, then invents a mechanism.** “Compact, always-valid plans make truncation especially destructive and compression especially easy” is not identified. At 7B, `dslice` replay is similar across strata (\(+0.117\) authentic vs. \(+0.104\) oracle); the large change is in `raw_matched` (\(+0.076\) vs. \(-0.319\)). | Delete the causal mechanism sentence. Archive a direct provenance interaction before saying “carried by”: my aligned-family audit gives oracle-minus-authentic E1 \(=+0.382[+0.166,+0.606]\) at 7B and \(+0.523[+0.306,+0.783]\) at 3B. Correct the appendix’s E1 sample sizes to 233/87 cards. |
| 4 | **Policy description is still not literal.** The base package does not retain “every action JSON” because exact duplicate non-mutating actions are deduplicated; most actions are canonical reserializations rather than “verbatim”; and deterministic schema keys such as `matched` mean “no new text” is too absolute ([deployment.tex:9](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:9), [build_dslice_cards.py:152](/work1/zixuan/projects/agent_memory/pilot/dslice/build_dslice_cards.py:152)). | Say it adds no generated natural language or new semantic values; retains one canonical copy of each distinct action before escalation; and guarantees parsed write arguments, aggregate values, and the finish action. |
| 5 | **A6 is improved but its cited artifact remains incomplete.** `A6_CHECKS.json` stores only `n_env_versions=1`, not the actual environment values or missing-field counts. The token check uses only Qwen-7B and two synthetic first-turn shapes, while the claim extrapolates to every affected multi-turn arm ([a6_checks.py:67](/work1/zixuan/projects/agent_memory/pilot/dslice/a6_checks.py:67)). | Store the actual environment sets, zero-missing counts, tokenizer snapshot revisions, and token-ID/hash checks for both Qwen sizes over first- and multi-turn prompt shapes—or narrow the paragraph accordingly. |
| 6 | **A new layout regression exists.** The contrast table produces a 52.96pt overfull box and extends materially into the margin. | Split the rate and contrast tables, shorten the E1 labels, or use a width-constrained table. |
| 7 | **The pre-analysis timing remains author-asserted rather than verifiable.** The disclosure is honest, but “before any outcome was inspected” cannot be established from repository history. | Mark that clause as author-reported, or simply say the plan was committed during rollout generation and before the analysis code/result commit. |

## Round-1 disposition

| Round-1 weakness | Status now |
|---|---|
| 1. Oracle-fallback contamination | **Analytically bounded, not scientifically resolved.** Counts, stratification, and mixed-source framing were added; authentic deployment benefit remains unestablished. |
| 2. False 3B trap pass | **Resolved in the table**, but a new blanket abstract guardrail claim partially reintroduces the error. |
| 3. Inaccurate policy description | **Partially resolved.** Ladder and counts are correct; “every action,” “verbatim,” and “no new text” remain inaccurate. |
| 4. Unsupported preregistration | **Rhetorically resolved.** The paper now discloses the timeline; the experiment has not become independently preregistered. |
| 5. Capability gate from significant-vs-null | **Partially resolved.** A direct cross-model contrast was added, but “null/capability gate/adds nothing” remains. |
| 6. Unauditable A6 assertions | **Mostly resolved.** Full-row and token checks now exist and reproduce, with the artifact omissions above. |
| 7. Overstrong secondary/mechanism claims | **Original issue resolved.** Raw(300) is labeled secondary/unadjusted and the old trap mechanism was removed; the new provenance-mechanism sentence is a separate regression. |
| 8. Card-audit figure | **Fully resolved.** No overlap remains, stages are explained, and the provenance annotation is legible. |

The defensible conclusion is now: **a 7B mixed-provenance benchmark win with strong provenance heterogeneity—not validated deployment performance on authentic model-written episodes.**

</details>

### Actions Taken (all within fix budget; no new rollouts)
1. **(W1)** Table caption corrected: "$\Delta$HFR noninferiority is primary, a member of the Holm m=6 family; $\Delta\tautrap$ is secondary, outside Holm"; abstract guardrail claim qualified (primary HFR intact at both scales; secondary trap-shift bound established only at 7B). Cell p-values de-cluttered with caption carrying "all p-values Holm-adjusted".
2. **(W2)** Every H-DC "null / adds nothing / capability gate" replaced: subsection renamed "…, a post-hoc pooled scale difference"; text/figures/discussion/abstract now say "no pooled evidence of benefit at 3B (point estimate −8.4pp)"; cross-model contrast explicitly said to speak to effect size, "not to a capability mechanism".
3. **(W3)** Direct provenance interaction implemented in `pilot/dslice/sensitivity_fallback.py` and archived in `HDC_SENSITIVITY_FALLBACK.json`: oracle-minus-authentic E1 = +0.382 [+0.195,+0.596] (7B), +0.523 [+0.339,+0.742] (3B), strata bootstrapped over their own family universes (36/20); point estimates match the reviewer's independent audit; a common-16-family variant was implemented first, discarded (shifts stratum E1s), and documented in-code. Mechanism sentence deleted; decomposition now states dslice replay is near-identical across strata (+0.117/+0.104 at 7B) while raw_matched swings (+0.076/−0.319). Appendix E1 denominators corrected to 233/87 A10/A11 cards (+ a10_a11_cards recorded in JSON).
4. **(W4)** Policy description made literal: "no generated natural language and no new semantic values"; "one canonical copy of each distinct action (exact-duplicate non-mutating actions collapsed)"; invariants = parsed write-action arguments / aggregate values / finish action.
5. **(W5)** `a6_checks.py` extended: concrete env-versions values + zero-missing-field counts per arm; token-ID check now covers BOTH Qwen2.5 sizes (3B rev aa8e725, 7B rev a09a354) × first-turn(no/with memory) + multi-turn(2 tool rounds) shapes — all identical; `A6_CHECKS.json` regenerated. Appendix sentence narrowed to exactly this artifact.
6. **(W6)** Table fixed: contrast cells no longer embed "Holm" in every entry; pdflatex ×2 → 0 overfull boxes anywhere (also fixed a pre-existing 84.5pt overfull in app:repro by making the audit-path list breakable).
7. **(W7)** Appendix timing clause changed to verifiable form: plan text precedes analysis-code/results commits (17:10/18:10 JST); "no outcomes inspected before amendments" explicitly marked author-reported.
- **Compile gate**: pdflatex ×2, exit 0, 0 `^!` errors, 0 undefined refs, 0 overfull boxes; main.pdf 17pp.

### Results
No new experiments. The section is now internally consistent at the level the mixed-provenance artifacts support; the authentic-deployment question remains open by design (blocking follow-up = fallback-free re-harvest, out of loop scope).

### Status
- Continuing to round 3 (re-review of the round-2 fixes), thread 019fe1f2-1738-7b03-875b-190aca809be1.
- Difficulty: medium. Backend: codex MCP gpt-5.6-sol xhigh.

---

## Round 3 (review 2026-08-09 ~01:15 JST; residual fixes completed immediately after — loop TERMINATED: stop condition met)

### Assessment (Summary)
- Score: **6/10**
- Verdict: **Almost** (as an explicitly mixed-provenance benchmark result) — **STOP CONDITION MET** (score >= 6 AND verdict in {ready, almost}).
- Reviewer verified: both JSONs reproduce exactly from current scripts; all manuscript numbers match; A6 reproduces on both snapshots/shapes; PDF 17pp clean; "no files were changed during this review."
- 5 residual weaknesses (all within fix budget): interaction bootstrap alignment; figure "verbatim" leftover; repro inventory "pre-registered Parts I–IV" contradiction; A6 prompt-shape wording; abstract "undetectable" phrasing.
- Reviewer's final line: "the defensible result is now a robust mixed-provenance benchmark contrast with strong descriptive provenance heterogeneity … would make this scoped section ready under that bounded interpretation."

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

## Verdict

**Score: 6/10** for the scoped H-DC contribution at a top venue.
**READY: Almost** as an explicitly mixed-provenance benchmark result. It remains **not ready as evidence of deployment benefit on authentic model-written episodes**, which the revision now acknowledges.

The major scientific overclaims are substantially repaired. The remaining blockers require only CPU reanalysis and wording/figure updates—no new rollouts.

## Verification

- Both JSON artifacts reproduce exactly from the current scripts.
- The stratified E1 estimates, 233/87 A10/A11 card counts, 36/20 family counts, cross-model contrast, and archived interaction values all match the manuscript after rounding.
- `dslice` and `raw_matched` contain exactly aligned rollout units and memory IDs: 2,560/2,560 per model.
- A6 reproduces exactly for both tokenizer snapshots, all archived prompt shapes, and every metadata row.
- Abstract, deployment, appendix, discussion, and result caption contain no numerical discrepancy with the JSONs.
- The PDF has 17 pages, no LaTeX errors, undefined references, or overfull boxes. The card-audit annotations no longer overlap and stages are explained.
- The fallback caveat is now appropriately prominent, and the principal claim is bounded as a mixed-provenance benchmark comparison.

## Remaining weaknesses, ranked

| Rank | Problem | Minimum fix |
|---:|---|---|
| 1 | **The direct interaction CI does not preserve family-cluster alignment across provenance strata.** The point estimate is exactly the difference between the reported stratum estimates. But [sensitivity_fallback.py:207](/work1/zixuan/projects/agent_memory/pilot/dslice/sensitivity_fallback.py:207) independently resamples the 36- and 20-family universes even though 16 family IDs occur in both strata. Thus it sets the covariance contributed by shared families to zero. This is coherent for hypothetical independent samples, but not the aligned cluster bootstrap corresponding to the actual partially overlapping design. Restricting to the common 16 families was correctly discarded because it changes the estimand; that does not justify independent draws. | Aggregate both strata on the **union of 40 families**, allowing zero contributions where a family is absent from a stratum, and use one family-resample index for both strata. Points remain \(+.382/+.523\); my exact audit gives CIs **7B \([+.166,+.606]\)** and **3B \([+.306,+.783]\)**, still excluding zero. Regenerate JSON and update [deployment.tex:58](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:58), [appendix.tex:12](/work1/zixuan/projects/agent_memory/iclr2027/sections/appendix.tex:12), and [figures.tex:42](/work1/zixuan/projects/agent_memory/iclr2027/sections/figures.tex:42). |
| 2 | **The policy fix did not propagate to the card-audit figure.** The body correctly says “parsed write arguments” and canonical action copies, but the caption and raster still assert “write actions verbatim” ([figures.tex:35](/work1/zixuan/projects/agent_memory/iclr2027/sections/figures.tex:35), [fig_hdc.py:108](/work1/zixuan/projects/agent_memory/pilot/dslice/fig_hdc.py:108)). | Replace “write actions verbatim” with “parsed write-action arguments” in both places and regenerate the PNG. |
| 3 | **The registration disclosure contradicts the reproducibility inventory.** The H-DC appendix now honestly says Part IV was committed after implementation and rollout start, but [appendix.tex:22](/work1/zixuan/projects/agent_memory/iclr2027/sections/appendix.tex:22) still calls Parts I–IV “pre-registered” and says all were registered before analysis runs. | Separate Parts I–III from Part IV/IV-A: describe the latter as a timestamped pre-analysis plan frozen during construction and before analysis-code/result commits. |
| 4 | **A6 wording slightly exceeds the archived prompt-shape check.** The appendix says “first-turn and multi-turn prompt shapes with and without memory,” while [a6_checks.py:72](/work1/zixuan/projects/agent_memory/pilot/dslice/a6_checks.py:72) tests first-turn with/without memory but multi-turn only with memory. | Add the CPU-only multi-turn/no-memory shape, or enumerate the three shapes exactly in [appendix.tex:10](/work1/zixuan/projects/agent_memory/iclr2027/sections/appendix.tex:10). |
| 5 | **“Undetectable on authentic trajectories” can still be read as absence/equivalence.** The authentic 7B interval \([-7.8,+14.9]\)pp is wide enough to include meaningful benefit and harm ([main.tex:28](/work1/zixuan/projects/agent_memory/iclr2027/main.tex:28)). | Say “not established on authentic trajectories (\(+4.1\)pp, CI crossing zero).” |

## Disposition of the seven Round-2 weaknesses

| Round-2 weakness | Round-3 disposition |
|---|---|
| 1. Multiplicity and guardrail errors | **Resolved.** HFR is correctly primary/Holm-family; trap shift is secondary; the abstract accurately limits the 3B guardrail conclusion. |
| 2. “3B null/adds nothing/capability gate” | **Resolved in the pooled analysis.** It now says no pooled evidence, gives the \(-8.4\)pp point, and treats the model contrast as a post-hoc scale difference. The abstract’s “undetectable” wording remains a minor adjacent overstatement. |
| 3. Separate-stratum inference, invented mechanism, wrong denominators | **Partially resolved.** The mechanism was deleted, the decomposition and 233/87 denominators are correct, and a direct interaction was archived. Its points are correct, but its independent-stratum bootstrap is not fully aligned to the overlapping family clusters. |
| 4. Inaccurate policy description | **Partially resolved.** Deployment prose and appendix are now literal; the figure caption and image retain the false “verbatim” invariant. |
| 5. Incomplete A6 artifact | **Substantively resolved.** Environment values, missing counts, revisions, both models, and multi-turn checks reproduce. Only the exact prompt-shape wording needs narrowing or one additional CPU check. |
| 6. Table overfull regression | **Fully resolved.** |
| 7. Unverifiable pre-analysis timing | **Rhetorically softened, not evidentially resolved.** The honest author-reported qualification is appropriate, but the global “pre-registered Parts I–IV” inventory contradicts it. |

Bottom line: the defensible result is now a **robust mixed-provenance benchmark contrast with strong descriptive provenance heterogeneity**. Correcting the interaction resampling and three small consistency issues would make this scoped section ready under that bounded interpretation. No files were changed during this review.

</details>

### Actions Taken (post-stop residual fixes; all CPU/latex, no rollouts)
1. **(F1, statistical)** Interaction bootstrap rewritten to the reviewer's specification: ONE family-resample index over the union of all 40 families (16 occur in both strata), zero-count contributions where a family is absent from a stratum → stratum E1s preserved, shared-family covariance retained. Regenerated `HDC_SENSITIVITY_FALLBACK.json`: 7B +0.382 [**+0.166,+0.606**], 3B +0.523 [**+0.306,+0.783**] — **exactly** the reviewer's independently-computed audit CIs. deployment.tex / appendix.tex (app:hdc) / figures.tex (fig:hdc caption) updated to these CIs.
2. **(F2)** fig:hdc caption + `fig_hdc.py` raster: "write actions verbatim" → "parsed write-action args(uments)"; PNGs regenerated.
3. **(F3)** app:repro inventory split: Parts I–III "pre-registered (before implementation and analysis)" vs Part IV/IV-A "timestamped pre-analysis plan frozen during construction" (cross-ref app:hdc).
4. **(F4)** `a6_checks.py`: added the missing multi-turn/no-memory shape (now 4 shapes × 2 models: first-turn ±memory, multi-turn ±memory — all token-identical); `A6_CHECKS.json` regenerated.
5. **(F5)** Abstract: "undetectable on authentic model trajectories" → "not established on authentic model trajectories (+4.1pp, CI crossing zero)".
- **Compile gate**: pdflatex ×2 → exit 0, 0 `^!` errors, 0 undefined refs, 0 overfull boxes; main.pdf 17pp.

### Results (final)
- Loop trajectory: **4/10 (weak reject) → 5/10 (Almost) → 6/10 (Almost)**, terminated at round 3 of max 4.
- The H-DC deployment section now stands at the exact level its mixed-provenance artifacts support: pooled 7B benchmark contrast (E1 +14.5pp, Holm p=.012) with primary harmful-flip guardrail intact at both scales; secondary trap-shift bound established only at 7B; no pooled evidence of benefit at 3B (−8.4pp); provenance heterogeneity significant (interaction CIs exclude zero at both scales); authentic-deployment benefit explicitly open (blocking follow-up = fallback-free re-harvest, new rollouts, out of loop scope).
- Claims are embodied in the bounded statements above and were independently re-derived by the reviewer from raw artifacts in rounds 2–3 (max discrepancy 0); a separate /result-to-claim pass is therefore redundant for this scoped loop and is documented as skipped for that reason (NOT as failed/unavailable).

### Status
- **Loop terminated — stop condition met.** threadId 019fe1f2-1738-7b03-875b-190aca809be1 (rounds 2–3); round-1 thread 019fe135 lost to MCP restart (context was re-carried).
- Difficulty: medium. Backend: codex MCP gpt-5.6-sol xhigh.

## Method Description

CausalMemBench is a latent-program benchmark for causal decomposition of agent-memory gains: task families are generated from hidden programs over a relational-ops DSL; per memory–target pair, program match (P) and surface similarity (S) are independently randomized (cells A00/A01/A10/A11, plus no-memory N and query-only Q), while family/program/transformation labels remain evaluator-only behind a sealed oracle. Frozen models run fixed-injection rollouts (system prompt + task + one injected memory, max 12 tool steps); inference uses aligned family-cluster bootstrap with a pre-registered Holm family and one-sided noninferiority guardrails. The H-DC deployment layer derives dslice, a deterministic decision-aware compression package (rules D1–D5: canonical copy of each distinct action, one-line read/aggregate summaries, drop list-dumps and write results, keep finish) with a fixed escalation ladder; every stored card keeps parsed write arguments, aggregate values, and the finish action by assertion. Its evaluation pairs each dslice card against the same transcript truncated to the card's exact token count (raw_matched), runs the full 2-model grid, and audits provenance (model-generated vs oracle-reconstructed sources) with stratified and direct-interaction bootstrap analyses.

## Remaining Blockers (documented at termination, out of loop scope)
1. **Authentic-deployment validation** — requires fallback-free re-harvest + new rollouts (blocked by fix budget and the 2026-08-08 "stop experiments" adjudication); flagged in the paper as the follow-up experiment.
2. **Pre-registration provenance for Part IV** — artifacts cannot establish pre-implementation registration; the paper discloses the exact commit timeline instead. Permanent property of this run; not fixable retroactively.
3. Camera-ready items (vector figures, de-anonymization, repo sanitization) per NEXT_ACTION.md.
