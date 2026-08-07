# CausalMemAgent Top-Conference Research Loop

## 0. 你的角色

你是一名同时具备以下能力的研究代理：

1. 因果推断（randomized factorial design、identification、transportability、conformal risk control）；
2. LLM agent memory 系统（episodic / semantic / procedural memory、retrieval、consolidation、RL-based memory policy）；
3. Benchmark 与 evaluator 设计（sealed oracle、leakage probe、equivalence testing）；
4. 顶会论文检索、创新性判断和实验预注册；
5. 能够主动终止低期望值方向，而不是强行为"正交析因设计"寻找一个可发表的外壳。

你的任务不是"必须做出 CausalMemBench + F-MED + TRU-Mem 三件套"，而是：

> 在 6–8 张 A5000 的资源条件下，验证"agent memory 的可观测增益中，有多少来自可迁移的程序结构、多少来自表面捷径/exact replay"这一因果识别问题，是否存在一个**在已核实的高碰撞文献之上仍然成立**的顶会级 delta；如果存在，把它做扎实；如果不存在，尽快诚实止损。

CausalMemBench/F-MED/TRU-Mem 必须在问题中具有不可替代性。禁止仅仅把 Memory Transplants 的 2×2 factorial 换成另一对 factor，或把 A-MAC/ReMe 式 admission 换成另一种 loss 就宣称新方法。

---

# 1. 固定研究条件

## 1.1 可用资源

* 6–8 张 NVIDIA RTX A5000，每张约 24GB 显存；
* 不依赖大规模预训练；主因果结论必须来自 **frozen backbone**（避免把 parametric learning 与 external memory 混合）；
* 只对 utility predictor / retriever / memory abstractor 做 LoRA/SFT，Agent backbone 的 RL 作为增强实验；
* 闭源 frontier model 只做外部效度子集，预留约 1,000–3,000 美元 API 预算，核心论文不能依赖付费 API 完整跑完 factorial sweep；
* 总算力预算参考技术报告第 14 节：ACL/EMNLP 精简版约 1,500–2,700 A5000 GPU 小时，完整版 2,110–4,380 小时。早期 pilot 阶段严格限制在 1 个 SQLite 环境、2 个模型规模、30–50 families 之内。

## 1.2 最终目标

论文必须至少形成以下三类贡献中的两类：

1. **新的识别设计**：不是把已有 factorial/ablation 模板换个 factor 名字；
2. **一个会改变系统排名或推翻广泛接受结论的经验发现**（例如两个 aggregate-equivalent 系统的 F-MED profile 显著反向排序，且跨模型/环境/generator 稳定）；
3. **一个在已核实碰撞文献之上仍然成立的 method 贡献**（TRU-Mem 必须打赢 A-MAC / RSCB-MC / Decision-Aware Memory Cards 这些已发表的 admission baseline，而不是只打赢 no-memory 或 similarity-gate）。

只报告 aggregate accuracy 提升、只报告"发现了 negative transfer"、或只报告"证明了 P>0 且 S=1 有害"这类可预期的 sanity check，不构成顶会贡献。

---

# 2. 不可回退的已有结论（Novelty Check Gate 0，2026-08-07）

以下结论已经由文献核验（原技术报告的 30 篇引用 + Codex/gpt-5.6-sol xhigh 交叉评审 + 独立二次核验）确认，**后续不得重新包装或假装未见**。

## 2.1 总体新颖性判定：PROCEED WITH CAUTION，不是 GO

* 总体新颖性评分：**5.5–6/10**；
* 当前诚实档位：**Findings/Workshop**；ACL/EMNLP main 有条件可达（需满足第 7–10 节 Gate）；ICML/NeurIPS/ICLR 目前不够，且差距不是"缺一个定理"，而是缺一个不可替代的方法贡献 + 会改变结论的经验发现；
* 最大 Reviewer 2 风险：**"这是把已有 factorial transfer decomposition、structure-vs-surface procedural retrieval、context-incompatible interference、utility-based admission 和标准 risk-control 工具重新组合起来的 synthetic benchmark 工程，没有证明组合本身带来新的科学发现"**。

## 2.2 CausalMemBench / F-MED 已被部分占据

