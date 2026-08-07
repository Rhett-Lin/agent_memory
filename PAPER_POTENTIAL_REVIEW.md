# §11 最终论文潜力审查（2026-08-08）

> 依据 loop 文件 §11 执行。输入证据链：Gate 0、Round 1 文献扫描（SAFE）、mini-pilot（Gate A/B 全过）、H-C minimal gate（NO_GO）、H3 form×coverage 析因（formal NO_GO + clarification）、两次 GPT-5.6 外部复审。本审查同时作为 loop §15 的 pivot/continue 判定。

## 11.1 一句话贡献

> 我们通过 evaluator-only 潜在程序 oracle + P(程序匹配)×S（表面相似）正交随机化（memory–task pair 级），首次把同构 harness 下的 agent memory 增益分解为 clean structural transfer、replay-like 复用、surface-trap 危害与 context 效应，证明：(i) 表观增益主要由 surface-matched replay 驱动，而干净结构迁移的幅度与符号随模型规模反转；(ii) 这一识别在 Memory Transplants 式 arch×content / Proced-Mem 式相似度梯度无法复现（饱和模型证明 P 效应不可吸收）；(iii) 表征形式之争（raw/summary/procedural）在多重校正下不产生显著差异——完整覆盖决定一切。

## 11.2 "为什么不是已有方法"测试

| 追问 | 实测回答 |
|---|---|
| 为什么不是 Memory Transplants 的 arch×content 2×2？ | 它的 factor 是"系统架构 × 总体内容"，不能在 memory–task pair 上把 program-match 与 surface-similarity 正交拆开；我们的饱和模型（sim_tf+sim_embed+arch 哑元）控制后 7B 的 P 系数仍 +0.165 SIG——单靠它的设计得不到这个量。Transplants 报告的是 aggregate；我们给出的是 pair 级结构分解。 |
| 为什么不是 Which Memory Operation Drives Recovery 的 PROVIDE/TAKE-IN/MANAGE factorial？ | 它的轴是 memory 操作种类，不是内容语义；pair 级 P×S 与 harmful-flip 分解完全不同。且同作者群的实验全是 code→math，其 aggregate 层级无法发现"replay dominant + scale reversal"。 |
| 为什么不是 Proced-Mem 的 functional-equivalence 检索评测？ | Proced-Mem 证明 embedding 检索在 novel vocabulary 上掉崖（检索层指标），我们的问题在行为层：注入的 memory 实际改变了成功率的哪个成分、幅度多大。我们的 τ_struct（+9.2pp SIG）在 Proced-Mem 的 cliff 解释之外仍然成立（控制了架构、叙事模板与 embedding）。 |
| 为什么不是 STITCH/CAME-Bench 的 contextual-intent gating？ | STITCH 处理"语义相近但 goal/intent 不匹配"的错误检索，已有方法设计；我们要回答"即使正确程序也存在，观察到的增益有多少是 replay 而不是迁移"，且给出随机化的 harmful-flip rate（18.8% / 9.2%，按程序分歧 branch 剧烈分层），STITCH 不产出这个量。 |
| 为什么不是 A-MAC / RSCB-MC / Decision-Aware Memory Cards 的 utility admission？ | 我们是评测+识别，不是 admission 方法。如果将来做 TRU-Mem，这只是其诊断基础；目前 H-C 已证明"检测关节不是 admission 增益"——保存疑问。 |
| 为什么不是 ReMe/HiMPO/AttriMem 的 outcome-based credit？ | 同样是方法侧；我们的测量框架是对那些 outcome 信号做因果验证的仪器，不是替代。 |
| 为什么不能靠更多 GPU 或更大 benchmark 直接解决？ | aggregate 指标在 aggregate 层面不可识别——多 GPU 只会更精确地测错；需要的是正交随机化的 task family 设计，这正是本文对象。 |

## 11.3 三项贡献测试

1. **会改变结论的经验发现**：✔ 支持（带强度限定）。
   - (a) aggregate-equivalent 表象下 replay dominance + scale reversal（7B τ_struct +9.2pp SIG 干净利落；3B 反向、τ_P×S SIG+——"memory helps weak models more"被修正为"only surface-matched replay helps weak models, structurally hurts them"）；
   - (b) harmful flip 不是弥散噪声而是集中在程序语义真正分歧的状态（P3-B 分支 17.5–32.5% vs A 分支 0–12.5%），近错卡的危害有结构性来源；
   - (c) 同一模型连自己执行的程序都不认识（judge 对 A10 程序等价 100% 判错，即便被明确要求忽略表面差异）——“learned from experience”的叙事被行为证据直接削弱；
   - (d) 表示形式（raw/summary/procedural）在 Holm 校正下对 τ_struct/τ_trap 无显著影响，只有保留完整决策内容的覆盖起作用；完整 transcript 完全兑现 replay（TOST 拒绝等价）。
   以上 (a)(b)(c)(d) 均有 CI 与多重校正支持，(d) 还是一段新的、此前并未广泛被讲述的社论级事实。
