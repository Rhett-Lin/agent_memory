# Novelty Dossier: CausalMemAgent

## Task for you (GPT-5.6-Sol, xhigh reasoning)

Act as a skeptical, brutally-honest senior reviewer for ACL/EMNLP/ICML/NeurIPS-tier venues. You are given
(1) a proposed research program description, (2) a list of candidate prior-work papers already found via web
search, and (3) explicit questions. Do NOT be diplomatic. Your job is to find reasons this is NOT novel before
accepting that it is. If you believe the searches below missed something, say so explicitly and name what kind
of paper/venue you'd expect it in.

Answer the four questions at the bottom in a structured way. Be concrete: cite which candidate paper(s), if any,
already cover each core claim, and state the delta (or lack thereof) precisely.

---

## Proposed Method Description (verbatim summary)

**CausalMemAgent** reframes "does agent memory help" (already answered many times) into "what is agent memory
gain actually made of, and can we select memory that survives distribution shift." Concretely:

1. **CausalMemBench**: An executable agent-task benchmark built around *latent program equivalence classes*
   z = (precondition partial-order, safety constraints, terminal conditions, recovery conditions). Each family
   F_z contains multiple surface-different "sibling" tasks that share the same z, plus a "near-miss" family F_z'
   that is textually/interface similar but has a different z (different precondition/branch/safety condition).
   Critically: the latent program id z, family id, transformation id, and near-miss label are **evaluator-only**
   — never exposed to the agent or to the memory/utility model, enforced by a sealed generator / hidden oracle,
   with leakage probes (bag-of-words / embedding / tool-name classifiers) used to certify that treatment
   assignment is NOT trivially predictable from surface features.

2. **Orthogonal factorial causal design (F-MED = Factorial Memory Effect Decomposition)**: Rather than the
   common "M0 (no memory) vs M1 (RAG) vs M2 (workflow memory) vs ours" ladder comparison (where multiple
   confounds change at once), the design independently and orthogonally randomizes a treatment vector
   W = (P, S, D, I, V, E) for each injected memory relative to a target task:
   - P = latent program match (0/1, evaluator-only ground truth)
   - S = surface/lexical similarity (0/1, calibrated by nuisance measures)
   - D = domain match, I = interface/tool-schema match, V = environment version/rule freshness match
   - E = exact same-instance exposure (nested factor, only defined within P=1,S=1,D=1,I=1,V=1)
   A primary 2x2 (P x S) factorial experiment with N (no-memory) and Q (sham/placebo memory, format-matched but
   content-free) arms yields identified causal estimands under randomization:
   - clean structural transfer effect: τ_struct = E[Y(P=1,S=0) − Y(P=0,S=0)]
   - surface trap / near-miss harm: τ_trap = E[Y(P=0,S=1) − Y(P=0,S=0)]
   - replay-like premium and true exact-exposure premium (nested, nested nuisance-controlled)
   - P×S interaction, and transport gaps G_D, G_I, G_V comparing τ_struct under matched vs shifted domain/
     interface/version conditions
   - A "harmful flip rate" (paired outcome flips from success to failure caused by near-miss memory)
   - A per-system "F-MED profile" vector so that two memory systems with identical aggregate accuracy gain can
     be shown to have completely different causal compositions (one mostly replay/exact, another mostly clean
     structural transfer)
   Stage D separately randomizes *retrieval/selection* (natural vs random vs oracle retriever over a mixed bank)
   to isolate content-utility from selection-policy effects, after content effects are established with fixed
   injection in Stages A-C.

3. **TRU-Mem (Transportable Robust Utility Memory, tentative name)**, positioned explicitly as a *secondary*,
   discovery-driven contribution: an oracle-free memory admission policy that estimates
   u_trans(m) = E_{x~A(x_src)}[Y(x,m) − Y(x,∅)] where A is an *observable* transformation generator (entity
   rename, schema paraphrase, tool rebinding, state resampling) — NOT the hidden family/program oracle. The
   utility model's input schema explicitly excludes ground-truth workflow graph, family ID, P/S/D/I/V labels,
   and transformation ID (audited). It optimizes a lower-tail / CVaR robust objective (not average utility), and
   gates admission with simultaneous-correction confidence bounds (LCB(mean utility) > eps AND UCB(harm risk) <
   delta) computed on calibration transformations disjoint from candidate generation (to avoid selection bias in
   the guarantee). Success is measured not by aggregate accuracy but by whether structural-transfer ratio rises
   and harmful-flip rate falls at matched token budget.

