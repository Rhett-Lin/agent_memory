# GATE_FINDINGS — 轮次级判定记录

> 判定阈值见 `GATE_PROTOCOL.md`（Gate A）与 `CAUSAL_STRUCTURE_AUDIT.md`（Gate B），均在数据产生前登记，不得事后放宽。

## Gate A — Pilot Identification Gate（Round 1，待判定）

**前置合规检查**

| 检查项 | 阈值 | 实测 | 通过 |
|---|---|---|---|
| parseable action 率 | >90% | 待填 | 待填 |
| compliance（memory 被读取） | 启发式 >0（pilot 登记以具体指标为准） | 待填 | 待填 |
| oracle 合法终态 | 100% | 待填 | 待填 |
| N 条件成功率区间 | 30–70% | 待填 | 待填 |
| 弱 leakage probe（overlap/length/embedding→cell） | AUC≈0.5 | 待填 | 待填 |

**主 estimand（Holm 校正，family-cluster bootstrap 95% CI）**

| Estimand | 3B 估计 [CI] | 7B 估计 [CI] | 判定 |
|---|---|---|---|
| τ_context = E[Y_Q−Y_N] | 待填 | 待填 | 待填 |
| τ_struct = E[Y_A10−Y_A00] | 待填 | 待填 | 待填 |
| τ_trap = E[Y_A01−Y_A00] | 待填 | 待填 | 待填 |
| τ_P×S | 待填 | 待填 | 待填 |

**判定**：待填（GO / NO_GO，附触发条款编号与证据指针）

## Gate B — 因果有效性 Gate（未触发）

Gate A 通过前不执行；触发后按 `CAUSAL_STRUCTURE_AUDIT.md` 填 6 项审计。

## Gate C / D — 本轮范围外

Stage B–D、TRU-Mem 均未启动（按 loop §16 第一轮禁令）。
