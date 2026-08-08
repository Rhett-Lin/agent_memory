# LITERATURE_COLLISIONS — Round 1（2026-08-07）

> 每轮更新。格式按 loop 文件 §3。状态：**Round 1 完结**。扫描窗口 2026-05-01 → 2026-08-07（两个独立 agent 分轨：factorial 作者群 + 90 天全领域）。**总体判定：两个核心 claim 均 SAFE——无直接 Collision；Partial 若干，必须正面区分。**

## A. Gate 0 [UNVERIFIED] 引用核验（本轮完结）

### A.1 When Memories Collide — VERIFIED（并入碰撞列表）

| 字段 | 内容 |
|---|---|
| Paper | *When Memories Collide: Associative Interference Dynamics in Lifelong Agent Memory*，Feng/Yao/Lewis，ICLR 2026 NFAM Workshop Poster（2026-03） |
| URL | https://openreview.net/forum?id=Y7r5ZODl7l （无 arXiv 版） |
| Problem | lifelong agent memory 在 domain shift 下，历史有用 memory 对当前推理的关联干扰 |
| Mechanism | AIM（训练-free）：稀疏编码 + per-item interference ledger + adaptive gating；消融显示 interference ledger 贡献最大 |
| Factorial/oracle design | 无（streaming 实验 + 消融，非随机化 P×S，无 hidden evaluator oracle） |
| Admission mechanism | 有 adaptive gating（基于干扰追踪），但非 utility/CVaR/风险校准准入 |
| Verified | 是（OpenReview 记录 + iclr.cc 虚拟页 + NFAM program 三处核对） |
| Overlap | 覆盖"干扰感知 gating / 跨域竞争检索边界"，与 near-miss gating 空间部分重合 |
| Remaining gap | 无随机化因果识别；无 P×match/S 正交；干扰定义非"surface similar + program mismatch" |
| Decision | Partial（近邻工作；Near-miss 方向需明确区分：F-MED 的 τ_trap 是随机化估计量，非观测性 ledger） |

### A.1.5 Rocchi "Does Memory Credit Travel?" — ⚠️ 新的部分碰撞（Round 1 agent-1 扫描发现，2026-07-22）

| 字段 | 内容 |
|---|---|
| Paper | *Does Memory Credit Travel? Paired Factorial Audits of LLM-Agent Memory*，Alessio Rocchi（solo），SSRN 2026-07-22；RG DOI 10.13140/RG.2.2.11232.44801；OpenAlex W7170150829 |
| Problem | 单条 memory 的因果贡献（"memory credit"）是否跨 memory banks × consuming agents 迁移 |
| Mechanism | bank-conditional memory credit；**单条 memory 的 paired memory/no-memory A/B replay audits（bank × agent 因子）**；预注册判据；regret-reduction 分布；bank-context outcome oracle 作零 regret 参考；讨论 utility gating 与 provenance-aware admission 并警示"utility gate 会固化窄 reward" |
| Factorial/oracle design | 有——单条 memory 级 paired factorial，但因子 = bank × agent 身份，**非 program-match × surface-similarity**；oracle 是 outcome oracle（regret 参考），**非程序等价标签** |
| Admission mechanism | 文中讨论/评测 utility gating 作对照，无 CVaR/conformal/risk-control admission |
| Verified | 题名/作者/日期经 DataCite + OpenAlex + Google Scholar 三方核验；全文被 SSRN/RG Cloudflare 墙挡，机制细节来自 Scholar 摘要片段，**机制为部分核验** |
| Overlap | 与 CausalMemAgent 主张 (a)（pair 级因果析因审计）强部分重合，且已引用 Feng 组三篇 workshop（Memory Transplants / AIM / LLA） |
| Remaining gap | 因子不同（bank×agent vs P×S）；无 evaluator-only program-equivalence oracle；无跨变换 CVaR/conformal 准入 |
| Decision | **Partial** —— 含义：论文 headline 不能写"首次对单条 memory 做跨配置的因果审计"；新意必须锚定在 verified-task-equivalence pairing（P×S + oracle equivalent class）与 risk-based admission 上。Related Work 必须正面区分。后续每轮需复查 Rocchi 该文是否有 arXiv/正式版本扩展因子到 P×S |

### A.1.6 SafeCommit（arXiv:2608.04289）— 新核验（2026-08-04）

| 字段 | 内容 |
|---|---|
| Paper | *SafeCommit: Certifying When Memory-Grounded Agents May Safely Act*，Akewar/Ranjan，arXiv 2608.04289（2026-08-04，NeurIPS 投稿方向） |
| Problem | 带副作用的 agent 动作在 memory 不确定性下何时可安全执行 |
| Mechanism | conformal risk control（level α）+ calibrated world sets，认证动作安全 |
| Factorial/oracle design | 无 |
| Admission mechanism | 非 memory admission；但 conformal × memory-grounded agent 的框架组合已被占 |
| Verified | 是（arXiv 摘要页） |
| Overlap | 压缩"首次把 conformal risk control 用于 memory-grounded agents"的表述空间（与 CORA/ToolChain-CRC 同线） |
| Remaining gap | 不做 memory admission 选择、不做跨变换 utility |
| Decision | Partial |

