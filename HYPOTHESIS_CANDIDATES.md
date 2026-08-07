# HYPOTHESIS_CANDIDATES — Round 1 收敛（Loop Step 4）

> 生成日期：2026-08-08，Gate B GO 之后。三个假设全部以 pilot 实测数据为锚（不得照搬 H1–H8 原文）。评分明细见文件末尾，选定结果见 SELECTED_HYPOTHESIS.md。

---

## Hypothesis ID: HA — Replay Dominance（Aggregate-inflation hypothesis）

#### 问题
当前 7B/3B 的表观 memory gain（A11 vs N = +18.6pp / −0.011）与 clean structural transfer（A10−A00 = +9.2pp / −6.6pp）在 pair 级正交分解下差距悬殊。**已发表系统报告的 total memory gain 中，replay-like 复用究竟占多大比例；structural share ρ 是否系统性地 <0.5？** 这个问题 Memory Transplants 无法回答（其因子是系统/域级 architecture×content，无法在 memory-target pair 级识别 replay-like 与 structural 的占比）。

#### 因果设计
Stage A 扩展：240 families（pilot 通过 Gate B 后唯一允许的规模动作），8 archetype × 30，每 family 4 siblings；cells A00/A01/A10/A11/N/Q 同 pilot；新增 14B 规模点（4bit 两卡）到 1.5B/3B/7B 序列。固定注入、family-split 50/20/30、预注册 ρ = τ_struct / (τ_struct + τ_replaylike)（τ_struct=A10−A00、τ_replaylike=A11−A10，family-cluster bootstrap und Holm）。

#### 经验依据
pilot 中 replay premium 两模型 SIG+（3B +0.102、7B +0.144）；τ_struct 仅 7B SIG（+0.092，trimmed +0.105）；ρ(7B) = 0.092/(0.092+0.144) ≈ 0.39 <0.5。

#### 核心机制
若 ρ 稳定 <0.5 且跨模型/生成器保持，则现有 memory benchmark 的"agent learns from experience"叙事大幅转变为"agent replays surface-matched episodes"——改变部署选择（值得为 replay 设计专用 cache 而非学习 admission）。

#### 识别必要性
aggregate gain 不可加总分解；M0–M6 ladder 把 representation 与 content 混在一起；Memory Transplants 的因子不含 surface-similarity 维，无法分 replay-like/structural。

#### 与已知碰撞论文的比较
- Memory Transplants：其 2×2 是 architecture×content；本假设的 replay/structural 分解是 content 内 P×S 分解 → 互补。
- Rocchi SSRN：bank×agent paired audit，因子不含 program-match×surface → 正交。
- Proced-Mem：embedding cliff 是检索表现，不是行为层 uplift 分解。
- Bridge Evidence / MemAudit：counterfactual utility 逐条记忆，不做 replay/structural profile 分解。

#### 最小 Gate
不扩到 240：在 pilot 40 fam 上按 8 archetype × 两域拆分结构，检验 ρ 是否在 hold-out archetype 上仍 <0.5；3 个 seeds 已有，补 2 个 → 5 seeds（增量 ~3200 rollouts）。

#### Kill condition
ρ 的 95% CI 覆盖 0.5，或 τ_replaylike 在扩展后失去显著性，或 archetype-holdout 上符号反转 ≥3/8。

---

## Hypothesis ID: HB — Capability × Transfer-Mode 符号反转

#### 问题
Memory Transplants 报告"弱模型 memory effect 更大"已成新共识。**把 transfer 分解为 replay-like 与 structural 后，'弱模型受益更多'是否仅在 surface-matched 条件下成立；弱模型的 structural memory 增益是否为负？** H7 的可检验版本。

#### 因果设计
1.5B/3B/7B/14B 四点规模 × pilot Stage A 网格（已有 1.5B-部分、3B、7B；补 14B 全量 + 1.5B 全量）；estimand：τ_struct(scale) 与 τ_replaylike(scale) 的单调/符号结构；logistic mixed model 含 scale×P×S 三向交互（family 随机截距）；Holm 校正。

#### 经验依据
3B τ_struct −0.066（Holm n.s. 但点估计负）vs 7B +0.092（Holm SIG）；3B τ_P×S +0.113 SIG（弱模型增益只在 S=1 下实现）；饱和模型中 3B P 系数 −0.007 vs 7B +0.165 SIG。

#### 核心机制
若成立，"memory 对小模型更有用"被修正为"memory 只在表面匹配时对小模型无害、对大模型才会出现干净结构迁移"——直接修改 Memory Transplants 的最重要结论。

#### 识别必要性
Transplants 未分 replay/structural，无法发现符号反转（其弱模型效应是把两类混合后的总量）。

#### 与已知碰撞论文的比较
- Memory Transplants：正面矛盾对象（+15pp vs +7pp 的总量结论）。
- More Skills, Worse Agents：skill shadowing 是 library 规模效应，非模型 scale×P 交互。
- Memory Transfer Learning：跨域 coding 单模型族，无符号反转分解。