4. **Theory**: basic non-identifiability + randomized-identification lemmas are explicitly demoted to "design
   support, not a contribution." The paper's candidate top-tier theoretical hook (only one to be pursued, not
   all three) is one of: (a) distributionally-robust admission under an f-divergence/Wasserstein ball on the
   deployment transformation distribution Q_t, (b) conformal risk control for admitted-memory harmful-flip risk
   under adaptive candidate selection, or (c) a conservative-contextual-bandit formulation of memory/no-memory
   admission with a regret/constraint-violation guarantee relative to a no-memory baseline.

The report positions itself explicitly against ~30 papers from 2023-2026 that it says are NOT sufficient to
independently claim novelty on their own (see candidate list below) — its central bet is that the *combination*
of (a) evaluator-only oracle + orthogonal P×S(×D×I×V×E) factorial randomization for causal decomposition of
"memory gain," plus (b) an oracle-free utility model trained/validated for transportability across *observable*
transformations rather than item-level or aggregate outcome, is what's new — not any single piece in isolation.

---

## Candidate Prior-Work Papers (found via web search, all verified to exist as of Aug 2026)

| # | Paper | Venue/Date | What it actually does | Closest overlap with CausalMemAgent |
|---|---|---|---|---|
| 1 | Reflexion (Shinn et al.) | NeurIPS 2023 | Verbal RL reflection stored in episodic buffer | Foundational; no randomization, no transfer identification |
| 2 | ExpeL (Zhao et al.) | AAAI 2024 | Extracts NL insights from experience, retrieves at inference | Experiential learning claim without randomized transfer test |
| 3 | Agent Workflow Memory (Wang et al.) | ICML 2025 | Induces workflows from WebArena/Mind2Web traces | Cross-task/site gains reported, no causal decomposition |
| 4 | Memp (Fang et al.) | 2025, arXiv 2508.06433 | Build/Retrieval/Update study of procedural memory, step vs script abstraction | Procedural memory cross-model transfer claim, no factorial causal design |
| 5 | MCMA (Liang et al.) | ACL 2026 Findings, arXiv 2601.07470 | Learns memory-abstraction hierarchy via DPO-trained "memory copilot," frozen task model, tests OOD/cross-task transfer (ALFWorld/ScienceWorld/BabyAI) | Learns WHAT to abstract; does not orthogonally randomize program-match vs surface-similarity, no evaluator-only oracle, no harmful-flip/near-miss causal estimand |
| 6 | ReMe (Cao et al.) | ACL 2026 Findings, arXiv 2512.10696 | Multi-faceted distillation + context-adaptive reuse + utility-based refinement/pruning; BFCL-V3, AppWorld; SOTA; memory-scaling effect (8B+ReMe beats memoryless 14B) | Utility-based admission/pruning already exists, but item-level/outcome-based, not transformation-robust, no factorial P×S identification |
| 7 | AFTER benchmark | 2026, arXiv 2606.23127 | 382 enterprise tasks, 6 roles, 22 procedural skill categories; local/cross-task/cross-role/cross-model transfer eval | Broad transfer benchmark but not causally orthogonal, no hidden latent-program oracle |
| 8 | Memory Transfer Learning (Kim et al.) | 2026, arXiv 2604.14004 | 6 coding benchmarks, trajectory/workflow/summary/insight compared; abstraction level predicts transfer; low-level traces cause negative transfer | Directly relevant finding (abstraction vs transfer) but observational/comparative, not randomized factorial; no oracle-only latent program |
| 9 | Memory Transplants (Feng et al.) | ICLR 2026 MemAgents Workshop | 2x2 factorial disentangling memory ARCHITECTURE vs CONTENT transfer across a code→math domain shift; weak solvers benefit more (+15pp vs +7pp) | **Closest methodological precedent**: uses a genuine 2x2 factorial design for causal disentangling in agent memory. But factors are architecture×content×domain-shift, not program-match×surface-similarity within matched task families; no evaluator-only latent program oracle; no nested exact/interface/version factors; workshop paper (not peer-reviewed main venue), single domain pair |
| 10 | When Continual Learning Moves to Memory (Hu et al.) | 2026, arXiv 2604.27003 | Stability-plasticity dilemma shifts to memory representation/retrieval; forward-transfer designs may increase forgetting | Conceptual/observational, not factorial-causal |
| 11 | More Skills, Worse Agents? (Song & Song) | 2026, arXiv 2605.24050 | Decomposes large skill-library degradation into skill-shadowing vs context-overhead | Decomposition framing similar in spirit but for library size, not P×S causal identification |
| 12 | Useful Memories Become Faulty (Zhang et al.) | 2026, arXiv 2605.12978 | Consolidation utility rises then falls even on correct trajectories; rewriting can corrupt memory | Different mechanism (consolidation decay), not surface/program confound |
| 13 | MemDelta (Wang) | 2026, arXiv 2606.29914 (verified real) | Controlled one-component-at-a-time ablation protocol (embedding/LM/retrieval/write-cost) on LongMemEval; shows ranking reversals across models | Confound-control precedent, but not factorial randomization of program/surface match; different confound class (pipeline components, not task structure) |
| 14 | Bridge Evidence (Mukhopadhyay et al.) | 2026, arXiv 2607.15253 (verified real) | Deletion-intervention "Counterfactual Trajectory Utility" for documents in agentic search; static relevance ~independent of causal utility | Deletion-based counterfactual utility precedent for retrieval, but for search documents not memory, single-item deletion not factorial task-family design |
| 15 | MemAudit (Tan et al.) | 2026, arXiv 2605.23723 | Counterfactual memory influence to find poisoned/harmful memories post-hoc | Counterfactual-attribution precedent, security-framed, not transfer-identification framed |
| 16 | HiMPO (Yan et al.) | 2026, arXiv 2606.16285 (verified real) | RL credit assignment for memory-write actions via local counterfactual utility + hindsight relevance filter, addresses entangled credit from downstream tool errors | Local counterfactual utility for write-policy training, not transportability-across-transformation utility, no factorial design |
| 17 | AttriMem (Li et al.) | 2026, arXiv 2607.21106 (verified real) | Token-level attribution process-reward for memory-construction RL policy | Fine-grained credit assignment, not causal transfer decomposition |
| 18 | LifelongAgentBench (Zheng et al.) | ICLR 2026, arXiv 2505.11942 | DB/OS/KG environments; skill acquisition/transfer/retention; shows plain replay hurt by irrelevant info/context length | Lifelong transfer benchmark, no orthogonal randomization |
| 19 | MemoryAgentBench (Hu et al.) | ICLR 2026, arXiv 2507.05257 | Incremental-injection benchmark for accurate retrieval/test-time learning/long-range/selective forgetting | Different axis (incremental injection), not causal decomposition |
| 20 | Mem2ActBench (Shen et al.) | 2026, arXiv 2601.19935 | Evaluates whether retrieved memory is actually used to select tools/ground parameters, not just factual QA | Action-grounded eval, not causal transfer decomposition |
| 21 | RECON | 2026, arXiv 2607.16716 (checked this session) | Benchmarks compositional reasoning over long-context memory (evidence chains, cascading invalidations, source conflicts); has "same-family vs cross-family" accuracy split | Uses a family/cross-family split similar in spirit, but for long-context compositional QA, not executable task transfer; no factorial randomization or evaluator-only latent-program oracle found in abstract |
| 22 | Supersede | 2026, arXiv 2606.27472 (checked this session) | Isolates "memory-update / supersession" failure (using stale vs current fact values), RL env + GRPO training, held-out generalization test | Held-out oracle-style eval, but narrowly about fact freshness/supersession, not program-structure transfer |
| 23 | SeqMem-Eval | 2026, arXiv 2605.15384 (checked this session) | Diagnostic framework decomposing sequential memory behavior into online utility / hold-out generalization / backward transfer / forgetting | A *decomposition* framework for memory eval, conceptually adjacent (decompose "improvement" into components) but the components are temporal/continual-learning axes, not program-match vs surface-similarity causal factors; no randomized factorial design or hidden oracle |
| 24 | RoMeRL | 2026, arXiv 2608.02508 (checked this session, published within days of this report) | Reduced-order utility-state RL memory system addressing "memory-reward trap" (irrelevant experiences get misleading utility updates) and utility dispersal | Different problem (RL memory-state representation efficiency), not causal identification via factorial design |
| 25 | Causal Agent Replay | 2026, arXiv 2606.08275 | Structural causal model of an agent run; interventions on steps to attribute failures | Uses SCM/intervention language but for within-trajectory failure attribution, not cross-task memory transfer identification |
| 26 | Conformal Risk Control (Angelopoulos et al.) | ICLR 2024 | General conformal risk-control theory | Generic tool CausalMemAgent proposes to apply, not agent-memory-specific |
| 27 | Conservative Bandits (Wu et al.) | ICML 2016 | Generic conservative-bandit theory | Generic tool, not agent-memory-specific |
| 28 | Transportable Representations for Domain Generalization (Jalaldoust & Bareinboim) | AAAI 2024 | Transportability theory from causal inference | Generic causal-transportability theory being imported into agent memory, not previously applied there |

