# SFT2 full-mint work ledger (φ+d lane C, data stage)

GS_MINT=20260812. Plan: 200 families (25/schema interleaved, DATA_SPEC §1 plan_families port),
group-split BEFORE rendering (150 train / 25 val / 25 test families → 3000/500/500 texts),
20 texts/family → 4000 total. Evidence clips ≤12 words. Decontamination vs 732 sealed hashes.

Module layout: `mint_core.py` (span/IR/audit-selfcheck) → `mint_p1x.py` (crm_escalate,
inv_overstock) → `mint_p2x.py` (inv_transfer, cal_move_headcount) → `mint_p3x.py`
(ticket_gate_close, cal_finalize) → `mint_p4x.py` (crm_purge_lead, ticket_purge_spam) →
`mint_all.py` (driver: plan, split, partners, mint, dedupe-by-rotation, decon gate, views,
nested LC subsets, receipt).

## Per-schema checkpoint (20-pair mini-batch: 1 family × 20 texts, full per-item gates)

| schema | module | mini-batch checks | PASS | notes |
|---|---|---|---|---|
| crm_escalate | mint_p1x | 120/120 | 1.0000 | incl. cross-schema A00 partner cards |
| inv_overstock | mint_p1x | 120/120 | 1.0000 | forced fix: P2 goal-tag instantiation |
| inv_transfer | mint_p2x | 120/120 | 1.0000 | forced fix: sentence-final-dot numeric probe |
| cal_move_headcount | mint_p2x | 128/128 | 1.0000 | forced fix: A01 nm-entity variants 90+v |
| ticket_gate_close | mint_p3x | 128/128 | 1.0000 | — |
| cal_finalize | mint_p3x | 128/128 | 1.0000 | scope=parent-link audit artifact whitelisted |
| crm_purge_lead | mint_p4x | 145/145 | 1.0000 | forced fix: NM erase-clause evidence split |
| ticket_purge_spam | mint_p4x | 146/146 | 1.0000 | — |

All 8 schemas ≥98% in ≤2 machinery iterations each; none BLOCKED. Forced fixes are
machinery-level (mint-side), logged in mint_receipt.json + DATA_QC.md.

## Full mint

| stage | status | receipt |
|---|---|---|
| full mint 4,000 | DONE — 4000/4000, 82151/82151 checks, decon 0 collisions | mint_receipt.json |
| determinism re-run (byte-identity) | DONE — all 7 artifacts sha256-identical across two runs | DATA_QC.md §7 |
| DATA_QC.md | DONE | gates + strata + decisions + limitations |

Note: run 1 tripped the >1% kill on dedupe collisions (45/4000); fixed in machinery
(pad-stream retries + A01 nm variants + P2 goal-tag instantiation), reminted; run 2/3
byte-identical. qc_run1/ holds the first-pass artifacts for diff provenance.