#### 最小 Gate
补 14B（4bit）40 fam × 6 cells × 4 seeds ≈ 3840 rollouts；检验 7B→14B 的 τ_struct 是否继续为正且增大；不需 1.5B 全量。

#### Kill condition
14B τ_struct CI 覆盖 0 或与 7B 无差异（CI 重叠）；或 3B τ_struct 在扩展样本下转正。

---

## Hypothesis ID: HC — Published write-path systems 的 F-MED profile 逆序

#### 问题
**两个 aggregate-equivalent 的已发表 memory 表示系统，在 τ_struct 与 τ_trap 上是否显著反向排序？** 这是技术报告 §13 列为"最重要两张主图"之一、也是 Gate C 的核定条件。pilot 只跑了固定注入的 procedural card 表示，尚无系统间比较。

#### 因果设计
在同一 harness/候选集/预算下实现 5 种已发表 write-path 表示系统（按原论文描述忠实复刻表示层，不声称复刻其完整管线）：
1. raw episodic trajectory（Reflexion/ExpeL 式）；
2. summary memory（通用 LLM 摘要）；
3. procedural card（Memp/AWM 式，即 pilot 现有表示）；
4. MCMA 式多层 abstraction（底层轨迹 + 高层 insight 双层，按原文 hierarchy 描述）；
5. ReMe 式 distill+utility-refined procedural（按 ACL2026 Findings 的 f≥5 且 u/f<0.5 删除规则做 write-side 版本）。
每系统在相同 source episodes 上生成各自表示的 card，注入到同一 agent harness，测完整 Stage A profile（τ_context/τ_struct/τ_trap/τ_replaylike + harmful flip）；2 模型规模；profile 间排序用 cluster bootstrap 差异 CI 判定。

#### 经验依据
pilot 已证明：(a) 同一表示内两模型方向相反（profile 对表示/能力敏感）；(b) near-miss 在 delete_after_capture archetype 上翻转率最高——不同系统对程序细节的保真度不同（summary 最可能丢 archive 步骤 → τ_trap 放大；procedural/hierarchy 保留 → τ_struct 增大），有可解释的分歧张力；(c) sim→uplift 相关 ≈0 说明表示间差异不会被"内容相似度"抹平。

#### 核心机制
若 raw/summary 的 τ_struct 显著低于 procedural/MCMA，而 τ_trap 与 harmful flip 显著更高，且两系统 aggregate gain 相近，则"该选哪个 memory 表示"成为由 causal profile 而非 aggregate 决定的部署问题——同时向公众普遍的"报告 total gain 即可"做出 methodologically 的反驳。

#### 识别必要性
只有 P×S 正交 + evaluator-only oracle 能给"系统的哪一环产生 replay/structural/trap"归因；aggregate 对比或 leave-one-out 只能证明"系统 A 比 B 好 1.3pp"。

#### 与已知碰撞论文的比较
- Rocchi SSRN（bank×agent）：不同因子，无 write-path 表示维。
- Memory Transplants（5 系统 aggregate）：报告过系统对比但未做 causal profile 分解；本假设是对其结果的"profile 重分析"，正面互补且必须直接实现其 2×2 作为方法基线（预注册内写明）。
- AFTER/Mem2ActBench：真实系统横评，无随机化 P/S。
- ReMe/MCMA/Memp/AWM：系统的被比较对象（忠实复刻表示层），非概念覆盖。

#### 最小 Gate
3 系统（raw / summary / procedural）× pilot 40 fam × N/Q/A-cells × 4 seeds × 1 模型（7B）≈ 3×3840 rollouts ≈ 同 pilot 的 1/4；若 raw vs procedural 出现 τ_struct 方向反转或 |Δτ_struct| > 8pp 且 CI 分离 → 升级完整 5 系统 + 14B。

#### Kill condition
三系统的 F-MED profile 形状统计不可分（所有两两对比 CI 覆盖 0）；或 summary 表示无法生成合格卡（manual spot check 失败率 >30%）。

---

## 评分明细（Loop Step 5，0–5 分）

| 维度（权重） | HA | HB | HC |
|---|---|---|---|
| N Novelty（0.25） | 3：replay/structural 分解净增量真实，但"增益被 replay 放大"近邻多 | 3：与 Transplants"弱模型受益更多"正面交锋，分解后反转属新 | 4：profile-divergence 落点是无人占据的（Bank×agent 与 aggregate 对比均非 causal profile） |
| I Identification necessity（0.20） | 4：分解必须靠 P×S 正交 | 4：符号反转只能在分解下显形 | 5：系统归因没有替代设计 |
| H Headroom（0.20） | 4：ρ(7B)≈0.39 直接支持 | 3：3B 负号未达 Holm，反转待 14B 确认 | 4：表示间机制张力可解释且与 pilot archetype 异质性一致 |
| F Feasibility（0.15） | 5：仅样本扩展 | 5：补 14B 单档 | 3：需实现 3–5 个表示系统 |
| B Baseline coverage（0.10） | 2：与 Transplants 互补论证已大体完成 | 3：正面矛盾很硬但需复现他们 2×2 | 3：系统需忠实复刻，工作量与复刻风险并存 |
| S Statistical rigor（0.10） | 4：estimand/推断链已跑通 | 4：同 HA | 4：profile 对比沿用 pilot 管线 + 系统间多重校正 |
| **总分** | **3.70** | **3.60** | **3.95** |

