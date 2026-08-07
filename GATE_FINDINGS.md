# GATE_FINDINGS — 轮次级判定记录

> 判定阈值见 `GATE_PROTOCOL.md`（Gate A）与 `CAUSAL_STRUCTURE_AUDIT.md`（Gate B），均在数据产生前登记。本文件只填数与判定，不改阈值。

## Gate A — Pilot Identification Gate（Round 1）

判定日期：2026-08-07
数据：7680 rollouts（40 fam × 4 sib × 6 cells × 4 seeds × 2 模型），RelationalOps 单环境，fixed injection。

**前置合规检查**

| 检查项 | 阈值 | 实测 | 通过 |
|---|---|---|---|
| parseable action 率 | >90% | 3B 98.9%（34186/34560）、7B 99.6%（30362/30491） | ✅ |
| compliance（memory 被读取） | 启发式有信号 | step_action_coverage：A01=0.141、A11=0.163、A10=0.001、A00≈0、Q=0（高相似 cell 与低相似 cell 的对比模式符合设计预期；A10 低 echo 是因为内容本就低相似；**该启发式偏弱，已列入 Gate B 补强**） | ✅（弱） |
| oracle 合法终态 | 100% | 800/800 | ✅ |
| N 条件成功率 | 30–70% | 3B 42.0%、7B 54.7% | ✅ |
| 弱 leakage probe | 无 treatment artifact | sim→S AUC=1.000（构造使然，不计）；sim→P AUC=0.605；length→P AUC=0.512 | ✅（0.605 标记转 Gate B 强 probe） |
| sibling 难度等价 TOST | ±7pp | 3B [−0.060,+0.063] 通过；**7B [−0.077,+0.038] 左侧越界、未通过** | ⚠️ 部分（转 Gate B 处置） |

**主 estimand（family-cluster bootstrap 10,000 reps 求 bootstrap-p，Holm m=8 校正；CI 为 2,000-rep percentile）**

| Estimand | 3B 估计 [CI] | 7B 估计 [CI] | Holm 校正后判定 |
|---|---|---|---|
| τ_context = Q−N | −0.019 [−0.067,+0.031] | +0.027 [−0.023,+0.080] | 两模型均 n.s.（context/format effect ≈ 0，理想基线行为） |
| **τ_struct = A10−A00** | −0.066 [−0.131,−0.002] | **+0.092 [+0.036,+0.152]** | **7B SIG（adj p=0.0048）；3B 点估计为负但 Holm 后 n.s.（adj p=0.29）** |
| τ_trap = A01−A00 | −0.011 [−0.072,+0.047] | +0.081 [−0.006,+0.173] | 均 n.s.（7B 方向为正，反直觉，见 BOTTLENECK §3-2） |
| **τ_P×S** | **+0.113 [+0.041,+0.189]** | +0.063 [−0.031,+0.156] | **3B SIG（adj p=0.020）；7B n.s.** |

辅助（secondary，不纳入 Holm）：
- τ_replaylike = A11−A10：3B +0.102 [+0.039,+0.161]、7B +0.144 [+0.087,+0.200]，两模型均 SIG+——**replay-like premium 是两模型最稳健的效应**。
- A11 vs N：7B +0.186 [+0.114,+0.261]；3B −0.011 n.s.
- paired harmful flip（A01）：3B **9.2→18.8%** [15.1,22.5]；7B **9.2%** [6.3,12.0]。
- 图3 sim-uplift 相关：Spearman 3B −0.020／7B +0.074（≈0）。

**判定：GO**

**触发的 GO 条款及证据**：

1. loop §7 GO-1「至少一个稳定、可解释的 cell difference」——多项满足：
   - 7B 的 **A11 大幅正（0.733，vsN +18.6pp）、A10 小正（+0.042 n.s.，τ_struct 经 Holm 仍 SIG +9.2pp）、A01≈A00** —— 即"表观 memory gain 主要来自 surface-matched replay，clean structural transfer 只占其中一小部分"的 **benchmark-inflation 信号**；
   - 3B 的 **A10 点估计为负、τ_P×S SIG+、replay premium 显著** —— 弱模型增益更依赖表面匹配；
   - 两模型 τ_struct 方向相反（3B −6.6pp vs 7B +9.2pp）—— 模型×cell 交叉（H7 方向）的初步证据。
2. loop §7 GO-2「Compliance 正常」——parseable 率与 compliance 启发式支持（见上表，标注弱启发式局限）。
3. loop §7 GO-3「弱 probe 无明显 artifact」——满足（sim→P 0.605 转强 probe 复核）。

**风险登记（不阻断 GO，转入 Gate B）**：
- 7B difficulty TOST 未过（左端 −0.077 vs margin −0.070）→ Gate B 必须做难度协变量/family 随机效应的稳健性复核；
- τ_trap 在 7B 方向为正（n.s.）→ 若 Gate B 复核后仍为正，需要修正 H4 的表述（near-miss 并非普遍有害，其危害集中于弱模型或特定 family 子群——3B flip 18.8% vs 7B 9.2%）；
- τ_struct 在 3B 为负 → 与 H1（exact>structural）一致但与"结构迁移普遍存在"的乐观读法相抵触，Gate B 需确认非难度/模板 artifact。

## Gate B — 因果有效性 Gate（2026-08-08）

**判定：GO。** 六项审计与补救全部通过（详见 `CAUSAL_STRUCTURE_AUDIT.md` §2/§6）：

| # | 审计项 | 结果 |
|---|---|---|
| 1 | Program equivalence 一致性 | LLM judge 0.25（工具失效，红色警报登记）→ 签名 8/8 相等 + 不一致逐案人审 = 标签结构正确；后续等价标注转人工 |
| 2 | Executable consistency | 800/800 + 抽样重跑 160/160 |
| 3 | 强 leakage probe | τ_struct 平面 AUC≈0.35–0.38 干净；τ_trap 平面 0.996 登记为"near-miss 在文本内可读"而非泄漏；family_idx 0.087 vs 0.025 |
| 4 | 难度等价 TOST | 3B 过；7B 初测未过 → 修剪 8/160 单元后通过且 τ_struct 反增至 +0.105 SIG |
| 5 | 连续-S 敏感性 | 二值化结论以"桶边界跳跃"形式复现，支持 P（非连续 S）驱动 |
| 6 | 效应存在性 | 7B τ_struct Holm SIG+（+0.092 / +0.105 trimmed）；3B τ_P×S SIG+；τ_trap 修剪后从 n.s. 转为 SIG（+0.099） |

**审计带来的叙事修正（写入后续 GATE_PROTOCOL 与论文）：**
1. τ_struct 机制降级为"操作模板/步骤 schema 迁移"，**禁止**写成"模型识别出同一程序"（judge 判错率 100%）；
2. 效应集中于 delete_after_capture 与 two_row_transfer 两个 archetype（异质性真实，主实验需 240+ family 提高 archetype 级精度）；
3. LLM probe 可捕获 7B τ_struct 的 0.75 → F-MED 的识别增量必须以"剩余 25% + 行为层证据"为论据，不能空称 similarity 无关；
4. τ_trap 语义为"陷阱在文本内可读但 agent 仍中招"——harmful flip 是陷阱有效性的直接证据。

## Gate C — 待启动（Loop Step 4/5 之后）

前置：恰好三个假设的生成与评分（Loop Step 4/5）→ 选定唯一假设预注册 → Memory Transplants/Proced-Mem/STITCH 直接对比。

## Gate D — 未触发

TRU-Mem 未启动（按 loop §16 禁令）。