### A.2 RC-MemStop — 移除，禁止引用

| 字段 | 内容 |
|---|---|
| Paper | *RC-MemStop: Risk-Controlled Early Stopping for Long-Context Memory Agents*（analemma.ai，2026-02） |
| 核实结论 | **非合法研究论文**：Analemma Intelligence 全自动研究系统 FARS 的机器生成产物（PDF 自声明 generated content），无 arXiv/OpenReview/DOI；内容本身为近负面结果（1.02–1.14× 加速） |
| Decision | 从项目记忆与全部文档中移除；后续轮次每轮无须再核实（已定性为自动生成 artifact），但需留意该类自动流水线产物可能涌现在检索结果中，一律要求 arXiv/OpenReview/出版社页面方可采信 |

## B. 必须持续直接对比的强 baseline（Gate 0 已确认，详见 RESEARCH_LEDGER.md）

Memory Transplants；Which Memory Operation Drives Recovery (OMAC)；Proced-Mem；STITCH/CAME-Bench；A-MAC；RSCB-MC；Decision-Aware Memory Cards。本轮若无新动向，维持原对标义务。

## C. Round 1 90 天全领域扫描结果（2026-05-01 → 2026-08-07）

### C.0 总结论

- **Claim (i)（P×S 正交随机化 + evaluator-only oracle + 四路增益分解）：SAFE，无 Collision。** 未发现任何工作在 memory–task pair 级独立随机化 latent-program match × surface similarity，或用 agent 不可见的 hidden family/program 标签做分解。检索显式负例：`"surface similarity" memory`（3 篇全是检索工程）、`agent hidden oracle memory labels`（0）、`aggregate replay leakage`（0）。
- **Claim (ii)（跨可观测变换 uplift + CVaR/下尾 + 多重校正的分体式准入校准）：SAFE，是最清晰的差异化点。** `CVaR memory agent`→0、`conformal memory admission`→0、`"distributionally robust" LLM agent`→0、`uplift memory agent`→2（均无关，已逐篇排除）。
- **Memory Transplants / OMAC 作者群（Feng/Yao/Lewis, UCSD Q-Lab）：2026-03 后无该方向后续工作**（作者个人页 + arXiv author listing + OpenReview + Scholar 四方确认）；两篇 workshop 均 VERIFIED。唯一引用者：Rocchi（→ §A.1.5）。
- 五个锚点引用更新：A-MAC 被引 13（无 factorial/causal 后续）；RSCB-MC 被引 1（LUCID，无碰撞）；Decision-Aware Memory Cards 0 被引、v2 2026-06-15 小修（claim 不变）；Proced-Mem 被引 1（LMEB，无 factorial）；STITCH 被引 2（SAM 合成安全，另一篇 drift 论文 **UNVERIFIED 待追踪**，见 C.3）。

### C.1 新登记 Partial（均为已核验 arXiv 摘要页；必须 cite 并正面区分）

