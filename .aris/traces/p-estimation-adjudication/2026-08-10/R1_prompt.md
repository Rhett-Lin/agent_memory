# 裁决请求：CausalMemAgent 的「部署态如何获得 P」路线选择（Round 1）

你是本项目的外部裁决者（项目治理规则：战略转向与负结果处置必须经你裁决后才能动作）。
工作目录 `/work1/zixuan/projects/agent_memory`，你可只读检视任何文件。关键入口：
`RESEARCH_LEDGER.md`（含你此前全部裁决记录）、`pilot/peval/PHI_D_EVALUATOR_PLAN.md`、
`pilot/peval/README.md`、`pilot/peval/phi_d/REPORT.md`、`pilot/peval/phi_d/audit_expanded/AUDIT_EXPANDED.md`、
`pilot/peval/phi_d/sft0/FEASIBILITY.md`、`iclr2027/`（17pp 论文本体）。

请先花力气核实我下面的事实陈述（我可能记错或美化），再裁决。

## 1. 用户提出的瓶颈（本轮议题）

论文的全部发现——replay dominance、structural transfer 的规模反号、harmful flip 集中在程序分歧
branch——**都是在"已知 P"的条件下成立的**。P（memory 与 target task 的程序等价性）在 benchmark 里是
evaluator-only sealed oracle。**部署态没有这个 oracle**。因此"用我们的发现去指导真实 agent system"这条
路被卡死：一个真实系统拿到一条候选 memory，无法知道它是 A11（表面匹配且程序匹配）还是 A01（表面匹配但
程序冲突的 near-miss），而这两者的行为后果相反（A11 是主要增益来源，A01 造成 3B 18.8% / 7B 9.2% 的
paired harmful flip）。

用户的要求：**探索如何得到 P**，给出可行方案。

## 2. 已注册证据（同一 640 对标注集，这条线不得绕开）

按时间顺序，所有尝试估计 P 的结果：

| 方法 | 结果 |
|---|---|
| sim_tf → P | AUC 0.608 (overall) / 0.595 (S=1 即 A11-vs-A01 部署关键切面) |
| sim_embed (bge-small) → P | 0.606 / **0.529（关键切面上等于随机）** |
| vanilla 7B 整体等价判定 | 跨域真等价 A10 上**判错率 100%** |
| STITCH 式 intent judge | AUC **0.508** |
| 早期分解式 CoT 判定（16 对） | 一致率 25%，A10 0%，A01 50% |
| P̂ v1 指纹判别器（logistic + TF-IDF pair 特征 + 15 手工特征） | family-CV **0.966/0.935**；**LOAO 0.636/0.590**；conditional_write 留出时 overall **0.408（低于随机）** |
| 分解式 judge（φ+d S1 canonical run4766） | overall 0.597 / S=1 **0.664**；A01 误收 **19.4%**、A10 误杀 **85%**、A11 仅保 **45%** |
| φ-IR 结构化抽取（guided decoding, Qwen2.5-7B） | 救援后 **532/532 = 100% 合法**，640/640 双侧可比 |
| φ-IR **忠实度**扩编审计（532 全量 join sealed truth + 分层人审） | **无一字段保留硬否决资格**；`absent` 全向不可用作否决（假 ABSENT 19.6% 槽级 / P4 29.6%）；branch 节点仅 52.8%；必需角色槽 41.4% present / 39.0% unknown；branch_effects 一致 32.7%；`pred_op` 唯一过 present-only≥0.90 |

结论性事实：**"程序等价"在这个 benchmark 上不是 embedding lookup 能解的，也不是 7B 零样本判断能解的；
唯一域内高分的方法（P̂ v1）被证明是 4 种已知 flip 类型的指纹，留一类即崩。**

## 3. 你此前已下的、约束本轮答案空间的裁决

1. **2026-08-09 φ+d 设计裁决**：GO with amendments。架构 = 嵌在两阶段检索后的约束检查器
   （top-k → 两侧独立 φ 抽取 → 确定性比较 → admit/abstain）；IR 必须角色归一（α-renaming）、程序图、
   ABSENT≠UNKNOWN、每字段 evidence span。成功门：macro-LOAO ΔAUC≥+0.10、灾难门、准入门
   (A01 接受≤0.10 且 A11 保留≥0.50，整体且逐族)、跨表面门、策略门。诚实等级：**locked evaluation
   而非预注册**，四种翻转机制设计者已知；真·未见机制迁移需规则冻结后造第五种 challenge set。
2. **2026-08-10 pivot 裁决（P→动态 belief）**：**NO_GO（当前）+ GO（未来种子带里程碑门）**。
   核心论断："**P 在执行中不应被更新；被执行更新的是 mismatch-relevance / utility 的 belief**"。
   要求任何渐进式方案先满足 `I(P;h_t|x,m)>0 by construction`。
3. **2026-08-10 双 estimand 裁决**：**P 保留为 benchmark 机制诊断变量；部署决策变量改为因果化、
   风险调整后的 utility U**（quarantine → randomized canary 暴露记 propensity → IPW/DR 或分层收缩
   → promote 需 LCB>边际、prune-for-harm 需 UCB<伤害边际）。lane 优先级 C(SFT 抽取器) > D(utility
   控制面) > A(current-IR 比较器基线) > B(prompt v3) > E。
