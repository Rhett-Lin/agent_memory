总裁决：

> **“用后果间接得到/反映 P”是 NO_GO；“用后果替代 P，直接估计 pairwise utility + downside risk”是 GO。**

Xiong et al. 支持的是后者，不支持微调一个 P judge。你提出的 quality ≠ applicability 基本成立，但必须承认 Xiong §4.3 已明确讨论 quality-filter 后仍存在 task misalignment；我们的增量是用 P×S 析因和 no-memory 配对把这种残差拆成 net utility、helpful flip、harmful flip，而不是首次发现 misalignment。

## 1. Xiong 原文核对

你的概括大体正确，但有三处需修正：

1. C3 的 300 条结果不能写“显著优于”。

   原文确实说，除 RegAgent 外，C3 是 GPT‑4.1‑mini 在独立训练集的 300 条 judge 数据上微调，[paper.txt](/work1/zixuan/projects/agent_memory/ref/paper.txt:248)。但正文只说 “outperforming / strong improvements”，没有报告这项比较的显著性检验。

   另外，RegAgent 的 C1/C2/C3 不是三个 GPT judge，而是 ground-truth absolute-error threshold 1.6/1.4/1.2。

2. strict 是模拟 human oracle，不是真实逐条人工标签。

   作者明确说实验中通过 generated output 与 ground truth 比较来模拟，[paper.txt](/work1/zixuan/projects/agent_memory/ref/paper.txt:263)。

3. Xiong 不只处理“一元 quality”。

   - addition 的 \(\pi(q,e)\) 是写入时 intrinsic execution quality，[paper.txt](/work1/zixuan/projects/agent_memory/ref/paper.txt:191)。
   - history deletion 已经是“某 record 在未来 retrieval 分布上的平均下游效用”，[paper.txt](/work1/zixuan/projects/agent_memory/ref/paper.txt:338)。
   - §4.3 明确认识到通过初始质量过滤的记录仍可能与当前任务错配，[paper.txt](/work1/zixuan/projects/agent_memory/ref/paper.txt:485)。

因此安全的 related-work 表述是：

> Xiong et al. study write-time execution-quality filtering and history-based pruning by average downstream evaluator scores, and explicitly recognize that quality-filtered experiences can remain misaligned with later tasks. CausalMemBench isolates a complementary residual: a source-valid memory may still be pairwise program-incompatible with a target. Its P×S factorial and no-memory pairing distinguish net utility, helpful transitions, and harmful transitions that a per-record average utility alone does not separately identify.

不要写“他们只管 quality，我们才发现 applicability”。

## 2. 数值审计：重算基本正确，但 harmful flip 改了 estimand

我从两组冻结 rollout 独立复算：

- 每模型 3840 行；
- 六个 cell 各 640；
- 所有 uplift 和 flip 计数与你一致。

但你表中的 59/350=16.9% 不是论文冻结的 HFR。需要同时保留两个指标：

\[
h_{\mathrm{joint}}=P(Y_N=1,Y_m=0),\qquad
h_{\mathrm{cond}}=P(Y_m=0\mid Y_N=1).
\]

论文代码使用前者，分母是全部 640 对，[analyze.py](/work1/zixuan/projects/agent_memory/pilot/analyze.py:164)。

| 模型/cell | joint HFR | conditional HFR |
|---|---:|---:|
| 7B A11 | 27/640 = 4.2% | 27/350 = 7.7% |
| 7B A10 | 60/640 = 9.4% | 60/350 = 17.1% |
| 7B A01 | 59/640 = 9.2% | 59/350 = 16.9% |
| 7B A00 | 95/640 = 14.8% | 95/350 = 27.1% |
| 3B A11 | 98/640 = 15.3% | 98/269 = 36.4% |
| 3B A10 | 133/640 = 20.8% | 133/269 = 49.4% |
| 3B A01 | 120/640 = 18.8% | 120/269 = 44.6% |
| 3B A00 | 113/640 = 17.7% | 113/269 = 42.0% |

建议：

- `joint HFR` 继续作为预期总体伤害的主指标；
- `conditional HFR` 作为“原本能做对的任务被破坏”的安全指标；
- 不能都简称 paired harmful-flip rate。

## 3. (a) “均值看不见 flip 风险”如何裁决

广义说法是平凡且字面不准确。二元结果下：

\[
E[Y_m-Y_N]
=P(\text{helpful flip})-P(\text{harmful flip}).
\]

所以均值不是“看不见”harmful flip，而是把正负转移相减，丢失了各自质量。

当前可以成立的经验 finding 是：

