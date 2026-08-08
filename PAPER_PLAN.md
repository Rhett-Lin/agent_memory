# PAPER_PLAN — CausalMemAgent Main-Conference Paper（2026-08-08 定稿前）

> 状态：Gate C-lite 通过后定稿前分级。证据链全部实测并存档；含两次 GPT-5.6 外部复审与负结果处置流程闭环。除标注"待写"外，无虚构结果。目标：ACL/EMNLP main（measurement+identification 主线，主打方法学论文）。

## 1. 候选标题

1. **What Are Agent-Memory Gains Made Of? Factorially Decomposing Replay, Structural Transfer, and Surface Traps with Evaluator-Only Program Oracles**（主推）
2. Decomposing Agent-Memory Gains: Replay Dominance, Scale Reversal, and the Limits of Similarity
3. Measuring What Memory Buys: A Randomized P×S Auditing Framework for LLM-Agent Memories

选 1（问题定位直接定义论文域）。

## 2. 一句话电梯稿

> 我们在一个 evaluator-only 潜在程序 oracle + P(程序匹配)×S(表面相似) 正交随机化的任务族上，把七种 agent memory 使用方式的"aggregate gain"分解为 clean structural transfer、replay-like reuse、surface-trap 危害与 context 效应；发现增益被 replay 主导（A11 腿占 matched 效应的 72%）、干净结构迁移的规模对模型能力反转、while 敏感判断一致性的 LLM judge 实际上不能识别程序等价——部署含义是脚本化可执行表示与完整 episode 覆盖是仅有的可控杠杆。

## 3. 贡献声明（后页凝练为 4 条）

1. **识别设计**：evaluator-only 潜在程序 oracle（partial-order equivalence class）+ pair 级 P×S 正交随机化（与 Transplants 系统级 arch×content、Proced-Mem 检索级、STITCH 意图级正交互补），含完整审计协议（签名对齐 512/512、oracle 100%、强 probe、难度 TOST、连续-S 重叠带、盲标注、Holm/TOST/M-Estimate 多重校正）。
2. **经验发现（会改变结论）**：
   - aggregate gain ≈ 主要由 surface-matched replay 构成（7B A11 vs N = +18.6pp [+11.4,+26.1]；A11 腿占 matched 效应 72%）
   - clean structural transfer 符号随模型反转（7B τ_struct +9.2pp SIG；3B −6.6pp Holm n.s.，τ_P×S +11.3pp SIG），推翻/修正 Memory Transplants 的"弱模型获益更多"
   - near-miss 卡的有害翻转集中在程序语义真正分歧的中间状态（branch 分解），非弥散
   - 7B 等 judge 对跨域程序等价的判断系统性失败（A10 100% 误判；judge AUC/acc 近随机）——memory 的"程序理解/学习"叙事获独立行为反证
   - replay 的实现依赖语义覆盖而非表示形式：完整 transcript/script 均可兑现（TOST 拒绝 ±3pp 等价），300-token 截断几乎归零（H-C raw ≈ 0），Eco−tp≈0；形式之争在 Holm 下不显著
3. **基线对照（Gate C-lite）**：Transplants 式 arch×content 2×2 在本 harness 下实测（procedural vs raw + 三类内容），无法分解 replay/structural（72% 的 replay 份额对它不可见，I_match = −0.129 SIG）；Proced-Mem 的 embedding similarity 只在 7B 有限预测 uplift（不预测 P 结构面也不预测 harmful flip）；STITCH 式 LLM intent judge 对全部 cell 几乎全报警（AUC 0.508）。
4. **负面结果（如实写）**：H-C write-path 形式对比（raw/summary/procedural）与 H3 form×coverage 主析因对 τ_struct/τ_trap 差异全部 Holm n.s.——证据指示**不是表示形式而是语义覆盖**驱动 replay 的可兑现性；Bad-path admission 类方法（TRU-Mem）被纪律性收缩删除。

## 4. 相关工作的差异化矩阵（全部 VERIFIED，逐篇已在 LITERATURE_COLLISIONS.md 登记）

