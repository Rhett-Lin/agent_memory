总裁决：

> 这是合法转向，但你把它抬高了一步。它不能“定义 P 的状态”，只能定义一个新的、部署可观测的**冲突证书状态**。  
> 正确记号应是 \(C_R(O)\in\{\text{CONFLICT},\text{UNRESOLVED}\}\)，不要叫 \(\tilde P\)。

“不给每对都猜 P”是成立的；“不再需要 P 真值”不成立——开发时可以不用 P，验证“触发是否可靠”仍必须用 sealed P、构造真值或形式化证明。

更关键的是：你第 3 节漏看了后续产物。comparator v0 已建成并跑完 640 对，现有结果不支持把 lane A 升级为主线。

## 1. 分类器→认证器：合法，但必须满足六个条件

合法类比不是“把失败分类器改名”，而是类型系统式的保守判断。但只有在存在 soundness 关系时才能称“认证”：

\[
C_R(O)=\text{CONFLICT}\Longrightarrow P^*=0.
\]

最小条件是：

1. **保持两个变量分离**

   - \(P^*\)：原 benchmark 程序等价真值，定义不改。
   - \(C_R(O)\)：规则 \(R\) 在可观测信息 \(O\) 上发出的证书。

   若把 \(C_R\) 直接重新命名为 P，就会把 measurement failure 藏进定义里。

2. **规则只能使用部署可得输入**

   文本、schema、policy/version provenance、合法 trace/witness；不得读取 family、archetype、near-miss kind、generator \(z\)、sealed signature。

3. **每次触发必须有 proof object**

   至少包含两侧 evidence span、规范化 semantic atom、冲突关系、normalizer/version hash。不能只输出一个 LLM verdict。

4. **矛盾必须落在 P 定义中的签名位**

   θ 不属于 P；可选 read、表面角色名、不同但逻辑等价的谓词表达也不能触发。

5. **缺乏证据只能 UNRESOLVED**

   非出现、抽取失败、UNKNOWN 都不能推出 conflict。

6. **同时报告 soundness 和 coverage**

   precision 会随 P=0 基率变化，不能单独用。必须至少报告：

   \[
   \begin{aligned}
   \mathrm{VetoPrec}&=P(P^*=0\mid C_R=\text{conflict}),\\
   \mathrm{VetoCov}&=P(C_R=\text{conflict}\mid P^*=0),\\
   \mathrm{FalseVeto}&=P(C_R=\text{conflict}\mid P^*=1).
   \end{aligned}
   \]

若没有形式证明、只有经验精度，建议名称为 `SUPPORTED_CONFLICT` 或 `selective conflict detector`，不要使用 `CERTIFIED`。

## 2. 非对称 conflict-only 是正确方向，但不是“安全准入”的充分条件

相对对称三值设计，conflict-only 更合理：

- match 需要封闭世界和完整性证书；
- conflict 可以由一个局部、签名相关的反例见证；
- 当前 IR 的 completeness 明显不足。

但有四个不健全风险：

- `<` 与 `>=` 可能因 negation/branch swap 而等价；
- source/destination 表面不同可能只是 α-renaming；
- 被见证的差异可能是 θ，而 θ 被 P 定义排除；
- 两侧抽取各自有误时，会制造假矛盾。

因此“一处字段不同”不够，必须是：

> 同一规范化 anchor 上、无法由允许的等价变换消去、且改变必要步骤/偏序/极性/写目标角色的矛盾。

准入规则也必须写成：

- `CONFLICT → reject`
- `UNRESOLVED → quarantine / risk controller / canary`
- 绝不能把 `¬CONFLICT` 解读为 P=1。

你写的 `¬CERTIFIED_CONFLICT ∧ 风险门` 只有在风险门本身独立受控时才合法。否则 unresolved 会被事实性地当成 match。

另外，P=0 不等于 harmful。Round 4 已显示部分 A01 有正平均效用。因此 conflict veto 是保守结构策略；是否值得拒绝仍需 policy-value/risk 评估。

## 3. 对扩编审计的读法：部分正确，但漏掉 comparator v0

审计本身确实是单侧字段 fidelity gate：

- missing 计作 all-row disagreement；
- `pred_op` present-only 297/327=90.8%；
- 审计明确只允许 positive-only/soft use，[AUDIT_EXPANDED.md](/work1/zixuan/projects/agent_memory/pilot/peval/phi_d/audit_expanded/AUDIT_EXPANDED.md:96)。

所以：

> “全行字段 audit 没有直接测 pair-level VetoPrec/VetoCov”是对的。

但“S2 比较器从未建成”已经过时。后续 comparator v0 已跑完 640 对，并被裁 DEMOTE，[REPORT_V0.md](/work1/zixuan/projects/agent_memory/pilot/peval/phi_d/comparator_v0/REPORT_V0.md:1)。

### 现有 conflict-only 重算

把 comparator v0 的 `verdict=contradict` 直接作为你的 conflict certificate：