## Additional searches run (Aug 2026) that found NO closer match

- "agent memory 'surface similarity' 'program match' factorial randomized causal decomposition transfer 2026" — no hits on the specific combination.
- "LLM agent memory 'evaluator-only' latent program oracle benchmark held-out family transfer" — surfaced Supersede, PM-Bench, RECON, MemQ, SeqMem-Eval (all listed above), none combine orthogonal P×S factorial + hidden program oracle.
- "'transportable utility' OR transportability agent memory transformation shift risk-controlled admission 2026" — no academic hits, only industry blog content.
- "agent memory replay vs generalization matched task family counterfactual randomized controlled trial arxiv 2026" — surfaced Causal Agent Replay (within-trajectory, not cross-task memory), Regret-Aware Policy Optimization (env-level replay suppression, different problem).
- ICLR 2026 MemAgents workshop accepted-paper list (~50+ papers) fetched directly — no paper found matching factorial P×S causal decomposition with evaluator-only oracle.
- "'near-miss' memory agent negative transfer surface trap program equivalence class 2026" — no hits combining these terms.

Caveat: web search coverage of the last 2-4 weeks of arXiv (i.e., papers from ~mid-July to Aug 7, 2026) may be
incomplete since indexing lags; RoMeRL above (arXiv 2608.02508) is dated literally days before this dossier was
written, suggesting the field is moving fast enough that something even more recent could exist unindexed yet.