> 在冻结 7B 网格上，A01 的 79 个 helpful flips 与 59 个 harmful flips 相互抵消，产生 +3.1pp 净 uplift；因此正的有限样本平均值可与 9.2% joint / 16.9% conditional downside mass 共存。

但现在不能写“系统性解耦”，原因有三：

1. A01 的 +3.1pp 没有总体推断支持。

   我的 family-cluster bootstrap：

   - A01 uplift：+3.13pp，95% CI [−3.91, +10.31]pp，\(p\approx.40\)。
   - A10−A01 uplift：+1.09pp，CI [−6.56,+8.59]pp，\(p\approx.80\)。

2. A01 的机制异质性很大。

   7B 逐 archetype：

   | archetype | A01 uplift | joint HFR |
   |---|---:|---:|
   | aggregate_gate | +15.6pp | 5.6% |
   | conditional_write | −11.9pp | 13.1% |
   | delete_after_capture | +21.9pp | 1.3% |
   | two_row_transfer | −13.1pp | 16.9% |

   这更像“聚合均值掩盖相反机制”，不是所有 near-miss 都呈正均值/高风险解耦。

3. A10 vs A01 不是识别 P 的干净对比。

   它同时改变 P 和 S。控制 S=1 的 P 对比应是 **A11 vs A01**。7B 的 A01−A11 joint HFR 差为 +5.0pp，family-bootstrap CI [+2.19,+8.13]pp，当前 exploratory \(p<.001\)。这是更合适的风险证据。

要升级成正式 finding，必须冻结：

- 主对比：A01−A11，固定 S=1；
- 指标：\(\mu,h_{\mathrm{joint}},h_{\mathrm{cond}},h_{\mathrm{help}}\) 四项全报；
- family-cluster bootstrap，40 family 为簇；
- 两模型×两个主 endpoint 的 Holm \(m=4\)；
- model×cell interaction；
- 四 archetype interaction/分层；
- 若声称“高风险操作不可接受”，必须增加 severity-weighted loss。当前 terminal success 把删除错误和普通失败等权，不能支持伦理严重性 claim。

“系统性解耦”的确认门应为：

- A01−A11 的 HFR 差经 Holm 后两模型均下界 \(>0\)；
- 至少 3/4 archetype 同方向；
- 同时 A01 的 mean-uplift 与风险结论分别有 CI 支持。

当前数据只支持：**7B 上存在显著 downside excess，但正均值只是点估计；作为已有机制 finding/appendix 够，尚不足成为新第三贡献。**

另一个事实错误是：

> “Xiong 式 deletion 不会删 A01”不成立。

Xiong 用的是 absolute downstream evaluator score 与任务特定 \(\beta\)，不是 uplift-vs-N。7B A01 absolute success 约 57.8%；\(\beta=0.7\) 会删，\(\beta=0.5\) 可能保留。只能说“若使用 mean uplift 且阈值为 0，聚合 A01 会被保留”。

## 4. (b) 离线序贯模拟的合法边界

### 合法部分

完整析因允许精确计算：

> 一个已经冻结、仅用决策时可观察量、对每个实例从四张 A 卡或 N 中选择一个动作的静态 contextual policy，在这 640 个有限实例上的 policy value。

这不是 IPW/DR，因为所有候选动作结果都在表里。

但“零估计误差”只能限定为：

- 固定策略；
- 固定有限网格；
- 固定 stream/order；
- 没有用同一 outcome 调阈值；
- 不外推到新 family、随机种子或动态 bank。

一般化仍需 family-cluster CI 和 held-out-family 评估。

### 不能合法模拟的部分

现有网格不能称 Xiong-style longitudinal deletion：

- 800 个非空 memory ID，每个只暴露 4 次；
- 四次都是同一 `(family,sibling)` 上的 seed 变化，不是多种未来 query；
- Xiong 常用最小 retrieval count \(n=5\)，当前每条 memory 最多 4 次；
- 即便 3 次均无伤害，单侧 95% CP 风险上界仍约 63.2%，无法认证 10% 风险；
- fixed injection 没有 bank-size→retrieval competition；
- memory 不由 agent 新写入，没有 error propagation；
- 当前 cell outcome 被假定不依赖过去 bank 状态，动态系统的这种无干扰假设并不成立。

最大效度威胁不是“卡由 generator 生成”本身，而是：

> **缺少 bank-state interference 与 feedback transition：在真实系统里，addition/deletion 会改变后续检索和生成；当前查表 outcome 与历史 bank 内容无关。**

因此裁决：

