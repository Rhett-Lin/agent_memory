# NEXT_ACTION — Round 1 in flight（2026-08-07）

唯一下一步动作（按 loop §16 顺序）：

1. ~~文献扫描~~、~~环境~~ 已完成（扫描结论：两条 claim 均 SAFE，无直接碰撞；见 LITERATURE_COLLISIONS.md §C.0）。
2. 等 agent-3 完成 pilot 实现 + SPEC §8 smoke（program_dsl/env 已落盘并经我独立测试通过，剩生成器/harness/网格/分析模块）。
3. smoke 通过后：启动 mini-pilot 正式网格（40 families × 4 siblings × 6 cells × 4 seeds × 2 模型，Qwen2.5-3B/7B，strictly fixed-injection Stage A）。
4. rollouts 完成后：`analyze.py` 产出四张核心图 → 填 `BOTTLENECK_PROFILE.md` 数值区 → Gate A 判定 → 写 `DECISION.md` / `GATE_FINDINGS.md`。

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