---

## Questions

1. **Is CausalMemAgent's core identification design — orthogonal randomization of latent-program-match (P) and
   surface-similarity (S), with the program label enforced evaluator-only via a sealed oracle, nested exact/
   domain/interface/version factors, and a per-system "F-MED profile" showing that aggregate-equivalent memory
   systems have different causal compositions — already been done? If not exactly, what is the closest single
   paper, and precisely what is missing from it relative to CausalMemAgent's design?**

2. **Is TRU-Mem's core idea — a memory-admission utility model trained/validated for robustness to *observable*
   task transformations (not hidden family/oracle labels), with a lower-tail/CVaR objective and simultaneous-
   correction risk-controlled admission bounds computed on disjoint calibration transformations — already
   covered by ReMe's utility-based refinement, HiMPO's local counterfactual utility, or AttriMem's attribution
   reward? Be specific about what changes and what doesn't.**

3. **Given candidate #9 (Memory Transplants, ICLR 2026 MemAgents Workshop) is the closest methodological
   precedent (a genuine 2x2 causal factorial design in agent memory), how much of CausalMemAgent's novelty
   survives once a reviewer who knows that workshop paper reads this proposal? Is "orthogonal P×S with an
   evaluator-only latent-program oracle across matched task families" a big enough delta from "architecture x
   content x code-to-math domain shift," or would a tough reviewer call it an incremental extension?**

4. **Overall verdict**: score novelty 0-10, give PROCEED / PROCEED WITH CAUTION / ABANDON, name the single
   biggest risk a Reviewer 2 would raise, and say what venue tier (ACL/EMNLP main vs ICML/NeurIPS/ICLR vs
   Findings/Workshop only) this actually merits as currently scoped — independent of the source report's own
   self-assessment (which already claims ACL/EMNLP main is achievable and ICML/NeurIPS needs one more
   nontrivial theory result). Do you agree or disagree with that self-assessment, and why?**
