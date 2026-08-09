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