| Paper | 日期 | 它做了什么 | 与我们（i)/(ii) 的关系 | Decision |
|---|---|---|---|---|
| Trap-of-Trajectory / CAMEL (2605.09330) | 2026-05 | 轨迹级 spurious-correlation taxonomy + 写/检索时校准 | 共享"memory 放大表面依赖"诊断；无 P×S、无 hidden family | Partial |
| CMI + Causal-LoCoMo (2605.17641) | 2026-05 | do-operator 式记忆对答案的因果干预估计 + 标注 useful/distractor/harmful 的对话 benchmark | **(i)+(ii) 最近交叉**；但干预是答案替换式、对话 QA 单轴、无程序族、无变换 uplift、无 CVaR | Partial |
| PATH-Bench + SEU (2608.01149) | 2026-08 | 受控 helpful/interfacing 历史测 path dependence；SEU 准入过滤器 | 单因子设计；准入为启发式，无风险校准 | Partial |
| ContinualSkillBench (2608.03874) | 2026-08 | 难度序任务；发现 in-context learning ≈ 显式技能维护 | 同一识别问题（增益是真迁移还是便宜适配），但方法完全不同（难度序 vs P×S factorial） | Partial |
| InMind (2607.24368) | 2026-07 | 125 任务 implicit-association 盲点；paired controls 分离混杂解释 | paired-control 精神相近；世界知识联想，无 P/S 因子/无 replay 臂 | Partial |
| Ground Truth First / Veracium (2607.21962) | 2026-07 | scripted gold 对系统隐藏 + no-memory 对照；排名随历史长度反转 | evaluator 侧真值隐藏思想相近；事实回忆型，非程序迁移 | Partial |
| OEP 经验投毒 (2605.18930) | 2026-05 | 黑盒注入"局部正确但不可迁移"经验，reflection 蒸出过度泛化规则 ASR>50% | 正面认可"local correctness ≠ structural transfer"区分的必要性；攻击演示而非测量设计 | Partial |
| GovMem (2607.02579) | 2026-06/07 | 写路径治理：依赖感知 support、反证检索、scope 指派→promote/reject/review；"risk-controlled evidence governance" 措辞已出现 | 基于证据协变量而非 outcome uplift；无变换/CVaR/多重校正 | Partial |
| Memory Worth (2604.12007) | 2026-04 | 双计数器估 Pr[success\|retrieved]，作者自注"associational, not causal" | outcome 反馈 utility；其作者亲自标出的因果缺口正是 (ii) 要填的 | Partial |
| MemTX (2607.23929) | 2026-07 | snapshot-isolated 事务 + validate-and-commit 准入 + 机检不变量 | 规则/出处理证；无统计风险控制 | Partial |
| RoMeRL (2608.02508) | 2026-08 | RL 低阶 utility 状态修"memory-reward trap" | RL 方案；无 conformal/CVaR/变换 uplift | Partial |
| LUCID 奖励膨胀 (2608.00017) | 2026-06/08 | LLM-judging 对错误存贮给高分的 Echo Gap + 去膨胀 | 修正 per-memory 价值估计；score 校准而非变换下尾准入 | Partial |
| Role-Stratified CRC (2607.24343) | 2026-07 | per-argument-role 的 conformal risk control（AgentDojo/InjecAgent） | CRC-for-agents 前沿现状；非 memory | Partial（引用为 CRC 最新前沿） |
| MemHarness (2607.28272) | 2026-07 | RL 重写检索出的 memory 防负迁移 | 修复而非审计；相邻 | Safe |
| SAM (2605.24468) | 2026-05 | state-adaptive 安全 consolidation | 相邻 | Safe |
| SAGE 新颖度门 (2605.30711) | 2026-05 | vMF 新颖度写侧路由 | 正交判据 | Safe |
| T-Mem (2606.15405) | 2026-06 | 描述/联想双通道召回 | 用了 surface-vs-latent 词汇但非识别设计 | Safe |
| Nous 信仰条件记忆 (2606.22030) 等治理簇（2608.01679/2606.24535/2606.04628/2605.06527/2603.14597/2607.08716） | 2026 各月 | 写侧/治理/有效性机制 | 无因果 utility 或风险校准准入 | Safe |

### C.2 监控项（Round 2 复核：2026-08-08 完成）

1. **Rocchi SSRN（§A.1.5）→ 维持 Partial（VERIFIED 升级）**：现正式存档 SSRN DOI 10.2139/ssrn.7160321，Crossref 完整摘要已核验（2026-07-27）：六格 factorial 仍为 bank × model-decoder agent（ALFWorld，576 episodes）；oracle 仍为 "outcome-hidden regret" 协议，非程序等价标签；无 P×S 因子，无 CVaR/conformal。升级触发条件未满足，0 被引。Related Work 区分锚点：P×S + hidden-equivalence oracle + risk-based admission。
2. **drift 论文 → VERIFIED 为 Safe，移出威胁监控**：真实存在但正交——Assidiqi et al., *Benchmarking Reference-Free LLM Agent Robustness Under Schema, Policy, and Toolset Drift*, **IEEE Access 14:79662–79672 (2026), DOI 10.1109/ACCESS.2026.3696096**（Crossref + DBLP + S2 三方核验）。tau2-bench 扰动鲁棒性，无 memory credit 分解、无 P×S、无 admission、无等价 oracle。从此列表删除；可作 Related Work 的普通引用。
3. **SafeCommit（2608.04289）→ Safe**：仍仅 v1（2026-08-04），未到 memory admission。
4. FARS/analemma 类自动论文流水线产物一律要求 arXiv/OpenReview/出版社页面才采信（§A.2 规则重申）。
5. **近三周 sweep（2026-07-18→08-08）两条 claim 均 SAFE**。新增 Safe 引用候选：EA-Graph（2608.04278，artifact-anchored verification memory）、MERIT（2608.05906，oracle-verified causal episodic memory Text-to-SQL）、Ground Truth First（2607.21962）、MemTX v2（2607.23929）。ConsistencyGate（2607.22962）为最近 admission 邻域，已在 §C.1 登记。

### C.3 扫描明确未覆盖/受限声明

- Semantic Scholar citations 端点在扫描中多次 429；引用数用 Scholar + OpenAlex 交叉核验替代（agent-1 已说明）。
- 两个 [UNVERIFIED] 原始条目的核验结论见 §A.1/A.2，不再复检。
- Rocchi SSRN 全文被 Cloudflare 拦截，其机制描述为部分核验（已在 §A.1.5 标明）。
