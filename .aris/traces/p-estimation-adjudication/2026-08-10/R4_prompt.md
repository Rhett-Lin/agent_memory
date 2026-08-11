# Round 4：用户提出借鉴 Xiong et al. 2026（experience-following）——"用后果反映 P" 的可行性裁决

用户读了 `ref/Xiong 等 - 2026 - How Memory Management Impacts LLM Agents.pdf`（ACL 2026, pp.623-645），
提议：既然拿不到 P，能否**间接反映 P**——(i) 构造判决标准，(ii) 微调一个 LLM。请裁决可行性。

## 1. 我读出的该文机制（请核对 `ref/paper.txt`）

- **addition**：`π(q,e) ∈ {0,1}` 决定这条执行是否入库。四档：fixed / add-all / coarse（C1=4o-mini,
  C2=4.1-mini, C3=**4.1-mini 在 300 条 judge 数据上微调**）/ strict（human oracle，实际用 ground truth 模拟）。
  结果：C3 用 300 条就显著优于未微调 coarse，接近 strict；add-all 与弱 coarse 会长期自我退化。
- **experience-following**：input similarity 高 → output similarity 高（RegAgent Pearson r≈1）。
- **history-based deletion**：`Φ` = 该 memory 历次被检索时的**下游执行效用均值**；被检索 ≥n 次且均值 <β 则删除。
  这就是该文"future task evaluations can serve as **free quality labels** for stored memory"的实现。
- **misaligned experience replay**：有些通过质量过滤的记录仍与当前任务目标不匹配 → 危害；
  他们用 KDE（图 6）**描述性**展示被删记录误差更高。

## 2. 我认为的结构性差异（请批判）

| | Xiong 的 `π(q,e)` | 我们的 P |
|---|---|---|
| 判定对象 | **一元**：这条执行本身对不对 | **二元关系**：memory m 与目标任务 x 是否同一程序等价类 |
| 标签来源 | 与 ground truth 比对，**写入时即免费** | 需 evaluator-only 程序等价 oracle，**部署态不存在** |
| 与我们的关系 | 我们的 **A01 near-miss 卡本身就是它自己任务的正确执行**——会满分通过他们的 addition 过滤 | 正是我们论文的对象 |

我的读法：**memory quality ≠ memory applicability**。他们控制的是 quality，我们的 near-miss 风险是
quality 过滤之后的**残差**。这是互补而非竞争。请裁决这个表述是否成立、是否可写进 related work。

## 3. 关键：我们有一个 Xiong 没有的资产，且我已实测

已核实：pilot 网格是**完整析因**——640 个 (family_idx, sibling_idx, seed) 实例 × 6 cells
（A00/A01/A10/A11/**N**/Q）× 2 模型全齐（每模型 3840 行，`meta.cell` 计数各 640）。
**每个实例都有 no-memory 反事实 Y(∅)**，所以任何动作空间 ⊆ {admit 4 张 A-cell 卡之一, abstain} 的策略
都能**精确离线评估、零估计误差**（不是 IPW/DR 估计，是查表）。

我从冻结 rollouts 直接重算（与归档数字一致：7B A11 0.733 vs N 0.547 = +18.6pp；7B A01 +3.1pp；3B A01 −5.8pp）：

| 7B | A11 (P1,S1) | A10 (**P=1**,S0) | A01 (**P=0**,S1) | A00 (P0,S0) |
|---|---|---|---|---|
| mean uplift vs N | +18.59pp | **+4.22pp** | **+3.12pp** | −5.00pp |
| paired harmful flip | 27/350=7.7% | 60/350=17.1% | 59/350=16.9% | 95/350=27.1% |
| helpful flip | 146 | 87 | 79 | 63 |

| 3B | A11 | A10 (**P=1**) | A01 (P=0) | A00 |
|---|---|---|---|---|
| mean uplift | −1.09pp | **−11.25pp** | −5.78pp | −4.69pp |
| harmful flip | 36.4% | 49.4% | 44.6% | 42.0% |

**读法（请批判）**：

1. 7B 上按平均效用排序恰好是 P 的正确序（A11>A10>A01>A00），但**决策关键边 A10 vs A01 只差 1.1pp**——
   无法设阈值；3B 上排序**直接反转**（P=1 的 A10 最有害）。→ 平均效用**分得开无关记忆、分不开近错记忆**。
2. 7B 的 A01 平均效用**为正**，所以 Xiong 式 history-based deletion **不会删掉近错卡**——而且从"最大化均值"
   的角度看这是**正确的**：它拿 59 次失败换了 79 次成功。
3. 但那 16.9% 的 harmful flip 是真实存在的风险，只是被 helpful flip 抵消掉了。
   → 我想说的 claim：**均值型效用管理在构造上看不见 flip 风险**；对删除/转账类高风险程序，
   这个交换不可接受。

## 4. 请裁决的四件事

**(a) 上述 claim 3 是不是同义反复？** "均值看不见尾部"本身是平凡的。我认为非平凡的部分是：
在真实 agent memory 数据上，**flip 风险与平均效用在近错卡上系统性解耦**（A01：+3.1pp 均值 / 16.9% 翻转），
且这恰好发生在 P 的决策边界上。请判定这是 finding 还是 trivially true，并给出如果要成为 finding
必须补的统计（paired bootstrap？与 A11 的 flip 率对比检验？逐 archetype？）。

**(b) 离线序贯模拟的合法性。** 我打算在完整析因上模拟 Xiong 的 addition + history-based deletion
（策略只用可观测量：sim、历史效用、检索次数；sealed P 只在最后评分）。但我们的设计是
**fixed-injection、静态候选池**，不是他们的动态自生成 memory bank：
- 我们的 memory 是 generator 造的卡，不是 agent 自己写的轨迹 → 没有 error propagation 通道；
- 我们没有"执行→入库→再检索"的闭环，所以 addition 那一半其实模拟不了。
请裁决：(i) 只模拟 **deletion/admission** 一半是否仍构成合法证据？(ii) 最大的效度威胁是什么？
(iii) 需要哪些前置声明才能不被指为"把静态网格伪装成 longitudinal 研究"？

**(c) 微调路线。** Xiong 的 C3 用 **300 条**微调就打赢未微调 coarse。用户据此提议微调一个 LLM 判 P。
我的判断是**不可迁移**：他们的目标是一元质量判定（标签写入时免费、分布内），我们的是二元关系判定
（标签需 oracle、且要跨未见失配机制泛化）；我们已实测 P̂ v1 全监督 640 对 → family-CV 0.935 但
**LOAO 0.590**（conditional_write 留出 0.408 低于随机），说明瓶颈不是模型容量而是标签枚举了机制。
你此前已裁"SFT judge = DEFER，SFT extractor = 最高优先"。请确认 Xiong 的 C3 证据**不改变**这一裁决；
若改变，请说明在什么条件下微调 judge 变得合法。

**(d) 优先级。** 这条"用后果反映 P"的线与上一轮裁定的 BLICC（5 天 CPU，接口信息上限普查）冲突还是互补？
若互补，谁先？请给一个不超过两周、CPU-only 的合并排序（GPU 现被其他项目占用）。

约束：只读，不改仓库。给判据与数字。若我第 3 节的重算有误请直接指出（脚本逻辑：按
`meta.(family_idx,sibling_idx,seed,cell)` 建表，uplift = mean(cell) − mean(N)，harmful flip =
N 成功且 cell 失败的实例数 / N 成功数）。