| 文献 | 它的量 | 我们与其关系 | 实测比较？ |
|---|---|---|---|
| Memory Transplants（ICLR26 MemAgents） | 系统级 arch×content 2×2 aggregate | 我们被其启发；互补：**在本 harness 实跑其设计并示出其不可见 replay/structural 分解** | ✔ Gate C-lite cond1 |
| Which Memory Operation Drives Recovery（LLA26） | 操作级 factorial（PROVIDE/TAKE-IN/MANAGE） | 操作轴 vs 内容语义轴；verallgemeinern 的问题，未覆盖 | ✔（交错引用） |
| Proced-Mem（arXiv 2511.21730） | embedding 检索在 novel vocabulary 坍塌 | 检索级信号；实测它对 uplift 只部分预测（7B Holm SIG），不预测 P/harmful flip | ✔ Gate C-lite cond2a |
| STITCH/CAME-Bench（ACL26 Findings） | intent mismatch 诊断子集 | 其 LLM judge 在此 harness 全报警（AUC 0.508） | ✔ Gate C-lite cond2b |
| Rocchi SSRN | bank×agent paired factorial regret audit | 因子无关（bank/agent vs P/S），oracle 为 regret 参考而非程序标签；Related Work 区别语句绑定三项 | ✔（VERIFIED SSRN 版） |
| A-MAC / RSCB-MC / Decision-Aware Cards / ReMe / HiMPO / AttriMem / MemGate / MemRouter / ConsistencyGate / CORA / ToolChain-CRC | admission/utility/risk-control 方法族 | 我们是诊断层，不 claim admission novelty；TRU-Mem 已从主论文移除 | — |
| SafeCommit（2608.04289） | conformal**动作**认证 | 与 memory admission conformal 同属 conformal-in-agents 但对象不同 | ✔（引用限） |
| drift/IEEE Access 2026 | drift robustness | agent-side，无 memory 分解 | ✔（Safe 引用） |
| Memory-R1/AgeMem/Reflexion/ExpeL/AWM/Memp/MCMA/AFTER 等 | memory 系统本体 | 在我们 framework 内被 profiled 的对象（raw/summary/procedural 复刻） | ✔（如实标注 write-path representation 复刻范围） |

参考文献上限 45；必须避免把当会减少引用簇的 Space。

## 5. 主结果表（全部实测，CI 已带；写入正文主表）

<主要数值引出：pilot 40 fam τ_struct 7B +0.092 [+0.036,+0.152]、3B −0.066 n.s.; replay 7B +0.144 / 3B +0.102 SIG；HFR 3B 18.8% [15.1,22.5]、7B 9.2% [6.3,12.0]；H3: TC +0.104/+0.190 SIG、SC +0.070/+0.125、eco ≈ 0（7B）；STITCH AUC 0.508；eq judge 0.25/32（100% A10 判错）。全部自 GATE_FINDINGS/H3_RESULTS 提取，写作时附原 JSON 路径。>

## 6. 图序（4 主图 + 2 支撑图，按"识别→发现→边界→部署含义"排布）

1. **Fig 1** P×S 四格成功率（两模型分面）；标出 A11 与 A10/A01/A00 数量级差异（含 CI 与 Holm 标记）→ 识别设计的揭示力
2. **Fig 2** F-MED profile forest（τ_context≈0、τ_struct（7B 正 3B 方向反）、replay premium 双 SIG、HFR 分支分解横条）→ 论文第二个最重要的发现图
3. **Fig 3** Transplants 式 2×2 在此 harness 的实测对照：arch×content 的 marginal vs P×S 的分解（展示 72% replay 份额对前者不可见）→ 方法学级鄙视
4. **Fig 4** Representation arms（SC/SP/TC/TP/eco） replay vs uplift 的森林图 + TOST 标记和"300-token truncated" 限定 → 部署含义（覆盖决定兑现性，不是形式）
5. Suppl Fig S1 similarity–uplift scatter（双向量 sim 视角）
6. Suppl Fig S2 LLM judge/equivalence 诊断（judge 判错热图；STITCH 全报警表）

## 7. 结构大纲（8 页 main conformed；括号内为段落职责）

1. Introduction：aggregate memory gains 遮蔽 replay。（锚定问题强度；一张 Fig 1 teaser；0.5 页背景 0.5 页主张与贡献列表）
2. Identification Framework：program equivalence class (partial-order)、P×S 正交 design、oracle isolation、stage-A 主析因；统计推断与多重校正方案。
3. CausalMemBench & Validity Audit：generator/archetype 表、oracle 100%、难度 TOST、强 probe（S0 平面 0.35–0.38）、连续-S 重叠带、盲标注、签名对齐。
4. Findings 主线（三段）：
   4.1 Replay dominance + scale reversal（附图 1/2；—与 Memory Transplants "弱模型获益更多"正面交锋：其 aggregate 陈述被我们的分解修正为"仅 surface-matched replay 对弱模型无害"）。
   4.2 Harmful flip 的结构来源（HFR 17.5–32.5% 于程序分歧 branch；A01 vs A00 的 marginal-versus-paired 差异；STITCH-style LLM judge 全部 misfire）。
   4.3 Replay realization is coverage-, not form-bound（H-C→H3 链条：raw truncated ≈ 0；完整 transcript/script 均兑现；TOST；形式在 Holm 下无显著差异）。
