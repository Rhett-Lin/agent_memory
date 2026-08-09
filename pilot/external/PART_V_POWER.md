# Part V — Power Artifact(冻结于分析前,2026-08-09)

## 输入假设(全部来自既有数据或冻结决定)

- 先验 discordance(上次 ALFWorld 检查,36 triads):q = 9/36 = **0.25**。
- 组内相关(同一 target 4 seeds):ICC ≈ **0.35**(上次数据粗估)→ 4 seeds 的 design effect DE ≈ 1 + 3×0.35 ≈ **2**。
- Power alternative(冻结):E-harm 真实 +10pp;观测下限 +5pp 仅作 GO 的声明门槛,不作为功效规划点(真实效应恰好在声明门槛时,点估计约半数时间低于自身期望,80% power 渐近不可达,一轮裁决已示)。
- 显著性口径:Holm step-down 最坏 α = .05/3(单侧)。

## 网格论证

- 独立配对二元(sign-test 近似,+10pp alternative,α=.05/3 单侧)所需独立三元组 ≈ **229**。
- 480 target-seed triads(120 targets × 4 seeds)÷ DE≈2 ≈ **240 独立当量** ≈ 覆盖 229,边际 ≈ **82% power**。
- E-serve / E-oracle 的功效地位以"出口与功效的关系"一节第 2、3 条为准(本节先前版本的旧表述已作废):精确等式下 E-serve 标准化功效与 E-harm 相同,允许 ≤5% gate 误差时为条件性且可能更低;E-oracle 无功效保障;两者未过均 → PARTIAL,不作负面推断。

## 出口与功效的关系(冻结)

- 完整 60+60 网格 = 上述功效主张生效的前提;不完整 → NOT_ESTIMATED。
- 若真实 E-harm 仅 +5pp(n_eff=240,q=.25,Holm 最坏 α=.05/3,精确配对计算),power 约 **24%**(此前写的 ~42% 对应未校正 α=.05,已更正)→ 完整网格下小效应大概率落入 INCONCLUSIVE 而非 paper-relevant NO_GO。该不对称性登记在案,接受。
- E-serve 在"G-struct≡oracle 且 G-S 双收"的精确等式下,估计与 SE 同减半,标准化检验与功效与 E-harm 相同;但允许 ≤5% gate 误差时等式不成立,**E-serve 功效为条件性,可能更低;未过即 PARTIAL(接受)**。
- E-oracle:R-admission 与 X-rejection 各允许 5% 误差时,gap 最坏可逼近 −5pp 边际——**无功效保障;未过即 PARTIAL**,不作 E-oracle 负面推断。

## 复算方式

分析脚本 `pilot/external/analyze_gate.py`(实现期 commit hash 入档)在报告头部重算本节关键数字(q、ICC、DE、独立当量),与冻结值并列;实测 ICC 若 ≥0.6,需如实披露有效样本量低于规划的后果(仅披露,不改判据)。
