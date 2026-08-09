# Novelty Dossier — Execution-Grounded Program-Equivalence Estimator for Agent Memory Admission (Gate 0)

Date: 2026-08-08. Reviewer: read this file and answer the questions at the end with brutal honesty.

## Proposed method (candidate next project, post-H-DC)

Setting: LLM tool-agent over a verifiable environment (SQLite DB/SQL-agent class; possibly ALFWorld-like). The agent has an episodic memory pool (stored task trajectories, decision-aware compressed). Before injecting a stored memory into the prompt, an **execution-grounded program-equivalence estimator** decides admission:

- Induce the memory's latent program from its stored action sequence (skeleton over tools with typed args; parameter binding abstracted).
- Derive the target task's required program class from task text + live schema (deterministic template induction, feasibility checked against the environment).
- Verify equivalence by *probing* in the environment: re-run the memory program's read/aggregate precondition chain against current DB state; compare the induced decision/write step and finish predicate class against the target's. Output P̂ ∈ {match, near-miss, unrelated} + confidence. NO LLM text judgment, NO embedding similarity — the environment itself is the oracle at admission time.

Endpoint metrics (if built): replay premium harvested (A11-leg gains retained), harmful-flip rate avoided (near-miss correctly refused), admission FP/FN vs oracle labels.

## Core claims to adjudicate

1. **C1 (mechanism)**: Admission decision via *in-environment re-execution/probing of the memory's action preconditions*, rather than static checks (belief signatures, metadata contracts, bandit features, neural gates). Claim: no prior work does probe-based admission for episodic memory in DB/SQL agents.
2. **C2 (program equivalence, not similarity)**: Program induction from a single stored trajectory + program-class matching to the target task, as the admission criterion — replacing embedding/LLM-judge similarity, which our own audit showed fails (LLM judge 0.25 agreement with oracle; intent judge AUC 0.508).
3. **C3 (near-miss detection)**: Executable probes distinguish program-matched vs surface-matched-but-divergent memories (near-miss) *before* injection — a detection mechanism, not just the problem statement.
4. **C4 (framing/contrast class)**: "Verify the memory, not the output" — execution grounding has been used to verify candidate outputs/plans (execution-guided decoding, self-correction), but not to gate *stored episodic memory* at read time.

## Phase-B verified prior work (all arXiv IDs verified via arXiv API on 2026-08-08)

| Paper | ID | Venue/Date | Overlap | Residual difference |
|---|---|---|---|---|
| RPMS: Rule-Augmented Memory Synergy | 2603.17831 | 2026-03 | ALFWorld; belief-state signature filtering of episodic memory pre-injection; 2×2 shows unfiltered memory HARMS (55.6%→11.1%) | Static signature check, NOT in-environment probing; no program induction; authors admit SCF is a "lightweight proxy for full precondition equivalence, leaves room for finer-grained filtering" |
| MemoGuard: Guarding Against Memory Traps | 2607.15589 | CODES/ESL 2026-07 | Coins "memory traps" = high-similarity but execution-invalid memories; 3 hard feasibility contracts gate reuse (robot navigation) | Contract checks are metadata/state-variable rules, not action re-execution; single-step supervisory actions, no multi-step program; no program induction |
| RSCB-MC: Learning When to Remember | 2604.27283 | 2026-04 | Abstention-aware contextual bandit for memory injection in coding agents; hard negatives = same stack trace, different root cause | 16-feature bandit; executes nothing; offline proxy eval only; debugging domain |
| Beyond Similarity / MemGate | 2606.06054 | 2026-06 | "Task-conditioned memory admission" terminology; semantic relevance ≠ contextually appropriate | 9M-param learned neural gate; no execution; conversational agents, security-oriented |
| MERIT: Dual-Level Memory for Text-to-SQL | 2606.00547 | 2026-05 | SQL-agent long-term memory (the target domain); execution feedback used in TRAINING-time process reward | Admission is a learned retrieval policy at deployment; no executable probe; no near-miss concept |
| Memp (procedural memory build/retrieve/update) | 2508.06433 | 2025 | Trajectory→procedural memory induction | similarity retrieval; no verification admission |
| Skills as Verifiable Artifacts | 2605.00424 | 2026-05 | "Skills untrusted until verified"; verification-level manifests | supply-chain framing; verify at LOAD time, not per-task admission; position paper |
| Voyager | 2305.16291 | TMLR 2023 | executable code skills library | retrieval by embedding, zero verification at reuse; success judged by LLM self-verify |
| Agent Workflow Memory (AWM) | 2409.07429 | ICML 2025 | workflow induction from trajectories + reuse | text/embedding matching; no program-class equivalence; no probes |
| BREW (DreamCoder-style recipe KB) | 2511.20297 | 2025-11 | recipes carry NL "when it applies" conditions; hindsight relabeling of near-misses | conditions are NL text, no executable check; no admission gate |
| Synapse (trajectory-as-exemplar) | 2306.07863 | NeurIPS 2023 | state-similarity conditioned exemplar memory | no verification/admission |
| AutoGuide | 2403.08978 | COLM 2024 | guidelines with applicability conditions | condition judgment via state-text similarity |
| Affordance Agent Harness | 2605.00663 | 2026-05 | "verification-gated skill orchestration" | statistical consistency checks; memory is prior not verified object; CV domain |
| Learning to Share | 2602.05965 | 2026-02 | "memory admission controller" | WRITE-side admission for efficiency |
| A-MAC | 2603.04549 | 2026-03 | "adaptive memory admission control" | WRITE-side; conversational facts; LLM utility scoring |
| MemRL | 2601.03192 | 2026-01 | RL runtime utility learning over episodic memory (ALFWorld) | learned utility, no execution-grounded equivalence check |
| LabEvolver | 2607.27690 | 2026-07 | ALFWorld; execution experience→skill/safety memory distillation | distillation/write-side; no read-side probe admission |
| AgentForge | 2604.13120 | 2026-04 | execution grounding as first-class principle | verifies code changes (outputs), not stored memory |
| LitE-SQL | 2510.09014 | 2025-10 | execution-guided self-correction | verifies GENERATED SQL (output), not retrieved memory |

## Context facts about the parent project (for positioning)

- Our ICLR-2027-submission benchmark provides sealed oracle program-equivalence labels; audit showed LLM judges (0.25 agreement) and intent judges (AUC 0.508) cannot recover them; embeddings only partially.
- Deployment result already secured: decision-aware compression (dslice) beats paired-budget naive truncation by +14.5pp replay premium on 7B, noninferior on traps (Holm-corrected).
- This dossier's idea is the intended *contrast completion*: static/neural admission gates fail (theirs + ours); executable probes are the remaining mechanism class.

## Questions for the reviewer

1. Is the **mechanism claim C1** (in-environment precondition probing / re-execution as the admission mechanism for stored episodic memory) novel against the table above and against anything else you know (2024–2026, incl. NeurIPS/ICML/ICLR/ACL programs)? Name any paper that does it.
2. Is the overall package (C1+C2+C3 in DB/SQL agents, evaluated causally against sealed oracle labels) publishable-novel at a top venue, or does RPMS/MemoGuard/RSCB-MC/MemGate collectively occupy the contribution?
3. What is the SINGLE closest prior work a hostile reviewer would cite, and what is the sharpest one-sentence delta?
4. Which claims should be DROPPED or softened (e.g., C3's "near-miss detection" vs MemoGuard's "memory traps" terminology collision)?
5. Recommended positioning: title-level framing + the 2–3 contrasts that must appear in eval to survive review.