- 触发 218；
- 真 P=0：116；
- 假 P=1：102；
- `VetoPrec = 116/218 = 53.2%`；
- `VetoCov(P=0) = 116/320 = 36.3%`；
- `FalseVeto(P=1) = 102/320 = 31.9%`；
- A01 conflict coverage = 56/160 = 35.0%；
- A10 false veto = 50/160 = 31.3%；
- A11 false veto = 52/160 = 32.5%。

这正是“结构不完整的两侧 IR 互相制造差异”：A01 与 A11 的 conflict 率几乎相同，[REPORT_V0.md](/work1/zixuan/projects/agent_memory/pilot/peval/phi_d/comparator_v0/REPORT_V0.md:100)。

如果按你的实际准入规则“所有非 conflict 都 admit”，则：

- A01 accept = 104/160 = 65.0%；
- A10 retain = 110/160 = 68.8%；
- A11 retain = 108/160 = 67.5%。

因此远未达到 A01≤0.10。

### pred_op-only 子规则

我又把冻结 verdict reasons 中仅由 `PRED_OP_MISMATCH` 触发的 pair 单独重算：

| 指标 | 结果 |
|---|---:|
| triggers | 48 |
| 真 P=0 | 45 |
| 假 P=1 | 3，全部 A10 |
| VetoPrec | 93.75%，单侧95% LCB **84.6%** |
| P=0 coverage | 45/320 = 14.1% |
| A01 coverage | 11/160 = **6.9%**，LCB 3.9% |
| P=1 false veto | 3/320 = 0.94%，UCB 2.41% |
| A10 false veto | 3/160 = 1.88%，UCB 4.77% |
| A11 false veto | 0/160，UCB 1.85% |

这是一个“低假杀、极低 A01 覆盖”的 selective detector，但：

- 点 precision 已低于 0.95；
- precision LCB 只有 0.846；
- 只能抓 6.9% A01；
- 这是看过 reason outcomes 后的 post-hoc 子集，不能作为确认性结果。

所以 lane A 维持 **baseline-only / DEMOTE**。不能因改用 precision/coverage 指标而撤销冻结 kill。若继续，应开一个新的 `conflict-certificate` lane，并使用全新 challenge set。

## 4. P4“结构性不可认证”：一般命题对，套到当前 benchmark 上错

当前 P4 不是单纯“没提 archive”。generator 明确写：

- “No archival copy is required”，[generate_families.py](/work1/zixuan/projects/agent_memory/pilot/generate_families.py:1098)；
- instruction 也写 “no archival copy is needed” 或 “do NOT leave any audit entry”，[generate_families.py](/work1/zixuan/projects/agent_memory/pilot/generate_families.py:1209)。

所以当前 P4 是**有显式负证据的存在型矛盾**，原则上可被文本认证。φ 的 `archive_capture` 只有 51.7% 是抽取器失败，不是文本不可识别证明。

正确的一般结论是：

> 在 open-world text observation 下，单纯不提某步骤不能证明该步骤不存在；若含 archive 与不含 archive 的程序产生相同可观察文本，任何 sound text-only certifier 都必须 abstain。

要写进论文，需要：

1. 全量 census：P4 的 omission 是 `explicit-negative / implicit-omission / unknown` 哪一种。当前 generator 预期 explicit-negative≈100%。
2. 构造同一 \(O_{\text{text}}\)、相反 P 的 collision pairs。
3. 冻结规则在 collision set 上必须输出 unresolved。
4. 加 schema/provenance/witness 后，量化 conflict coverage 增量。
5. 形式化说明：若 \(|I_P(O)|=2\)，sound certifier 的该子集 coverage 上界为 0。

因此“缺失型在文本上永远不可认证”太强；“**仅由 non-mention 表达的缺失在 open-world 文本中不可认证**”成立。

## 5. 主指标不能只选 policy value；oracle-P 也不是天花板

若论文 claim 是“冲突认证器”，主门必须先是认证 soundness/coverage。否则一个完全不懂 P、但恰好利用 A01 正效用的 gate 也能获得高 policy value。

建议层级：

### Gate 1：证书有效性

- `VetoPrec` 单侧95% LCB ≥0.95；
- `FalseVeto(P=1)` 单侧95% UCB ≤0.05；
- 上述 false veto 对 A10、A11 和逐机制分别成立；
- A01 `VetoCov` LCB ≥0.20，才有资格升级为方法；低于此值只作诊断。

### Gate 2：最终准入安全

对 `conflict certifier + risk gate` 整体：

- A01 accept UCB ≤0.10；
- A11 retain LCB ≥0.50；
- **新增并冻结 A10 retain LCB ≥0.50**；
- 逐机制同报。

A10 门是必须的，因为 conflict-only 最危险的失败正是把跨表面 P=1 当矛盾。现有 comparator 已证明这一点。

### Gate 3：policy value

- family-cluster bootstrap，family=40 个独立簇；不能沿用当前 instance bootstrap。
- 与 best deployable baseline 做配对非劣，margin −3pp。
- 同时要求相对 risk-only gate 的 joint HFR 不恶化；若 claim 安全改进，则 HFR 差的95% UCB应 \(<0\)。
- 必须做 `risk-only` vs `certifier+risk` ablation，防止 certifier 是冗余工程件。

