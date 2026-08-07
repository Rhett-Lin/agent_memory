# DECISION — 轮次决策记录

## Round 1 决策链

| # | 决策点 | 依据 | 结果 | 日期 |
|---|---|---|---|---|
| 1 | 立项判定 | Gate 0 新颖性核验（5.5–6/10，PROCEED WITH CAUTION） | 进入 Round 1，目标仅限 pilot 识别可行性 | 2026-08-07 |
| 2 | [UNVERIFIED] 处置 | agent-0 三方核验 | "When Memories Collide" verified → Partial 碰撞并入；RC-MemStop 判定机器生成 → 移除禁引 | 2026-08-07 |
| 3 | 90 天文献扫描 | agent-1/-2 报告 | 两条 claim 均 SAFE（无直接碰撞）；Rocchi SSRN 与 SafeCommit 等新 Partial 已落档 | 2026-08-07 |
| 4 | Gate A | GATE_PROTOCOL.md §5 | **GO**（7B A11 大幅正 + τ_struct SIG+；3B τ_P×S SIG+；replay premium 两模型显著；6/6 前置通过，1 项 TOST 弱项转 Gate B） | 2026-08-07 |
| 5 | Gate B | CAUSAL_STRUCTURE_AUDIT.md | 已触发，执行中（强 probe + 难度稳健性 + 连续-S） | — |

## 止损计数

Gate A/B 连续 NO_GO：0 ｜ 总连续 NO_GO：0（达到 3 / 6 分别触发 loop §15 的修正与终止程序）

## 当前结论

待 Round 1 pilot 数据。预登记承诺：**GO 与 NO_GO 同等详细记录；不得为保持 loop 运行而放宽 GATE_PROTOCOL.md 已登记阈值。**