2. **识别设计的机制性贡献**：✔ 支持。
   - evaluator-only oracle + pair 级 P×S + sealed generator + 全部审计（强 probe、难度等价、连续-S、oracle 复跑、盲标注、结构 SA、Holm-M8 校正、TOST）作为公开协议；饱和模型证明 M0–M6 ladder、arch×content 2×2、cliff 解释全部无法替代此分解。
3. **打赢已发表 admission baseline 的方法结果**：✘ 未实现（按 loop §10 纪律，TRU-Mem 未启动）。

**计：2/3**。达到 loop §1.2"至少两类"下限，但第 3 类缺失使论文天然锚定"测量与识别"而非"方法"。

## 11.4 模拟审稿（每类三条最可能拒稿理由）

**Benchmark/evaluator 审稿人**
1. 8 个 archetype × 单 SQLite 域（RelationalOps）的外部效度——一个问题簇的"程序等价"只对这一类 DSL 成立；
2. 抽象签名等价类是否匹配真实软件工程意义上的"程序"，人工验证缺失（LLM judge 又已证明不可信）；
3. sealed oracle 公开后，与 generator 同源的 hidden test 如何保证不可被检索重建。

**因果推断审稿人**
1. S 二值化；连续-S 只在重叠带一致性检验，且 P_S1 平面文本可读性高（AUC 0.996）——treatment 至少在 trap 平面上可由文本高置信预测；
2. family 簇只有 40/32，仅 2 模型家族外推；τ_struct(+9.2pp) CIs 边界对 family 数极敏感；
3. 无完备 positivity 论证：prefix 臂在 token 分布上与 complete 臂不可比。

**Agent memory 系统审稿人**
1. 未把 Memory Transplants/Proced-Mem/STITCH 作为强基线跑在同一 harness（Gate C cond1/cond2 未执行）；published-system F-MED 对比实际上不存在；
2. raw/summary/procedural 三系统 NO_GO 与 H3 n.s. 反而表明"写路径表示层不重要"——论文最大卖点（profile divergence）被自己否掉的局部证据反驳；
3. 读者会问"那 memory 系统到底怎么选？"——本文目前不回答。

**Reviewer 2（"只是更细的测量协议"）**
1. 核心科学贡献嵌在方法学里而没有一个正面的"新方法"或强反直觉事实；harmful-flip 与 τ_struct 可被读成"精心构造的 benchmark 固有产物"；
2. 所有结果依赖合成环境，外部效度和与同领域真实 trace 的联系不展示；
3. 与 Memory Transplants 相同动机的差异只是干预单元粒度。

**统计/理论审稿人**
1. H3 的 ε_cov 结论多重校正后 n.s.，却仍在引言被讲述为结论——措辞越界；
2. 3B τ_struct 负号 Holm 后 n.s.，"反转"必须措辞为"7B SIG / 3B 方向相反但边际"；
3. bootstrap family 数为 40/32、reps 2000–10000 的 CI 偏度在 HFR 罕见事件上需要考虑偏倚校正。

## 结论（§11 裁定）

- **Findings/Workshop 档论文现在就可写**（诚实、数据完整、两轮 GPT-5.6 复审通过）：分解 + scale-reversal + HFR 结构证据 + judge-not-recognizing + 两个诚实 NO_GO。这是 loop 文件 §2.1 判定的当前诚实档位，且证据比当初预估更厚。
- **ACL/EMNLP main 仍有一个可执行缺口**：Gate C 三条件未执行/未过（1 Transplants 基线未实测复刻；2 Proced-Mem/STITCH 信号可预测性未对比；3 已发表系统 profile 逆序——H-C/H3 已显示启动此对比风险极大：形式系统间没有显著反转，只有覆盖效应是唯一已知强反转轴）。
- **决定（本审查自身，非最终动作）**：继续 loop 的唯一顶会路径 = 执行 Gate C 补全模块（估计 10–15 GPU 天），同时把 profile 叙事重心从"形式系统逆序"改到"覆盖完备性 vs 截断"轴；若 Gate C 不出结果，按 GPT-5.6 裁决直接写测量论文（Findings 档）。
- 该决定遵守两处刚性强约束：(i) 用户规则：负结果必须先自分析+与 GPT-5.6 讨论——已走两轮；(ii) loop §10/§16：TRU-Mem 在未证明 structural gain 与 surface trap 共存前不得实现——目前 pilot 已证明共存（τ_struct SIG + HFR > 0），但 admission 方法本身仍缺 Gate C 证明的诊断方向。

## §15 pivot 账本（本轮更新）

- 连续 Gate A/B NO_GO = 0；假设层累计 NO_GO = 2（H-C、H3）。未达 3/6 止损阈值——按 loop §15 允许且应继续，下一动作由 §15 给定：回到 Loop Step 1（文献扫描新一轮）前的**不透明子步骤：Gate C 补全模块**（因为是 main 档唯一缺口，且现有资源还足够）。
- 若 Gate C 补全也失败（≈第 3 次假设层 NO_GO），执行 GPT-5.6 裁决：写 Findings 档测量论文并诚实结题。
