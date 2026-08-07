# NEXT_ACTION — Round 1 in flight（2026-08-07）

唯一下一步动作：

Gate A=GO、Gate B=GO（2026-08-08）。Loop Step 4/5 完成：选定 H-C（published write-path systems 的 F-MED profile 逆序，评分 3.95），GATE_PROTOCOL Part II 已预注册冻结。当前 agent-6 正在实现 minimal gate：

1. `pilot/systems/build_raw_cards.py`（800 源任务真实轨迹采集，含 oracle_fallback 标注）；
2. `pilot/systems/build_summary_cards.py`（7B 温度 0 摘要，禁 sealed 标签）；
3. raw + summary 各 3840 rollouts 网格（10 GPU）；
4. `analyze_hc.py` 产出 6 个预注册对比（3 系统对 × {τ_struct, τ_trap}，Holm）。

回来后我做 GO/NO_GO 判定（H-C-3：任一对 |Δτ_struct|≥8pp 且 CI 分离，或 aggregate-equivalent 系统 τ_trap 排序反转）。同步按 loop §14 产出 Round 1 正式汇报（在结果齐后）。

Gate A 通过前**不做**：Stage B/C/D、TRU-Mem 任何实现、240–320 families 扩展。

## 轮次文件状态

| 文件 | 状态 |
|---|---|
| RESEARCH_LEDGER.md | Gate 0 已写入 |
| LITERATURE_COLLISIONS.md | 待扫描结果 |
| BOTTLENECK_PROFILE.md | 待 pilot 数据 |
| CAUSAL_STRUCTURE_AUDIT.md | 待 Gate A 后强 probe 审计 |
| HYPOTHESIS_CANDIDATES.md | 待 Gate A/B 后（Loop Step 4） |
| SELECTED_HYPOTHESIS.md | 待 Loop Step 5 |
| GATE_PROTOCOL.md | 待选中假设后预注册 |
| GATE_FINDINGS.md | 待 Gate A 判定 |
| DECISION.md | 待 Gate A 判定 |