4. **措辞护栏（已冻结）**：避免 "program compatibility belief / procedural signature /
   progressive program inference"；合法 claim 收窄到"在本 benchmark 上，估计 evaluator-hidden P
   需要结构推断，不归结为 embedding lookup"。collision：Skill-Pro (arXiv 2602.01869, ICML 2026
   spotlight)、CMI 为 close-partial；禁称 first causal memory usefulness / first intervention selection。

## 4. 一条你可能还没看到的新证据（lane C step 0 可行性，CPU 实测，本仓 `pilot/peval/phi_d/sft0/FEASIBILITY.md`）

为 SFT 抽取器造 (text → gold program-graph IR) 语料的可行性检查，已实测出：

- renderer 的结构化中间体（roles dict）**未持久化**到 sealed artifacts，但可按同 seed 流 **bit-for-bit 重生成**；
  evidence span 只能靠确定性字符串对齐恢复（每个 span 都是 renderer 插入的逐字子串）。
- **73/372** 唯一 memory 文本 join 到 >1 个 sealed 源行；**12/372** 存在冲突的标量 θ（复现审计的 12 例）；
  再加 24 例 two_row_transfer（实例相关参数），**36/372 memory 文本存在文本不可判定的数值参数**。
- **符号化表述占比：P1+P2 memory 卡 137/372 = 36.8%；指令的 policy-table 间接 20/160 = 12.5%；
  合计 157/532 = 29.5% 语料文本**的关键取值不在文本里明写。

我的读法（请批判）：这意味着**"P 从文本可识别"存在一个可测量的不可识别下界**——不是抽取器不够好，
而是文本里根本没有那个信息。如果属实，"估计 P"这个目标的正确形态就不是"提高 AUC"，而是
"把可识别部分与不可识别部分分开，并在后者上受控弃权"。

## 5. 另一个我认为必须摆上桌的外部效度问题

`pilot/peval/README.md` caveat 1 自陈：本 benchmark 的**指令几乎逐字陈述了 policy**（翻转的比较词直接
出现在文本里，如 "above 5" vs "at or below"），所以文本分类器接近于"从表面读出答案"。
**真实部署的任务语言是隐式的。** 因此即便我们在 CausalMemBench 上把 P̂ 做到很高，也可能对真实系统零迁移。
我担心整条 P 估计线在 external validity 上是自欺的。请正面裁决这一点。

## 6. 我目前的候选路线（请批判、排序、补我漏掉的）

- **A. 直接结构化估计 P**（lane C）：SFT 一个 φ 抽取器（监督目标 = z 的文本可证投影 π(z, renderer, text)），
  + 冻结的确定性比较器。风险：忠实度审计已判无字段可硬否决；语料有 29.5% 符号化 / 36 例不可判定；
  且 SFT 于同一 generator 语料 = 第二代指纹的高风险。
- **B. 放弃 P 作为部署变量，走 utility U**（lane D，你已裁 GO）：randomized canary + 因果 uplift。
  但这**回答不了用户的问题**——它绕开 P 而不是得到 P，且需要在线暴露预算与伤害暴露伦理成本。
- **C. 改变 estimand：不估 P，估 P 的决策相关泛函**。真正要的不是"程序是否等价"，而是
  "这条 memory 在这个 task 上是否会造成 harmful flip"。后者可能比 P 更容易估、也更贴近 admission 决策。
- **D. 执行式验证（check, don't classify）**：不做文本分类，而是把候选 memory 的程序在**沙箱/可回滚
  副本/干跑**上对目标任务执行一小步，用环境本身的谓词做判定。把 P 估计从分类问题变成测试问题。
  我认为这是 ledger 里**最未被探索**的一支，且天然规避"文本不可识别"的下界。
  风险：真实部署未必有可回滚沙箱；成本；且可能与 Part V 关闭的那条外部验证线共享失败模式。
- **E. 选择性预测 / 风险控制形态**：任何估计器都配 abstain，用分布无关的风险控制把
  "A01 误收率 ≤ α" 变成有保证的量，代价是覆盖率。Gate 0 已登记 conformal-in-agents 被占据
  （CORA、ToolChain-CRC），所以 delta 不能是"首次把 CRC 用在 memory 上"。

**请裁决：**
1. 我第 4 节和第 5 节的两个"不可识别 / 外部效度"论断是否成立？若成立，是否意味着"估计 P"这个目标
   本身要重新定义？请给出你认为正确的 estimand 表述。
2. A–E 的排序与组合方式；每条的 kill condition；哪些是我漏掉的路线。
3. 这条线要成为论文的第三类贡献（Gate 0 认定当前缺"打赢已发表 admission baseline 的方法结果"），
   最小的可信形态是什么？还是说它注定只是工程件、应该诚实地留在 appendix？
4. 请明确指出我这份简报里的事实错误、选择性叙述或框定偏差。

约束：只读检视，不要修改仓库任何文件。回答请给出可执行的判据与数字，不要泛泛的方法学建议。