- **GO**：称为 `offline full-information contextual admission/routing replay`。
- **NO_GO**：称为 longitudinal memory-management、history-based deletion 或 self-degradation simulation。
- 可做一个弱的 leave-one-seed-out repeat-exposure pilot，但必须声明它等价于“同一 pair 已有 3 次 canary 暴露”，不是免费的长期历史。

策略更新时也禁止使用 \(Y_N\)、uplift 或 harmful flip；部署中这些是反事实。策略只能看到被选动作的实际 evaluator score。N 和其他 arms 只用于最终离线评分。

## 5. (c) 微调 judge 裁决

**Xiong C3 不改变既有裁决：SFT P-judge 继续 DEFER；SFT extractor 优先级不变。**

原因不是简单的“300 太少”，而是监督目标不同：

- Xiong：同分布的一元 execution-quality label；许多任务有 ground truth/evaluator。
- P judge：二元关系标签；部署不可得；关键要求是未见失配机制迁移。
- Xiong 没有展示 leave-one-misalignment-mechanism-out 泛化。
- 你们 640 对的 LOAO 失败说明“更多同 generator 二元标签”不能作为迁移证据，但还不能严格证明模型容量永远无关。

P-judge 只有同时满足以下条件才可重开：

1. 训练标签来自合法接口/人工结构标注，不是把 sealed P 当部署可得标签。
2. 至少第五、第六种未见机制，且 renderer-disjoint 或外部构造。
3. 模型、prompt、阈值在 challenge P 解封前冻结。
4. macro-LOAO 相对 P̂ v1 提升 ≥0.10 AUC。
5. S=1 切面 A01 accept ≤0.10、A11 retain ≥0.50，整体及逐机制。
6. confirmatory 规模至少 100 families/机制；沿用 R2 的 800 primary pairs 与精确区间门。
7. 与 deterministic structured comparator、简单文本基线同时比较。

如果微调的是 **utility/risk judge** 而不是 P judge，则更合理，但名称和 estimand 必须改为预测：

\[
\mu(x,m)=E[Y_m-Y_N],\qquad
r(x,m)=P(Y_N=1,Y_m=0),
\]

并采用双门：

\[
\operatorname{admit}
\iff \operatorname{LCB}(\mu)>0
\land \operatorname{UCB}(r)<\alpha .
\]

这仍需要 randomized canary 或完整析因生成训练标签；不能宣称从普通单臂日志免费得到反事实 risk。

## 6. (d) 与 BLICC 的两周 CPU 排序

两条线互补，但必须隔离：

- BLICC：问“接口信息能否识别 P”。
- consequence line：问“绕开 P，能否直接做风险调整决策”。

顺序固定为 BLICC 先。由于你现在已经看过 outcome 并提出假设，后半段只能叫 **locked post-hoc evaluation**，不能再叫 blind/preregistered。

### Week 1：BLICC

按已有五天计划执行。接口规则不得读取 outcome。

- PASS：继续 interface paper 路线。
- FAIL：关闭现有 benchmark 上的 P-interface 第三贡献；不以 outcome 结果挽救 P。

### Week 2：Consequence Profile Gate

Day 6 先 hash：

- \(\mu,h_{\mathrm{joint}},h_{\mathrm{cond}},h_{\mathrm{help}}\) 定义；
- A01−A11 为主对比，A10−A01 仅为策略排序；
- family-cluster bootstrap；
- Holm \(m=4\)；
- archetype/model interaction；
- 静态 policy 输入字段；
- 禁止策略读取 P、N-counterfactual、其他未选 arm outcome。

Day 7–8：

- 全量 consequence decomposition；
- mean-only、similarity-only、abstain/N、risk-constrained 四类基线；
- P-oracle 只能作为 ceiling，不能参与策略。

Day 9–10：

只在 repeat-exposure pilot 中比较 risk-constrained 与 mean-only：

- joint HFR 至少下降 3pp，且 95% family-cluster CI 上界 \(<0\)；
- mean uplift 非劣，95% CI 下界 \(>-3\)pp；
- 四 archetype 中至少 3 个不恶化；
- 阈值用外层 held-out family 评估。

任一门失败：

- 不启动 LLM 微调；
- history-deletion 模拟降为 appendix descriptive audit；
- utility U 的在线 canary 路线保留，但不得声称已有部署验证。

最终定位应是：

> **后果不是 P 的代理标签；它是更接近部署决策的另一估计对象。**  
> Xiong 为“平均历史效用可管理 memory”提供先例；你们可能增加的结果是“平均净效用会掩盖成对 downside transitions，因此 admission 需要 mean–risk 联合控制”。这与台账中已经保留的 TRU-Mem 窄路线一致，而不是重启 P judge。