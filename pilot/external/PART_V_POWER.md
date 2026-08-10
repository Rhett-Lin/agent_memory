# Part V — Power Artifact v2(2026-08-10 冻结,Part V-A 配套;取代 08-09 版)

## 输入假设

- 先验 discordance:q = 9/36 = **0.25**(上次 ALFWorld 检查)。
- 组内相关:ICC ≈ 0.35 → 4 seeds 的 design effect DE ≈ 2。
- Power alternative:E-harm 真实 +10pp;显著性口径 Holm 最坏 α = .05/3,单侧。
- **计划功率声明(裁决要求的诚实措辞):E-harm 是唯一前瞻功率端点;计划功率 ≈ 76–78%,低于 80%。E-serve/E-oracle 无功效保证,未过即 PARTIAL。**

## 网格论证(v2,Part V-A 规模)

- 独立配对二元(sign-test,+10pp,α=.05/3 单侧)所需 ≈ 229。
- **400 target-seed triads(50 heat + 50 cool,×4 seeds)÷ DE≈2 ≈ 200 独立当量**,覆盖 229 的 87% → ≈ **76–78% power**。
- 真实 +5pp 时(200 当量)power ≈ **20%** → 小效应大概率落入 INCONCLUSIVE(与该出口设计一致)。
- E-serve:在 gate 决策精确继承下与 E-harm 同标准化检验;允许 ≤5% gate 误差时为条件性功效,可能更低 → PARTIAL 出口预载。
- E-oracle:parser 误差可使 gap 逼近 −5pp 边际——**无功效保障,未过即 PARTIAL**,不作负面推断。

## 与出口判定关系(冻结)

- 完整 50+50 model-only 网格是上述功率主张生效的前提;不完整 → NOT_ESTIMATED(Part V-A 最终性条款:随后直接关闭,不再做任何可行性修补)。
- 实测 ICC ≥ 0.6 时如实披露有效样本量缩水(仅披露,不改判据)。
- 分析脚本在报告头重算 q、ICC、DE、独立当量并与本文件并列。

## 复算方式

`pilot/external/partv/analyze_gate.py`(hash 见 FREEZE_MANIFEST)输出报告头:q、ICC(配对差 d=sN−sX)、DE、有效独立当量、以及与本文件的对比行。
