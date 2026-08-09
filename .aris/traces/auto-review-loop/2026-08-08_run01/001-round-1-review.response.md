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

- The 3B \(\Delta\tau_{\mathrm{trap}}\) noninferiority claim is false. Its one-sided lower bound is \(-0.0719\), below the \(-0.05\) margin, and `ttrap_noninf_ok=false` ([HDC_RESULTS.json:181](/work1/zixuan/projects/agent_memory/pilot/dslice/HDC_RESULTS.json:181), [HDC_RESULTS.json:392](/work1/zixuan/projects/agent_memory/pilot/dslice/HDC_RESULTS.json:392)). The table nevertheless says “pass (+0.000; n.s.)” ([deployment.tex:45](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:45)). Part IV-A explicitly forbids treating nonsignificance as noninferiority.
- This error does not overturn the registered GO decision, because the GO model is 7B and both 7B guardrails pass.

## Remaining weaknesses, ranked

| Rank | Weakness | Minimum fix | Constraint status |
|---:|---|---|---|
| 1 | **The “deployment” result is contaminated by undisclosed oracle trajectories.** The builder reconstructs oracle-plan trajectories whenever harvesting failed ([build_dslice_cards.py:107](/work1/zixuan/projects/agent_memory/pilot/dslice/build_dslice_cards.py:107)). This affects 188/640 cards: A00=52, A01=49, A10=43, A11=44. An exploratory existing-file sensitivity gives 7B E1 \(=+0.041\), CI approximately \([-0.078,+0.145]\), after excluding fallback cards cell-wise, versus \(+0.424\) \([+0.250,+0.613]\) on oracle-fallback cards. On 3B, the corresponding signs also reverse: model-generated \(-0.226\), oracle \(+0.297\). Thus the positive 7B deployment interpretation does not survive on authentic model-generated source trajectories. | Disclose all fallback counts; add a family-bootstrap fallback-stratified sensitivity; reframe the result as a mixed model/oracle-source benchmark comparison. Remove claims of validated deployment on past model episodes. | **Within constraints.** Retaining the stronger authentic-deployment claim would **require new compute**: reharvest without fallback and rerun. |
| 2 | **3B trap noninferiority is misreported.** “n.s.” is used as a pass despite the preregistered bound rule. | Change the table to “not established; lower95 \(=-0.072<-0.05\).” State that HFR passes on both models, while \(\tau_{\mathrm{trap}}\) passes only on 7B. | Within constraints; LaTeX only. |
| 3 | **The implemented policy is described inaccurately.** The section says every action JSON and the finish result are retained ([deployment.tex:9](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:9)). In fact, stage \(\ge3\) drops the finish result for 269 cards, stage \(\ge4\) drops read/list actions for 261, and stage 5 drops aggregate actions for 9 ([build_dslice_cards.py:42](/work1/zixuan/projects/agent_memory/pilot/dslice/build_dslice_cards.py:42)). Also, 91 cards fall below the nominal 200-token floor. | Describe D1–D5 as the **base** card and enumerate the actual deletion ladder and counts. Replace “keeps every action JSON” and “keeps the finish result” with the actual invariants: write arguments, aggregate values, and finish action. | Within constraints; LaTeX plus figure-caption tweak. |
| 4 | **“Pre-registered, then amended” is not supported by the repository history.** `ca9c74d` committed the builder at 16:59; Part IV and IV-A were both first added in `b90e93d` at 17:06. Dslice outcome-bearing rollouts began around 17:01 JST. This does not prove outcomes were inspected, but it does mean the artifacts do not establish a separately timestamped original preregistration before implementation. | Call it a “timestamped pre-analysis plan amended during construction,” disclose that dslice generation had begun but analysis had not, and avoid claiming independently verifiable preregistration unless an immutable earlier artifact is supplied. | Within constraints; LaTeX only. |
| 5 | **“Capability gate” is inferred from significant-versus-null results without a registered cross-model interaction.** The 3B estimate is not evidence of zero: E1 is \(-0.084[-0.177,+0.002]\), mostly compatible with harm. | Either say “positive evidence at 7B and no evidence of benefit at 3B,” or add a clearly post-hoc direct model×policy contrast. My existing-file audit gives \(+0.230\), CI approximately \([+0.134,+0.333]\). Do not retroactively include it in the primary Holm family. | Within constraints; existing-rollout analysis. |
| 6 | **A6 is overclaimed.** The JSON confirms arm-level config hashes and environment versions, but contains no model snapshot ID, dirty-state record, or token-ID no-op result. The analyzer also retains only the first metadata row per arm ([analyze_dslice.py:88](/work1/zixuan/projects/agent_memory/pilot/dslice/analyze_dslice.py:88), [analyze_dslice.py:207](/work1/zixuan/projects/agent_memory/pilot/dslice/analyze_dslice.py:207)). Thus the appendix’s complete “assertions passed” statement is not auditable from the cited JSON. | Narrow the appendix to what the JSON establishes. Archive the token-ID comparison and snapshot evidence if they already exist; otherwise state those checks as unverified rather than passed. | Within constraints through reframing; no rollout needed. |
| 7 | **Secondary findings are presented too strongly.** The raw(300) contrast and \(\tau_{\mathrm{trap}}\) check are explicitly secondary and outside Holm, yet the text calls the 3B raw(300) result “significantly negative.” The sentence attributing reduced traps to “removing decision-irrelevant bulk” also exceeds the package-level causal identification admitted later. | Use “secondary unadjusted CI excludes zero”; label \(\tau_{\mathrm{trap}}\) secondary; replace the mechanism sentence with a package-level empirical statement. | Within constraints; LaTeX only. |

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