5. Gates & Boundaries（"我们没证明什么"）：Gate C-lite cond3 未实现（published system 逆序不存在方向）；H-C/H3 的 NO_GO 如实叙述；TRU-Mem 被纪律性移除（与 ReMe/A-MAC/RSCB-MC 的空间关系坦白）。
6. Related Work（按 §4 矩阵分三段：factorial/causal 类、结构-表面/近错类、admission/risk 类）。
7. Discussion & Limitations：合成 RelationalOps 的外部效度；程序等价由 partial-order signatures 定义、LLM judge 不足以自证（需人工）；family/模型amily（Qwen2.5 3B/7B） 有限；部署含义："清单"——选择脚本化可执行表示、保存完整决策覆盖、对 high-sim 表加入 harmful-flip 监测。
8. Artifact & Reproducibility Statement：全部 prompt/seed/config/hash/git、生成器与 sealed oracle 的开源方案（Sealed evaluate release）。

## 8. 部署含义段（核心 takeaway，回应部署选择问题）

1. **只保留脚本化/程序化可执行 memory**：完整 episode 覆盖（保留 write-decision + finish），禁止粗暴 token 截断。
2. **聚合指标停用**：系统间的"aggregate gain"排名不能直接用于选型；profile 必须在 P×S 下分解。
3. **高相似 ≠ 可用**：对 near-miss 布线 harmful-flip 监控（branch-aware），特别是删除/转账类高风险程序。
4. **LLM judge 不足用于程序等价**：评估方的程序等价验证需结构签名/执行轨迹，否则本轮研究揭示 LLM 无法自证。

## 9. 伦理与可复现

- 全部 sealed/public 切分随代码发布；Rand seeds 已记录；拒绝自动论文生成产物（FARS 类）引用；对未独立核实的条目以 [UNVERIFIED] 标记或剔除。

## 10. 写作分工（若进入执行）

- Sec 1-2：全量时政（0.5 天）
- Sec 3 + Appendix 数据表：gate 文件汇总（0.5 天）
- Sec 4 三个 Findings：Beta 审查各一份（2 天 + 1 天交叉）
- Sec 5-8 + bib：统稿（1 天）
- 所有图：paper-figure skill（东京出 4 main + 2 suppl）
- 外部 review 路径：auto-review-loop skill 2 rounds；投稿前对照 fresh-arxiv 90 天

## 11. 冻结禁忌（写作红线）

1. 不写 "first to causally audit individual memories"（Rocchi 已占）；限定语用 "first at pair-level P×S it with hidden program-equivalence oracle"。
2. 不声称"确认 coverage 驱动 replay"（GPT-5.6 限定；用 "supported-but-unresolved" 或"对覆盖/截断敏感"）。
3. 不把 H-C 的 300-token 截断差异写成形式机制差异（必须在方法学部分独立命名）。
4. 全称尺度只在 frozen Qwen2.5 3B/7B 范围内声明；明确不外推到 frontier model。
5. 对 3B 的负面（Holm n.s.）与 3B harm flip 18.8% 不得合并表述为"弱模型全面受害"——必须因果化到 P/S 条件层。
6. 避免使用 "proof"、"zero leakage"；一律 "no evidence detected at this audit strength"。

## 12. 退出、转向与放弃（写作纪律）

- 若 §4 写作发现叙述需要在数据层补"测量内容"实验，**禁止**在写作阶段追加——只许更新 GATE_PROTOCOL 闸门备选；证据链冻结于 2026-08-08 (commit f41e177 之前)。
- 如果 final review（auto-review-loop skill）两轮过不去 breadth-critic（Section 4 外部效度），降档为 Findings / 或 AAAI DemoRecord 提交——仍符合 §15 "诚实止损/完整账"要求。

## 13. 附录包

A. Prompts verbatim（probe/judge/selfcheck）
B. Git commit/config hash/GPU/seed 全记录
C. 32 个 fresh families 与 pilot 40 families 的 signed generator seeds + sealed oracle 描述
D. H3 五臂的 card 示例各 2（含完整/prefix + eco 差异演示）
E. 审计与推断 JSON 文档梏（AUDIT_RESULTS / H3_RESULTS / h3_inference_8tests / transplants_2x2_results / procedmem_results / stitch_results）