淘汰触发检查：三者均无 N<3 / I<3 / H<3、无未解决直接碰撞、均可在 A5000 frozen backbone 完成、均非"仅更多 nested factors"。

**选择：HC**（Gate C 的 profile-divergence 是硬条件，只有 HC 直接攻击它；HA/HB 留存为 paper 次级发现，不占单独方向开发资源）。

---

# Round 2 追加评分（2026-08-08，H-C NO_GO 之后）

新候选来自已归档 H-C 的次级信号（**hypothesis-generating evidence，不得用同数据确认**）+ GPT-5.6 指定的最高杠杆设计。与 HA/HB 并排重新评分（HA/HB 分数沿用 Round 1）。

## Hypothesis ID: H3（新）— representation × semantic-coverage 2×2 factorial on τ_replaylike

#### 问题
H-C 中 raw-prefix 的 replay 溢价显著低于 procedural（−15.8pp）。这是**表示形式**（transcript vs script）、**语义覆盖**（决策步骤是否保留）、还是二者交互造成的？该混杂是 H-C 无法给出机制结论的根因，也是"原始轨迹 vs 蒸馏程序在部署中的真实差异"的干净化版本。

#### 因果设计
新鲜 2×2：factor A surface form（transcript/dialogue vs imperative/script）；factor B semantic coverage（complete decision steps vs matched-prefix 缺失）。所有卡片从同一 canonical proposition set 组装：相同事实集、相同顺序、同 write-decision 与 finish 存在性、同来源、同 token 量（尽可能等长）、同 harness/位置。生态第 5 臂：原 300-token 硬截 transcript（对应 H-C 的 raw）。网格：新确认集（utilize pilot 的 held-out archetype/新 family seed 的 20–40 families，不重评分旧观测）× 2 覆盖 × 2 形式 + 生态臂，主 estimand τ_replaylike，n per cell 按 pilot family-level covariance 功效分析定（优先加 family）。两 estimand 分别预注册：deployed-policy effect、pure-form effect。

#### 经验依据
H-C：Δτ_replaylike(raw−procedural) −0.158 [−0.239,−0.080]；raw 卡仅 48–59% 含写步骤、8/640 含 finish（候选混杂）；summary 居中。

#### 核心机制
若纯形式效应在完整覆盖下存在 → 表示本身影响回放兑现（部署应强制 script 化）；若仅在截断覆盖下出现 → H-C 差异主要是覆盖假象；若只在预算帽下 → 系统级预算结论。三者任一都有明确论文落点。

#### 识别必要性
单臂修复（如只加预算）混合多个维度；只有同内容-异形式-异覆盖的完全析因能分离。现有工作（Memp/AWM/raw-replay 对比）没有做过同内容析因；Rocchi 的 bank×agent、Memory Transplants 的 arch×content 都不含语义覆盖维。

#### 与已知碰撞论文的比较
- Rocchi：bank×agent，无形式/覆盖维；
- Memory Transplants：arch×content，不含 coverage；
- Proced-Mem/Memp 等：表示比较但没有同 canonical content 的 confound 控制；
- 无直接 Collision；Partial = H-C 已归档数据仅作 motivation。

#### 最小 Gate
8 families（每 archetype 1 个）× 5 arms（2×2+生态）× 4 sib × 3 seeds × 7B ≈ 480 rollouts 的构造有效性试验：验证四臂内容一致性（same proposition coverage）与长度均衡 <5% SMD；不过此检不进入主实验。

#### Kill condition
构造无法满足"同 canonical content"（transcript 自然语言不可避免引入内容漂移）→ 放弃 pure-form 改只报 deployed-policy；或主实验中四臂 τ_replaylike 两两 CI 全部重叠。

## Round 2 评分

| 维度 | HA 3.70（沿用） | HB 3.60（沿用） | H3 |
|---|---|---|---|
| N (0.25) | 3 | 3 | 4 |
| I (0.20) | 4 | 4 | 5 |
| H (0.20) | 4 | 3 | 4 |
| F (0.15) | 5 | 5 | 4 |
| B (0.10) | 2 | 3 | 4 |
| S (0.10) | 4 | 4 | 4 |
| **总分** | **3.70** | **3.60** | **4.20** |

淘汰触发检查：H3 无 N<3/I<3/H<3，无未解决直接碰撞（已复核），A5000 可行，非"仅更多 nested factors"（混杂分离是唯一目标）。
**Round 2 选择：H3。**
