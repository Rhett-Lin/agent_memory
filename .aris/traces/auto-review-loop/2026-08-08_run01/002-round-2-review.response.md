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