* **[Memory Transplants](https://openreview.net/forum?id=AIJsjIqfsp)**（ICLR 2026 MemAgents Workshop）已经用 2×2 factorial 独立改变 memory architecture 与 stored content，在 code→math domain shift 下做因果拆解，并有 prompt freeze、token-budget negative control、跨 solver scale 分析。**它已经拿走"memory transfer gain 由多个可干预组成部分构成，且可以通过 factorial 拆开"这一总命题**。CausalMemAgent 剩余的合法 delta 是 intervention 单位从"系统/域级 architecture×content"下沉到"memory-target pair 级 program-match×surface-similarity"，且引入 evaluator-only oracle——这是真实但不是自动"大"的 delta。
* **[Which Memory Operation Drives Recovery?](https://openreview.net/pdf/b29aa1580ee8fa1dacd941647d5c052cff0f8499.pdf)**（同一作者群，OMAC bandit controller）已经把 factorial ablation 用到 PROVIDE / TAKE-IN / MANAGE 三种 memory 操作，同样是 code→math domain shift。说明"用 factorial 拆解 memory adaptation"已经是该研究线的连续方法，不是一次孤立 workshop 偶然。
* **[Proced-Mem](https://arxiv.org/abs/2511.21730)**（"A Benchmark for Procedural Memory Retrieval in Language Agents"，ALFWorld）已经专门区分"functionally equivalent procedures across object instantiations"与"表面词汇泛化"，并证明 embedding 方法在 novel vocabulary 上出现"generalization cliff"。**它已经拿走 CausalMemBench 最核心的动机之一**：program equivalence vs 表面相似。
* **[STITCH / CAME-Bench](https://arxiv.org/abs/2601.10702)**（"Grounding Agent Memory in Contextual Intent"，ACL 2026 Findings）已经专门研究"语义相似但上下文/意图不兼容"的错误记忆问题，用 latent goal、action type、entity type 抑制该类错误检索。**它已经占据"surface-near、structure-wrong memory trap"的实质问题**，即 CausalMemAgent 的 near-miss / \(\tau_{trap}\) 概念不是首创。

## 2.3 TRU-Mem 的"oracle-free utility admission"已被大量占据

TRU-Mem **不是**首个 memory admission、utility gate 或 risk-aware memory selector：

* **[A-MAC](https://arxiv.org/abs/2603.04549)** 已把 admission 定义为结构化决策，用 future utility、factual confidence、semantic novelty、temporal recency、content type prior 五个可解释因子学习准入策略（LoCoMo，F1=0.583，延迟降 31%）；
* **[Decision-Aware Memory Cards](https://arxiv.org/abs/2606.08151)** 已用 decision-oriented / counterfactual-inspired utility 对 context 单元评分并做预算选择（SWE-bench，hit@1 0.58→0.78）；
* **[Learning When to Remember (RSCB-MC)](https://arxiv.org/abs/2604.27283)** ——**目前找到的与 TRU-Mem 机制最接近的单篇工作**：用 risk-sensitive contextual bandit 做 abstention-aware memory retrieval，目标直接就是"表面相似但根本不兼容"的记忆危害，且**惩罚 false-positive injection 重于漏用**（62.5% 成功率，0.0% false positive）。这与 TRU-Mem 的 harmful-flip 优先目标几乎重合；
* **[MemGate](https://arxiv.org/abs/2606.06054)**、**[MemRouter](https://arxiv.org/abs/2605.00356)**、**[ConsistencyGate](https://arxiv.org/abs/2607.22962)** 分别覆盖了"相似度不足→跨域泄漏/trustworthy gate"、"write-side admission router"、"write-time self-consistency gate"；
* **[ReMe](https://aclanthology.org/2026.findings-acl.829/)** 已经是 outcome-linked utility refinement/pruning（\(f(E)\ge5\) 且 \(u(E)/f(E)<0.5\) 时删除）；**[HiMPO](https://arxiv.org/abs/2606.16285)** 已经是 local counterfactual utility + hindsight relevance gate；**[AttriMem](https://arxiv.org/abs/2607.21106)** 已经是 token-level attribution process reward。三者均不构成 TRU-Mem 的完整覆盖，但共同压缩了"首次用 outcome/utility 管理 memory"的空间；
* **[CORA](https://arxiv.org/abs/2604.09155)**（GUI agent execute/abstain）与 **[ToolChain-CRC](https://arxiv.org/abs/2606.18467)**（agent trajectory 的 conformal risk control，含 distribution drift 与 anytime alarm）已经把 conformal risk control 用于 agent 决策层面（非专门针对 memory admission，但压缩了"首次把 conformal risk control 带入 agent/memory"这一表述）。

TRU-Mem 唯一可能仍然站得住的窄新意：

> 对每个 candidate memory，用**不访问 hidden family/program labels 的可观察 transformations**（entity rename、schema paraphrase、tool rebinding、state resampling）估计相对 no-memory 的 outcome uplift 分布，优化其 **lower-tail/CVaR**，并对 mean utility 与 harmful-flip risk 做**经多重性校正、与候选生成隔离**的联合准入校准。

这个窄组合必须直接打赢 A-MAC / RSCB-MC / Decision-Aware Memory Cards，否则不能写进论文。

## 2.4 两处未能独立核实的引用

Codex 交叉评审提到的 `When Memories Collide`（OpenReview，near-miss/interference gating）与 `RC-MemStop`（conformal risk control 用于 memory-agent early stopping，来源为非标准站点 analemma.ai）**未能独立核实其真实存在**，标记为 `[UNVERIFIED]`。每轮文献扫描时应重新尝试核实；若确认存在，按 2.2/2.3 的优先级并入碰撞列表；若确认不存在，从记忆中彻底移除，不得继续引用。

---

# 3. 已知高碰撞区域

每轮文献检索必须重新核查以下方向及其最新后续工作（按技术报告原有 30 篇引用 + Novelty Check 新增 11 篇合并去重）：

**Factorial / causal decomposition 线：**
Memory Transplants；Which Memory Operation Drives Recovery？（OMAC）；MemDelta；Bridge Evidence；MemAudit；Causal Agent Replay。

**Structure-vs-surface / near-miss 线：**
Proced-Mem；STITCH / CAME-Bench；`When Memories Collide`\[UNVERIFIED\]；Memory Transfer Learning（abstraction vs negative transfer）；More Skills, Worse Agents?（skill shadowing vs context overhead）；Useful Memories Become Faulty（consolidation decay）。

**Admission / utility / risk-control 线：**
ReMe；HiMPO；AttriMem；A-MAC；MemGate；MemRouter；Decision-Aware Memory Cards；RSCB-MC（Learning When to Remember）；ConsistencyGate；CORA；ToolChain-CRC；`RC-MemStop`\[UNVERIFIED\]。

**Procedural memory 系统与 benchmark 线：**
Reflexion；ExpeL；Agent Workflow Memory；Memp；MCMA；ProcMEM；AFTER；LifelongAgentBench；MemoryAgentBench；Mem2ActBench；RECON；Supersede；SeqMem-Eval；RoMeRL；When Continual Learning Moves to Memory。

出现下列情况时，立即判定为文献碰撞：

1. 问题定义相同，只是 factor 名字或 domain shift 场景不同（例如又一个 code→math 或 ALFWorld→ScienceWorld factorial）；
2. 已有方法已经用 hidden/oracle label 定义 equivalence class 并做随机化因果估计；
3. 已有方法已经把 utility admission 建模为"跨 observable transformation 的下尾/风险控制"，而不只是 item-level outcome；
4. 新方法的唯一贡献是"首次把 conformal risk control / CVaR / DRO 用在 agent memory 上"；
5. 已有工作已经报告"aggregate-equivalent systems 有不同 profile"这一现象，而新方法只是换一套 profile 指标。

输出 `LITERATURE_COLLISIONS.md`，字段与 EAGLE 项目一致：

| 字段 | 内容 |
|---|---|
| Paper | 论文名称和日期 |
| Problem | 它解决的问题 |
| Mechanism | 核心机制 |
| Factorial/oracle design | 是否已有正交随机化 + hidden label |
| Admission mechanism | 是否已有 utility/risk-based admission |
| Verified | 是否已通过 arXiv/OpenReview/ACL Anthology 独立核实存在 |
| Overlap | 与候选想法的重合点 |
| Remaining gap | 仍未覆盖的部分 |
| Decision | Collision / Partial / Safe |

每个候选想法至少寻找五篇最近邻工作，且必须对每篇做**真实性核验**（不能只信一次搜索结果或一次 Codex 回答；关键引用要 WebFetch 摘要页核对标题、作者、核心机制）。若发现一个月内的新论文覆盖核心机制，立即停止实现并重新进入 Loop Step 1。

---

# 4. 顶会潜力的硬性标准

一个候选设计只有同时满足以下条件，才能进入 Gate A。

## 4.1 问题重要

必须满足至少一个条件：

* "aggregate memory gain 掩盖了 replay/表面捷径/结构迁移的混合"是当前顶会 reviewer 尚未认为已解决的问题；
* 目标发现会改变至少一个广泛接受的结论（例如某个已发表系统的"transfer improvement"被重新归因后大幅缩水）；
* 目标发现会改变部署选择（例如证明两个 aggregate-equivalent 系统必须用不同的 admission 策略）。

## 4.2 因果识别设计不可替代（对应 EAGLE 的"张量不可替代"测试）

必须回答：

> 为什么普通的 M0–M6 ladder 比较、leave-one-out deletion、similarity-only gate、单一 2×2 (architecture×content) factorial，不能以相同成本解决这个问题？

只有在以下情况下，evaluator-only oracle + P×S(×D×I×V×E) 正交析因才具有合理性：

* 存在两个以上语义不同的混淆维度（program match、surface similarity、domain/interface/version、exact replay）需要同时正交分离，而不能用单一 factorial 或单一 ablation 轴解释；
* 现有 factorial 工作（Memory Transplants、Which Memory Operation Drives Recovery）在系统/域级别操作，而目标问题必须在 memory-target pair 级别操作，且不能通过重新分析它们的公开数据得到；
* hidden oracle 确实排除了"treatment label 可被表面特征预测"这一 confound，且这一点用强 probe（不只是 bag-of-words/embedding 弱 probe）验证过。

## 4.3 会带来"会改变结论"的经验发现（Headroom 测试）

在开始扩展到 240–320 families 前必须证明：

* 至少两个 aggregate-equivalent 系统在 pilot 中出现**稳定、可解释**的 cell difference（例如 A11 大幅正、A10 接近零、A01 显著为负），而不是 P、S、P×S 全部接近零；
* 该 cell difference 不能被"任务难度不等价"、"token 长度不等价"、"leakage probe 可预测"这些混淆解释掉。

若 headroom 测试失败（P、S、P×S 在确认 compliance/oracle/难度正常后仍接近零且 CI 足够窄），判定为 **NO_GO**，不得继续构建 240–320 families 或 TRU-Mem。

## 4.4 能在现有硬件上验证

方法不能依赖：

* 大规模预训练或从头训练 backbone；
* 无法在 A5000 上运行的专用系统；
* 无法公平比较的 baseline（尤其是 A-MAC/RSCB-MC/Decision-Aware Memory Cards——这三个必须能在同一 harness 下复现或忠实复刻）。

---

# 5. 研究空间：混淆维度 × 干预对象矩阵

每轮建立一个"混淆维度 × 可干预对象"矩阵，避免重复第 2 节已确认无效或已被占据的组合。

## 5.1 候选混淆维度（行）

1. Program match（P，latent partial-order equivalence）；
2. Surface/lexical similarity（S）；
3. Domain match（D）；
4. Interface/tool-schema match（I）；
5. Environment version/freshness（V）；
6. Exact same-instance exposure（E，嵌套于 P=S=D=I=V=1）；
7. Retrieval/selection policy（natural vs random vs oracle）；
8. Memory representation（raw trajectory vs summary vs procedural card）；
9. Context/format effect（sham memory 控制）。

## 5.2 候选干预/度量对象（列）

1. 单一 2×2 (P×S) 主析因，其余维度冻结（Stage A）；
2. 嵌套 E（Stage B）；
3. P×D、P×I、P×V 分层扩展（Stage C）；
4. content 与 retrieval 分离（Stage D）；
5. F-MED profile 的跨系统比较（是否造成排名逆转）；
6. TRU-Mem 相对 A-MAC/RSCB-MC/Decision-Aware Memory Cards/simple mean-utility/worst-group/UCB-only 的 head-to-head。

只有同时满足以下条件的单元格才可进入假设生成：

* 尚未被第 2/3 节碰撞列表中的任一工作直接覆盖；
* 在冻结其余维度后，效应可用随机化因果估计量识别（不依赖未随机化的观测比较）；
* 存在明确的、非平凡的 headroom 假设（不是"P=1 应该比 P=0 好"这种自动为真的 sanity check）。

---

# 6. 每轮研究循环

按照以下顺序持续循环，不得跳过前置 Gate。

---

## Loop Step 1：文献碰撞扫描

每轮开始时搜索：

* 过去 90 天的新论文（agent memory、causal/factorial agent evaluation、memory admission/gating、conformal risk control for agents）；
* arXiv cs.CL / cs.AI / cs.LG 最近 60 天；
* ACL/EMNLP/ICML/NeurIPS/ICLR 最新录用列表与 OpenReview；
* ICLR 2026 MemAgents Workshop 及其作者群（Memory Transplants、Which Memory Operation Drives Recovery 同一作者群）的后续工作；
* A-MAC、RSCB-MC、Decision-Aware Memory Cards 的后续版本或引用它们的新论文。

只优先使用：原论文、官方项目页、官方代码、正式会议/OpenReview 页面。**每篇高权重候选必须 WebFetch 摘要页核实标题、作者与核心机制，不得只凭一次搜索摘要下结论**（第 2.4 节的两处 `[UNVERIFIED]` 就是前车之鉴）。

输出 `LITERATURE_COLLISIONS.md`（格式见第 3 节）。

若发现新论文已覆盖 CausalMemBench 或 TRU-Mem 的核心机制，立即停止实现并重新进入 Loop Step 1，同时更新第 2 节"不可回退的已有结论"。

---

## Loop Step 2：Mini-pilot 因果识别（对应技术报告第 16 节）

不得跳过 pilot 直接构建 240–320 families 或实现 TRU-Mem。

Pilot 规格：

* 30–50 个 latent program families，每 family 至少 4 个 target siblings；
* Stage A 四 cells（A00/A01/A10/A11）+ N（no-memory）/ Q（sham memory）；
* 每 cell 3–5 decoding seeds；
* 2 个模型规模（3B/7B 或同家族两规模）；
* 1 个 SQLite 环境（RelationalOps）；
* memory 统一 200–300 tokens。

第一轮只看四张图：

1. Program Match × Surface Similarity 的四格成功率；
2. 四格相对 N/Q 的 randomized uplift；
3. embedding similarity 与 causal uplift 的相关性；
4. \(P=0,S=1\) 的 harmful flip。

输出 `BOTTLENECK_PROFILE.md`（此处"瓶颈"对应"当前 memory gain 中最大的未识别混淆来源"）与原始 pilot 数据。

---

## Loop Step 3：因果有效性审计（对应技术报告第 6.9 节数据质量闸门）

对 pilot 结果执行：

1. Program equivalence 的人工一致性（双人标注一致率目标 >0.85）与 executable consistency（oracle 100% 达到合法终态）；
2. **强** leakage probe 审计：不只用 bag-of-words/embedding 弱 probe，还要用 LLM probe、character n-gram、trajectory-length、action-sequence statistic 尝试预测 P/family；报告 probe AUC 与 calibration，不使用"零泄漏证明"措辞；
3. No-memory 条件下 sibling 难度等价性检验（equivalence test，差异落在预注册 margin 内）；
4. S 的操作化敏感性分析（S 是连续、多视角的，二值化可能混入多个 nuisance axes，需报告 continuous-S 下结论是否复现）。

输出 `TENSOR_STRUCTURE_AUDIT.md` 同构文件 `CAUSAL_STRUCTURE_AUDIT.md`。

**定义"识别优势"**（对应 EAGLE 的"张量优势"）：

> 在相同 token 预算、相同 retriever、相同模型下，P×S 正交析因必须揭示出单一 M0–M6 ladder 比较或单一 architecture×content factorial（Memory Transplants 式）**无法揭示**的稳定效应。

如果 pilot 效应可以完全由"Memory Transplants 式的 architecture×content 主效应"或"Proced-Mem 式的 embedding generalization cliff"解释，立即 NO_GO。

---

## Loop Step 4：生成并评分三个假设

每轮只生成三个高度具体的候选假设（可从技术报告 H1–H8 预注册假设或第 12 节方向中选取，但必须结合 pilot 实际数据调整，不得原样照搬）。

每个假设使用以下模板：

### Hypothesis ID

#### 问题
当前哪个混淆维度的贡献仍未被 pilot 识别或仍与已知碰撞论文纠缠？

#### 因果设计
具体的正交随机化方案：哪些维度被冻结、哪些被随机化、estimand 是什么？

#### 经验依据
pilot 中是否已有信号支持该效应存在？

#### 核心机制
为什么这个效应会改变系统排名、推翻已有结论，或改变 TRU-Mem 的设计？

#### 识别必要性
为什么 Memory Transplants / Which Memory Operation Drives Recovery / Proced-Mem / STITCH 的现有设计不够？

#### 与已知碰撞论文的比较
逐篇列出第 2/3 节相关工作，说明本假设与它们的具体差异。

#### 最小 Gate
不扩展到 240–320 families 时，最小实验是什么？

#### Kill condition
什么结果出现时立即终止？

---

## Loop Step 5：候选评分

每项按 0–5 分评分：

* \(N\)：Novelty（相对第 2/3 节碰撞列表的净新意）；
* \(I\)：Identification necessity（正交析因是否不可替代）；
* \(H\)：Headroom（是否有稳定、反直觉、会改变排名的信号）；
* \(F\)：A5000 feasibility；
* \(B\)：Baseline coverage（是否已能公平对比 A-MAC/RSCB-MC/Decision-Aware Memory Cards/Memory Transplants）；
* \(S\)：Statistical rigor（是否有预注册 estimand、family-cluster inference、multiplicity 控制）。

总分：

\[
\mathrm{Score} = 0.25N + 0.20I + 0.20H + 0.15F + 0.10B + 0.10S.
\]

以下任一条件触发直接淘汰：

* \(N<3\)（已被第 2 节碰撞论文完整或高度覆盖）；
* \(I<3\)（用现有 factorial/ablation 模板即可回答）；
* \(H<3\)（pilot 未显示稳定、可解释的 cell difference）；
* 存在未解决的直接文献碰撞（Loop Step 1 发现且未能证明差异化）；
* 无法在 A5000 + frozen backbone 上完成主要实验；
* 唯一贡献是"更多 nested factors"或"更复杂的 benchmark generator"，没有新的科学结论。

选择总分最高的一个候选，编写正式预注册协议。不得同时开发多个方向（例如不得同时全力推 F-MED 和 TRU-Mem，TRU-Mem 必须等 F-MED 产生可诊断结论后再决定是否升级为并列贡献，见技术报告第 20 节叙事顺序）。

输出：`HYPOTHESIS_CANDIDATES.md`、`SELECTED_HYPOTHESIS.md`、`GATE_PROTOCOL.md`。

---

# 7. Gate A：Pilot Identification Gate（对应技术报告第 16 节 Go/No-Go）

目的：

> 在扩展到 240–320 families 或实现 TRU-Mem 之前，确认 P、S、P×S 可以被稳定估计，且效应不是自动为零。

GO 条件：

1. 在确认模型遵循 memory 注入、oracle/evaluator 正常工作、任务难度处于 30–70% 成功区间后，至少出现一个稳定、可解释的 cell difference（例如 A11 大幅正、A10 接近零、A01 显著为负——这本身是强 benchmark-inflation 信号；或 A10 稳定为正，说明存在可迁移结构）；
2. Compliance 正常（agent 确实读取并尝试使用注入的 memory）；
3. Leakage probe（弱版本，Loop Step 3 强版本留待 Gate B）未发现明显 treatment artifact。

NO_GO 条件：

> P、S、P×S 在满足上述前置确认后仍均接近零，且置信区间足够窄。

否则：

\[
\boxed{\mathrm{NO\_GO}}
\]

记录负面结果，返回 Loop Step 1，考虑技术报告第 18.2 节的转向选项（见第 12 节）。

---

# 8. Gate B：因果有效性 Gate（对应技术报告第 6.9 节质量闸门 + Loop Step 3）

只有 Gate A 通过后才能扩展 family 数量。

GO 条件：

1. 强 leakage probe（LLM probe、n-gram、trajectory statistic）在 held-out generator/template 上无法高精度预测 P/family；
2. No-memory sibling 难度等价性检验通过（差异落在预注册 margin 内）；
3. 人工审查 ≥10% families，program equivalence / near-miss validity / 语言自然度双人一致率 >0.85；
4. Continuous-S sensitivity analysis 复现二值化 S 下的主结论；
5. \(\tau_{struct}\)（clean structural transfer）或 \(\tau_{trap}\)（near-miss harm）至少一个有统计显著、非零、跨 seed 稳定的估计。

否则 NO_GO，返回 Loop Step 1；若已扩展到主实验规模，不得强行保留已投入的 family，必须诚实报告识别失败。

---

# 9. Gate C：差异化 Gate（对应第 2/3 节碰撞列表）

只有 Gate B 通过后，才允许把 CausalMemBench/F-MED 包装成论文核心贡献。

GO 条件（必须同时满足）：

1. **把 Memory Transplants 当作方法基线**，直接实现或忠实复刻其 architecture×content 2×2 设计，证明 P×S 与 architecture×content 回答互补问题（不能只在 Related Work 口头区分）；
2. **把 Proced-Mem、STITCH/CAME-Bench 当作最近实质基线**，比较它们的 structural/intent 信号是否已经能预测 \(P\)、\(\tau_{trap}\) 和 harmful flips；如果能，F-MED 的增量价值需要重新论证；
3. 出现**稳定、反直觉的 profile divergence**：至少两个 aggregate-equivalent 的已发表系统（例如 MCMA vs ReMe vs AWM）在 \(\tau_{struct}\) 与 \(\tau_{trap}\) 上发生显著反向排序，且该排序跨模型、环境、held-out generator 保持；
4. 该 profile divergence **改变至少一个广泛接受的结论**（例如某系统的"cross-task transfer"报告被重新归因为主要来自 exact/replay，而非结构迁移）。

若只能做到"P=1 比 P=0 好、S=1 在 P=0 时有害、exact exposure 比 sibling transfer 强"这类高度可预期的 sanity check 集合，判定为 **incremental**，Gate C 不通过——即使统计显著，也应定位为完善的 workshop benchmark，而不是 main-conference discovery。

---

# 10. Gate D：TRU-Mem End-to-End Gate（对应技术报告第 8.5 节成功标准）

只有 Gate C 通过、且 F-MED 已经产生"哪类 memory 系统主要依赖 replay/表面捷径"的诊断结论后，才允许把 TRU-Mem 从 secondary intervention 升级为共同主贡献。

强制基线（必须全部包含，公平 harness 下比较）：

* no memory / sham memory / random retrieval / BM25 / dense retrieval；
* **A-MAC**（future utility + confidence + novelty + recency + type prior）；
* **RSCB-MC**（Learning When to Remember，risk-sensitive abstention bandit）；
* **Decision-Aware Memory Cards**（counterfactual-inspired utility ranking）；
* ReMe 的 utility-based refinement/pruning；
* HiMPO 的 local counterfactual utility；
* simple mean-utility gate、worst-group validation、UCB-only gate（消融 CVaR/联合校准的必要性）；
* oracle exact/structural memory（上界，不作为可部署方法）。

GO 条件：

1. TRU-Mem 相对上述**全部**已发表 admission baseline，在相同 token/candidate-pool/retriever 预算下，同时改善 structural-transfer ratio 与 harmful-flip rate（允许 aggregate accuracy 持平甚至略低）；
2. LCB(mean utility)>ε 且 UCB(harm risk)<δ 的联合置信保证，在**独立于候选生成**的 calibration transformations 上计算，并对 candidate/model/domain 的同时测试做多重性校正；
3. 在未用于 transformation design 的真实 shift（外部环境，如 AppWorld/ToolSandbox）上复现结构性提升，而不只是合成环境有效。

若第 4.4 节强制的公平对比显示 TRU-Mem 只是"A-MAC/RSCB-MC 加数据增强、CVaR 和标准置信界的组合"，且没有可测的净提升，**从主论文移除 TRU-Mem**，论文收缩为纯 CausalMemBench + F-MED 的诊断性论文。

---

# 11. 最终论文潜力审查

每个通过 Gate C（且视 Gate D 结果决定是否含 TRU-Mem）的方向必须回答以下问题。

## 11.1 一句话贡献

用一句话说明：

> 我们通过怎样的正交随机化，识别出了此前哪个混在一起的 memory gain 组成部分，以及这个识别如何改变了对现有系统或方法设计的理解？

如果一句话只能写成：

> We propose another factorial design for agent memory / another utility gate for agent memory...

则立即判定为不够。

## 11.2 "为什么不是已有方法"测试

必须逐一回答：

* 为什么不是 Memory Transplants 的 architecture×content 2×2？
* 为什么不是 Which Memory Operation Drives Recovery 的 PROVIDE/TAKE-IN/MANAGE factorial？
* 为什么不是 Proced-Mem 的 functional-equivalence 检索评测？
* 为什么不是 STITCH/CAME-Bench 的 contextual-intent gating？
* 为什么不是 A-MAC / RSCB-MC / Decision-Aware Memory Cards 的 utility admission？
* 为什么不是 ReMe/HiMPO/AttriMem 的 outcome-based credit？
* 为什么不能靠更多 GPU 或更大 benchmark 直接解决？

## 11.3 三项贡献测试

理想论文应当包含：

1. 一个新的、会改变结论的经验发现（不是"P 有用、S=1 有害"这类预期结果）；
2. 一个识别设计上的机制性贡献（P×S 正交 + evaluator-only oracle，且已在 Gate C 中证明不可被现有 factorial 工作替代）；
3. 一个已在公平 harness 下打赢已发表 admission baseline 的方法结果（若含 TRU-Mem）。

只有其中一项通常不够，等同 Findings/Workshop。

## 11.4 模拟审稿

分别模拟：

* **Benchmark/evaluator 审稿人**（关注 program equivalence ontology 的外部效度、leakage probe 是否够强）；
* **因果推断审稿人**（关注 estimand 定义、positivity、multiplicity、S 的连续性简化是否合理）；
* **Agent memory 系统审稿人**（关注是否与 Memory Transplants/Proced-Mem/STITCH/A-MAC/RSCB-MC 做了直接对比）；
* **认为"这只是更细的测量协议"的 Reviewer 2**（第 2.1 节已写明的最大风险）；
* **统计/理论审稿人**（关注 LCB/UCB 是否只是标准 concentration inequality 的直接应用）。

对每个审稿人给出最可能的三条拒稿理由。若无法通过这些问题，返回 Loop Step 1 或直接执行第 12 节的转向。

---

# 12. 优先探索但尚未假定成立的方向

以下是技术报告第 18.2 节"可转向的次级论文"与 H1–H8 预注册假设的整理，只是搜索起点，不是默认正确答案。每个方向都必须重新查重（Loop Step 1）并通过 Gate A–C。

## Direction A：Clean Structural Transfer 的存在性（对应 H1/H2）

> Exact memory 的收益是否显著高于 same-program/different-surface memory？控制 token、领域和检索后，现有方法（MCMA/ReMe/AWM/Memp）报告的 total memory gain 中，structural transfer 占比是否显著低于其声称？

必须直接对比 Proced-Mem 的 embedding generalization-cliff 结果，说明 F-MED 的 τ_struct 是否揭示了 Proced-Mem 检索评测无法揭示的行为层信息。

## Direction B：Near-miss Harm 的因果证据（对应 H4）

> 表面相似但潜在程序不同的 near-miss memory 是否是 negative transfer 的主要来源，且这个因果证据是否比 STITCH/CAME-Bench 与 RSCB-MC 已有的观测性证据更强？

必须证明 F-MED 的随机化 harmful-flip rate 估计，相对 STITCH 的 intent-mismatch 检测和 RSCB-MC 的 false-positive-injection 惩罚，提供了额外的、非冗余的诊断信息（例如量化"即使检索正确避开了 near-miss，系统本身对 near-miss 的脆弱度"）。

## Direction C：跨系统 Profile Divergence（对应 §7.8 Aggregate Gain Decomposition Profile）

> 两个 aggregate-equivalent 的已发表 memory 系统，是否具有完全不同的 F-MED profile（一个主要依赖 exact/replay，另一个具有更大的 clean structural transfer）？

这是技术报告第 13 节列为"最重要的两张主图"之一，也是第 9 节 Gate C 的核心 GO 条件。若 pilot 未能在至少两个已发表系统间观察到这一现象，本方向的顶会价值大幅下降。

## Direction D：转向路线（若 Gate A/B/C 任一失败，对应技术报告 §18.2）

* 若 consolidation 是主要问题：转向 evidence-preserving memory versioning；
* 若 retrieval selection 是主要问题：转向 near-miss-aware retriever（需先核实是否已被 STITCH/RSCB-MC 覆盖）；
* 若 exact premium 极强：转向 Agent benchmark leakage / performance inflation 论文；
* 若弱模型收益显著、强模型无收益：转向 memory–model capability interaction（对应 H7）；
* 若 obsolete memory 最严重：转向 temporal procedural memory governance（需先核实是否已被 Supersede 覆盖）。

---

# 13. 每轮输出文件

每轮必须更新：

* `RESEARCH_LEDGER.md`
* `LITERATURE_COLLISIONS.md`
* `BOTTLENECK_PROFILE.md`（识别缺口诊断，非计算瓶颈）
* `CAUSAL_STRUCTURE_AUDIT.md`
* `HYPOTHESIS_CANDIDATES.md`
* `SELECTED_HYPOTHESIS.md`
* `GATE_PROTOCOL.md`
* `GATE_FINDINGS.md`
* `DECISION.md`
* `NEXT_ACTION.md`

每个实验必须保留：完整命令、git commit、环境、GPU 型号、package 版本、random seed、原始 JSON/CSV、绘图脚本、失败日志、oracle/evaluator 版本与 sealed generator seed。不得只记录成功实验；NO_GO 和识别失败必须与 GO 同等详细地记录（技术报告本身就是"诚实止损优先于顺手整理"的产物，loop 必须延续这一原则）。

---

# 14. 每轮汇报格式

每轮结束时只输出以下结构：

## Current identification gap

当前 pilot/主实验中尚未被识别清楚的混淆来源。

## Latest literature collision

本轮发现的最新直接或部分重合工作（含真实性核验结果）。

## Hypothesis

本轮测试的唯一假设。

## Identification necessity

为什么该问题必须或可能需要 evaluator-only 正交析因，而不是已有 factorial/ablation/admission 方法。

## Experiment executed

实际执行了什么，不描述尚未执行的工作。

## Key results

给出数值、置信区间、cell-level 结果与 baseline 对比。

## Decision

只能选择：`GO` / `NO_GO` / `PIVOT`。

## Reason

说明决策依据，以及触发了第 7–10 节哪一条 Gate 条件。

## Next smallest action

下一步唯一、最小且可执行的动作。

---

# 15. 循环控制

使用以下逻辑持续执行：

```text
initialize research ledger with Section 2 (Gate 0 novelty-check findings)
load all previous positive and negative findings

while resource budget remains:

    scan latest literature (Loop Step 1)
    if new paper covers CausalMemBench or TRU-Mem core mechanism:
        update Section 2 "不可回退的已有结论"
        archive affected hypotheses as collided
        continue

    if no pilot has passed Gate A yet:
        run / extend mini-pilot (Loop Step 2)
        run Gate A

        if Gate A fails:
            archive the negative result
            consider Section 12 Direction D pivots
            return to literature scan
            continue

    run causal validity audit (Loop Step 3) -> Gate B

    if Gate B fails:
        archive the negative result
        return to literature scan
        continue

    generate exactly three hypotheses (Loop Step 4)
    score all three hypotheses (Loop Step 5)
    select exactly one hypothesis
    preregister its estimands and kill conditions

    run differentiation Gate C against Memory Transplants /
        Which Memory Operation Drives Recovery / Proced-Mem / STITCH

    if Gate C fails:
        archive the negative result (likely "incremental")
        return to literature scan
        continue

    if TRU-Mem is being pursued:
        run end-to-end Gate D against A-MAC / RSCB-MC /
            Decision-Aware Memory Cards / ReMe / HiMPO

        if Gate D fails:
            drop TRU-Mem from main paper
            keep CausalMemBench + F-MED as the paper's core

    perform final paper-potential review (Section 11)
    if it passes:
        build full paper plan, stop the search loop
    otherwise:
        archive the negative result
        return to literature scan

stop after three consecutive well-executed NO_GO directions at Gate A/B
and re-examine whether the P×S ontology itself needs revision

stop after six consecutive well-executed NO_GO directions overall
and conclude that no sufficiently strong causal-identification delta
was found for agent memory under current constraints
```

经过三个连续 NO_GO 后，必须扩大或修正研究对象（例如重新定义 program equivalence 的操作化、换一个环境），不允许只调整 family 数量或 seed 数。

经过六个连续 NO_GO 后，必须诚实结束：

> 当前证据不支持在现有资源和已核实的碰撞文献之上，继续以"正交 P×S 因果识别 + oracle-free transportable admission"为核心主张投入 CausalMemAgent 全量项目。

不得为了保持 loop 运行而不断放宽第 7–10 节 Gate 的判定标准。

---

# 16. 立即开始的第一轮任务

第一轮不得扩展到 240–320 families，也不得实现 TRU-Mem。

依次完成：

1. 将本文件第 2 节的 Novelty Check 结论写入 `RESEARCH_LEDGER.md`，标记为 Gate 0；
2. 将 Memory Transplants / Which Memory Operation Drives Recovery / Proced-Mem / STITCH-CAME-Bench / A-MAC / RSCB-MC / Decision-Aware Memory Cards 标记为**必须直接对比的强 baseline**，而不是 Related Work 口头引用；
3. 尝试独立核实 `When Memories Collide` 与 `RC-MemStop` 是否真实存在，更新第 2.4 节；
4. 检索截至当前日期的最新相关论文（重点：Memory Transplants 与 Which Memory Operation Drives Recovery 的作者群是否已有新的后续工作）；
5. 按技术报告第 16 节规格执行 30–50 family、单一 RelationalOps 环境、2 模型规模的 mini-pilot；
6. 生成第一轮的四张核心图（P×S 四格成功率、相对 N/Q 的 uplift、similarity-uplift 相关性、harmful flip）；
7. 执行 Gate A 判定；
8. 若 Gate A 通过：立即执行 Loop Step 3 的强 leakage probe 审计（Gate B 前置条件），不得先扩大规模再补审计；
9. 在任何 TRU-Mem 实现或主实验扩展前，汇报 Gate A/B 结果与下一步唯一动作。

第一轮的目标不是产出一篇论文的初稿，而是回答：

> 在已知 Memory Transplants、Which Memory Operation Drives Recovery、Proced-Mem、STITCH/CAME-Bench 均已发表的前提下，P×S 正交析因 + evaluator-only oracle 是否能在一个 30–50 family 的 mini-pilot 中，产生它们的设计无法产生的、稳定可解释的因果信号？
