# CAUSAL_STRUCTURE_AUDIT — Round 1

> 对应 loop 文件 §6 Loop Step 3 / §8 Gate B（技术报告 §6.9 数据质量闸门）。状态：**框架冻结（2026-08-07），待 Gate A 通过后执行强审计并填数。** "识别优势"定义与 NO_GO 触发器已登记，不得事后修改。

## 1. 审计范围与触发条件

仅当 Gate A = GO 后执行本节全部强审计；Gate A 之前只做 GATE_PROTOCOL.md §4 的弱版（弱 probe + 难度等价 + 长度平衡）。

## 2. 审计清单（Gate B GO 条件逐条对应）

| # | 审计项 | 方法 | 通过阈值（预注册） | 结果 |
|---|---|---|---|---|
| 1 | Program equivalence 人工一致性 | ≥10% families 双人标注（equivalence / near-miss validity / 语言自然度） | 一致率 >0.85 | 待填 |
| 2 | Executable consistency | oracle walker 对全部 sibling 执行 | 100% 合法终态 | 待填（生成时已测，审计复核抽样） |
| 3 | 强 leakage probe | **不止** bag-of-words/embedding：另加 (a) LLM probe（用 frozen 7B 仅看公开文本判别 P/family 标签可恢复性）、(b) character n-gram、(c) trajectory-length、(d) action-sequence statistic；held-out generator/template 上评估 | probe AUC 接近 0.5 且 calibration 良好；报告 AUC + calibration，**不使用"零泄漏证明"措辞** | 待填 |
| 4 | No-memory sibling 难度等价 | TOST，预注册 margin ±7pp | 差异落在 margin 内 | 待填 |
| 5 | S 操作化敏感性 | 连续 S（token overlap + embedding 双指标）下重估 τ_struct / τ_trap | 主结论在二值化与连续 S 下方向一致 | 待填 |
| 6 | 效应存在性复核 | τ_struct 或 τ_trap 至少一个 | 统计显著、非零、跨 seed 稳定 | 待填 |

## 3. "识别优势"登记（对应 EAGLE 的"张量优势"）

**登记定义**：在相同 token 预算、相同 retriever（pilot 为 fixed injection）、相同模型下，P×S 正交析因揭示出的稳定效应，必须不能由以下两者完全解释：

1. Memory Transplants 式 architecture×content 主效应（系统/域级 2×2）；
2. Proced-Mem 式 embedding generalization cliff（检索侧相似度断崖）。

**操作化判定**（pilot 版本）：若 τ_struct 与 τ_trap 的 cell-level 模式可由 (a) memory/target 的 aggregate embedding similarity + (b) architecture/content 两个哑变量的线性组合完全吸收（残差 CI 含 0），则识别优势不成立 → **立即 NO_GO**。

## 4. 失败处置（预登记）

- 任一审计项未过：记录失败细节 → 返回 Loop Step 1；已扩展 family 不得强行保留，诚实报告识别失败；
- 连续 3 次 Gate A/B NO_GO 后必须修正研究对象（重定义 program equivalence 操作化或换环境），不得只调 family/seed 数。

## 5. 证据存档位置

- probe 模型与数据：`outputs/agent_memory/pilot/probes/`
- 人工标注表：`outputs/agent_memory/pilot/human_audit/`
- 本文件填数后同步更新 `GATE_FINDINGS.md`、`DECISION.md`、`RESEARCH_LEDGER.md`。
