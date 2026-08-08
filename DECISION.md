# DECISION — 轮次决策记录

## Round 1 决策链

| # | 决策点 | 依据 | 结果 | 日期 |
|---|---|---|---|---|
| 1 | 立项判定 | Gate 0 新颖性核验（5.5–6/10，PROCEED WITH CAUTION） | 进入 Round 1，目标仅限 pilot 识别可行性 | 2026-08-07 |
| 2 | [UNVERIFIED] 处置 | agent-0 三方核验 | "When Memories Collide" verified → Partial 碰撞并入；RC-MemStop 判定机器生成 → 移除禁引 | 2026-08-07 |
| 3 | 90 天文献扫描 | agent-1/-2 报告 | 两条 claim 均 SAFE（无直接碰撞）；Rocchi SSRN 与 SafeCommit 等新 Partial 已落档 | 2026-08-07 |
| 4 | Gate A | GATE_PROTOCOL.md §5 | **GO**（7B A11 大幅正 + τ_struct SIG+；3B τ_P×S SIG+；replay premium 两模型显著；6/6 前置通过，1 项 TOST 弱项转 Gate B） | 2026-08-07 |
| 5 | Gate B | CAUSAL_STRUCTURE_AUDIT.md §6 | **GO**：六项审计全通过（强 probe 关键平面干净、难度修剪后 TOST 通过且效应增强、连续-S 复现、签名 8/8 相等 + oracle 160/160；LLM judge 失效登记为教训） | 2026-08-08 |
| 6 | H-C minimal gate | GATE_PROTOCOL Part II §11 冻结判据 | **NO_GO**：|Δτ_struct| 最大 5pp 且 CI 均跨 0；τ_trap 排序仅点估计反转 + 修正推断不显著。GPT-5.6 确认维持 NO_GO；次级信号 Δτ_replaylike=−0.158 记为 hypothesis-generating（截断/覆盖混杂未分），不作为既定发现 | 2026-08-08 |
| 7 | H3 form×coverage 析因（fresh 32 fam × 2 models，9216 rollouts） | GATE_PROTOCOL Part III §13 冻结判定树 | **formal NO_GO + informative clarification**：冻结 GO 判据（ε_form 显著）未达；方向反（transcript ≥ script）；cov 覆盖对比 Holm m=8 下全 n.s.；robust 发现：完整 transcript 在两模型下 replay 收益实质性非零（TOST 拒绝等价）；H-C 异常记为"对覆盖/截断敏感"，不代表示形式结论。GPT-5.6：NO_GO 入账，下一步停实验写测量论文 | 2026-08-08 |

## 止损计数

Gate A/B 连续 NO_GO：0 ｜ 假设层连续 NO_GO：**2**（H-C minimal gate + H3 form×coverage 析因，均 2026-08-08；达到 Gate A/B 3 次 / 总计 6 次分别触发 loop §15 修正与终止程序）

## 当前结论

**完成位置（2026-08-08）**：loop §11 最终论文潜力审查通过 → 贡献计 2/3（identification design + 会改变结论的经验发现）；Gate C-lite cond1+cond2 通过 → main 档路径铺通；**`PAPER_PLAN.md` 已产出**（measurement+identification 主线，全差异化矩阵 VERIFIED）。证据链 + 负结果处置（两轮 GPT-5.6 外部讨论：H-C→019fdba5、H3→019fde39）与 §13 全部归档文件齐备。

预登记承诺重申（全程有效）：**GO 与 NO_GO 同等详细记录；不得为保持 loop 运行而放宽 GATE_PROTOCOL.md 已登记阈值。**