### “oracle-P ceiling”更正

当前策略先由 similarity 取 top-1；380/640 是 A11，260/640 是 A01，[README.md](/work1/zixuan/projects/agent_memory/pilot/peval/README.md:103)。`oracle_p` 只是“top-1 的 P=1 才 admit”，[gate_eval.py](/work1/zixuan/projects/agent_memory/pilot/peval/gate_eval.py:154)。

它不是 utility ceiling，因为 P=0 可能有益、P=1 也可能有害。

我用冻结结果计算的真正 hindsight ceiling：

| 作用域 | 7B uplift vs N | 3B uplift vs N |
|---|---:|---:|
| oracle-P baseline | +8.13pp | +1.25pp |
| true outcome oracle，仅 top-1/N 二选一 | **+14.38pp** | **+14.38pp** |
| true outcome oracle，四张 A 卡/N 五选一 | +28.44pp | +25.31pp |

因此 P̂@0.6 的 +8.59pp：

- 不是“追平 oracle 天花板”；
- 只捕获 top-1 outcome-oracle headroom 的约 59.8%；
- 比 oracle-P 多 0.47pp 可能来自接受有益 A01或拒绝有害 P=1，不必然只是抽样噪声；
- 阈值仍是在同一数据上选的，[README.md](/work1/zixuan/projects/agent_memory/pilot/peval/README.md:135)，不能作为确认性 policy result。

## 6. 指纹纪律

“比较符极性”作为概念不天然是指纹；“看到 `>` vs `<=` 就拒绝”则是机制指纹。

一个合法通用规则必须：

- 先把 predicate 规范化到 anchor、量词、negation、branch-effect mapping；
- 能识别 `not(x≤t)` 与 `x>t` 等价；
- 能识别 op 改变但 branch effects 同时交换时仍可能等价；
- positive controls 中必须包含表面 op 不同但 P=1；
- negative controls 中包含表面 op 相同但 anchor/effect 不同；
- 在 `<,≤,>,≥,=,≠` 和不同语言渲染上测试；
- 规则输出 evidence certificate，而非关键词命中。

现有四机制只能作为 development set，因为规则作者已经知道它们。确认纪律收紧为：

1. rule author 冻结代码、ontology、normalizer、触发理由和 hash；
2. challenger 在 hash 后选机制，且不是原四机制作者；
3. 至少一个新存在型冲突、一个隐式 omission/provenance 冲突；
4. 每个新机制同时造 P=0 challenge 和 P=1 adversarial positive controls；
5. renderer-disjoint、词汇和正负 cue counterbalanced；
6. scorer 只返回预注册聚合，不给逐例反馈后改规则。

样本量：

- 零错误时，单侧95% precision LCB≥0.95 至少需要 **59 个实际触发**；
- 若四项 Bonferroni，需约 **86 个触发/机制**；
- 若 coverage 门为20%，要期望获得86个触发，需约 **430个 P=0 families/机制**；
- 每 family 再配一个 P=1 正控，则两个新机制的正式确认约 1720 pairs。

100 families/机制只能作为 screening，不能保证 precision 门有功效。

## 7. 两周 CPU-only 排序

你的“先跑便宜认证器”只批准为半天的 forensic triage，不批准先重写 comparator。

### Day 1：冻结 v0 的 conflict-only 重评分

不改规则，只重报：

- any-conflict；
- pred_op-only；
- VetoPrec/VetoCov/FalseVeto；
- actual non-conflict admission；
- policy point value。

二值门：

- precision LCB≥0.95；
- A01 coverage LCB≥0.20；
- P=1 false-veto UCB≤0.05。

现有 pred_op-only 已知会因前两项失败。结论应是 `NO_GO_UPGRADE_LANE_A`，不继续在现有 640 上调规则。

### Day 2–6：BLICC

继续原计划。它回答 text-only conflict information ceiling 是否至少有20%。如果 ceiling 本身低于20%，新的 text certifier 直接停止。

### Day 7–8：只在 BLICC 支持时冻结新 lane

产物：

- `C_R` 形式语义；
- proof-object schema；
- allowed observations；
- equivalence normalizer；
- 规则 hash；
- 完整 kill gates。

现有四机制只能用于单元测试，不能作为确认集。

### Day 9–10：独立 challenge screening

- 第五、第六机制；
- 各100 families；
- 每 family 一对 P=0/P=1；
- 共400 pairs；
- CPU-only一次评分。

筛查任一失败即停止：

- precision point <0.95；
- false veto >0.05；
- coverage <0.20；
- positive controls 任一机制出现系统性假杀；
- combined gate 相对 risk-only 没有 HFR 改善。

筛查通过后才排正式的430 families/机制确认集；不在本两周内用当前四机制补样本或调规则。

最终定位：

> **这不是重新定义 P，而是建立一个相对于 P 有待证明 sound 的、保守且可弃权的 conflict certificate。这个研究方向合法；但当前 comparator 已经给出负结果，不能升级旧 lane。新机会只存在于“proof-carrying、conflict-only、独立新机制确认”的新 lane。**