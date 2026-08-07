# H-C Minimal Gate 负结果分析备忘录（2026-08-08，先行分析 → 待 GPT-5.6 讨论）

> 触发治理规则 §1（RESEARCH_LEDGER.md）：出现负结果，先自行分析，再与 GPT-5.6 讨论，讨论前冻结下一步动作。本文是"自行分析"部分。

## 1. 预注册判据与实测

H-C-3 GO 判据（GATE_PROTOCOL Part II §8/§11）：
A. 任一对系统 |Δτ_struct|≥8pp 且 cluster-bootstrap 95% CI 不含 0；
B. aggregate-equivalent（A-cells 平均成功率差 <3pp）的两系统在 τ_trap 上排序方向相反且各自 CI 支持。

实测（7B，3 系统 × 3840 rollouts，6 对比 Holm 校正）：

| 对比 | Δτ_struct [CI] | Δτ_trap [CI] | 判据命中 |
|---|---|---|---|
| raw − procedural | −0.050 [−0.120,+0.028] | −0.097 [−0.206,+0.011] | A：差 3pp 且 CI 跨 0；B 见下 |
| summary − procedural | −0.042 [−0.111,+0.034] | −0.033 [−0.108,+0.045] | 均 n.s. |
| raw − summary | −0.008 [−0.085,+0.064] | −0.065 [−0.155,+0.021] | 均 n.s. |

- 判据 A：**不成立**（最大 |Δτ_struct| 5pp，CI 均跨 0）。
- 判据 B：raw 与 procedural aggregate 等价（−2.9pp，CI 内）。τ_trap：raw −0.016 [−0.109,+0.077] vs procedural +0.081 [−0.002,+0.172]。符号相反但两者 CI 均跨 0，排序反转**不显著** → 不成立。

**按冻结判据，H-C minimal gate = NO_GO**（'incremental' 档：replay premium 方向性差异存在但未反转 trap/struct 主 estimand）。

## 2. 同时出现的、不应被忽略的显著信号

1. **Δτ_replaylike(raw − procedural) = −0.158 [−0.239,−0.080], p_boot=0.000（预注册 profile 元素之一，非主对比）**：回放溢价对表示层敏感。raw A11=0.584 ≈ raw A10=0.598 ≈ N；procedural A11=0.733。aggregate 等价下 replay premium 差 15.8pp，这**正是** H-C 想找的系统间 profile 分裂的实证——只是出现在 replay 维度而非 struct/trap 维度。
2. summary（LLM 摘要）在所有 estimand 上位于 raw 与 procedural 之间且更接近 procedural（A11=0.711），支持"摘要保留了大部分程序信息"的常识但**首次给出数值化 profile**。

## 3. 数据层必须登记的三个瑕疵

1. **raw 卡全部顶格截断**：640/640 张 raw-card 恰好 300 tokens（硬截），仅 48–59% 含写操作步骤，8/640 含 finish。"raw 注入"实际 ≈"片段前缀"，经常丢掉决策步骤。τ_replaylike 的差异**部分是这个截断机制的必然结果**，部分可能是真表示效应——两者在当前设计下不可分。
2. **oracle_fallback 超阈**：29.4%（188/640）的 raw 卡轨迹来自 oracle plan 而非模型 rollout（预注册口头阈值 <5%）。这些卡更接近"最优解教材"而非 Reflexion 式经验，方向性上应**增强** raw 的表现；raw 仍无 replay premium，说明截断/表示效应真实占据主导。fallback 集中在建模更难的家庭（P4 purge 类）。
3. **QA 抽查**：10/10 summary 卡审计，1/10 顺序颠倒轻微缺陷（item 7 把 delete-children 与 delete-parent 次序写反），fail rate 10% < 30% kill 阈值。**通过但登记**。

## 4. 我对成因的判断（提交 GPT-5.6 评审的要点）

1. 判据 A/B 未达成是**设计真实的回答**：τ_struct 与 τ_trap 对这三类表示层不敏感——因为三者都携带同源的程序语义摘要。τ_struct 的差异上限就是"信息保真度"差异，而 300-token 预算下三者保真度相近。
2. τ_replaylike 的差异有**语义内容**：procedural/summary 以"可执行脚本"形式呈现（照抄即可执行），raw 以观察记录呈现（需要读者重构计划）+ 截断丢决策 → 回放溢价只在脚本化表示下实现。这与 pilot 中"7B 增益主要在 A11（surface-matched procedural replay）"互相印证，并可塑造成一个新的更窄发现："在等预算下，**仅结构化/脚本化表示能实现 replay 收益；原始轨迹即使表面匹配也无法兑现**"。这仍是系统间分歧，只是分裂轴是 replay 实现而非 struct/trap。
3. 判据 B 的 τ_trap 排序方向相反但 n.s.（power 不足），不宜硬写"H-C GO/分歧已证"。

## 5. 提交 GPT-5.6 的三个问题

1. 在冻结判据下应如实记为 NO_GO。下一步哪条更值：(a) 修复 raw 构建缺陷（预算 600-800 token 的非等预算臂，或改为 raw 的可执行化编辑版）后重测，与等预算臂并列为"预算×表示"的 3×3 设计；(b) 直接把 replay-premium 的表示敏感性升格为新假设（修改而非伪造 discovery），走 Loop Step 4 重新评分；(c) 记 NO_GO 回 Loop Step 1 按 §12 Direction D 转向。
2. 当前证据是否已足以支撑一篇"测量正确性"为核心的小论文（CausalMemBench + F-MED profile + replay-representation 效应 + 全部审计），还是先补 5 系统与 3B 完整臂。
3. GPT-5.6 对"raw 截断污染 τ_replaylike 差异"这一混杂的最干净拆解实验设计是什么（避免再犯我的预算腐蚀问题）。

## 6. 冻结声明

在 GPT-5.6 讨论结论落笔前，不启动任何新实验、不修改 SELECTED_HYPOTHESIS、不写 Gate 判定结论。
