# Round 2 裁决

总方向通过，但有两项关键修正：

1. **signature-obscured collision set 应成为第一个实验交付物**，但在它之前必须有一个约半天的 signature-atom 规范冻结；不能只重分 157/532。
2. **D 不能按“最终状态转移逐点相等”升级为 certified P。** 在本 DSL 中，certified P 的闭合路径是 `F 保留可执行规范 → canonical signature/IR 比较`；差分 witness 用于验证规范与实现一致、提供反例证书，不是 P 的基本定义器。

---

## 1. “经验下界为 0”和 explicit-policy 是同一事实吗？

### 裁决：部分成立，因果表述需收窄

成立的部分：

- 四类 near-miss 的判别位确实都被 renderer 直接语义化进文本：
  - P1：`above` / `at or below`；
  - P2：`from source to destination` 直接翻转；
  - P3：`none open` / `at least one done`；
  - P4：明确写出 archive 或“No archival copy is required”。
- 因此当前 benchmark 是 **signature-explicit upper-bound setting**，这确实解释了 family-CV 文本分类器为什么能学到很强信号。

不成立的强版本：

> “经验 Bayes 下界为 0，恰恰因为所有 signature 位逐字明写。”

当前下界为 0 的直接数学原因是：640 个完整 O 全部唯一，没有同 O 反 P collision。即便真实生成映射是多对一，只要样本没有重复观测，也会得到这个经验下界。signature-explicit 是合理机制解释，但尚未由干预实验识别。

此外，不能只审计四个 near-miss 位。完整 signature atom 至少包括：

- archetype / step multiset；
- P1 J1/J2 policy-read；
- partial-order/dependency/commutation；
- predicate operator/polarity；
- P2 source/destination role；
- P3 aggregate subset + operator；
- P4 archive presence + archive-before-delete dependency；
- abstract write/effect roles。

例如 J1/J2 也是 P1 signature 的组成部分，[program_dsl.py](/work1/zixuan/projects/agent_memory/pilot/program_dsl.py:104) 明确把它写进 signature。

### 正确的第一交付物

不是“重分 157/532”，而是：

**Signature Observability Census v1**

对全部 532 唯一文本、每个适用 signature atom 标注：

- `EXPLICIT`：文本直接蕴含；
- `RESOLVABLE`：借助已提供 schema/policy/provenance 唯一确定；
- `OBSCURED`：存在至少两个与 O 一致、signature atom 不同的程序；
- `NA`。

每个 `EXPLICIT/RESOLVABLE` 必须有 evidence span 或接口字段；报告：

\[
\mathrm{AtomCov}(A)
=\frac{\#\text{被接口 }A\text{ 唯一确定的 signature atoms}}
{\#\text{适用 atoms}}.
\]

这是 532 全量 census，不需要抽样 CI。若 `OBSCURED=0`，可以写：

> Current CausalMemBench renders every evaluated signature distinction observably.

不能写“P 判定 trivial”：A10 的 α-renaming、否定归一和跨域角色对齐仍然不是字符串 lookup。

### collision set 是否第一优先？

**是。** 更精确地说：

1. P0：冻结 atom ontology 和 observability 判据；
2. P1：完成 532 census；
3. P2：立即构造 signature-obscured collision set。

P2 必须逐 atom 隐藏，而不是只隐藏 polarity：

- 同一文本，policy snapshot 中 operator 不同；
- 同一文本，provenance version 对应 source/destination mapping 不同；
- 同一文本，schema 中 child-set definition 不同；
- 同一文本，workflow version 中 archive requirement 不同。

每个 collision class 内应有完全相同的 \(O_A\) 和平衡的 P=0/P=1。若 collision 子集占总体质量 \(q\)，且每个 collision class 标签 1:1，则任何 deterministic text-only estimator 的 0–1 error 下界为 \(q/2\)。

---

## 2. D 能否靠有限状态探针 certified P？

### 裁决：按“最终 DB 状态函数相等”表述，否

有三个代码级反例。

#### 反例 1：不同 signature，相同最终状态

P1 J1 和 J2 signature 不同，因为 J2 多一个 policy READ；但当 policy 表给出的 θ 与 J1 θ 相同时，两者对业务表的最终状态完全相同。任何只比较 final snapshot 的探针都看不见额外 READ。

#### 反例 2：相同 signature，不同最终状态

具体 θ 不属于 equivalence class。[program_dsl.py](/work1/zixuan/projects/agent_memory/pilot/program_dsl.py:10)

因此两个 P=1 的实例可有不同 θ，并在同一具体数值状态上走不同 branch、产生不同最终状态。于是：

\[
P=1\nRightarrow T_{z_x}(s)=T_{z_m}(s)
\]

对裸 concrete state 并不成立。

#### 反例 3：partial order 不等于 final-state semantics

两个程序可以有不同依赖边，但在无故障、确定性执行中产生相同最终数据库。若 P 把 partial order 算作 signature，必须观察 labeled trace、故障阻断或全部合法 schedule；final snapshot 不够。

### 在什么条件下可以 certified P？

如果 F 在写入时保留 canonical executable IR，那么本 benchmark 的 P 按定义就是：

\[
P=1
\iff
\operatorname{Canon}(IR_x)=\operatorname{Canon}(IR_m).
\]

这里的 certified P 来自 canonicalization/hash，不需要通过 probes 猜。

差分 witness 的作用变成：

- 验证 executable artifact 的实际行为符合所声明 IR；
- 对 P=0 给出人可审计的 distinguishing counterexample；
- 检测 stale policy/schema 或实现漂移。

### 若仍要证明有限 witness suite 完备，证明义务如下

1. **Universe closure**：明确程序宇宙是当前有限 signature catalog，还是整个参数化 DSL。只对已枚举 catalog 完备，不能写 DSL-universal。
2. **Canonical quotient**：证明 entity、table、字段、θ 等 instance parameters 被正确 α-renaming/商掉。
3. **Observation semantics**：观察量必须包含 canonical labeled trace、writes、branch outcome 和 dependency/fault behavior；不能仅含终态。
4. **Soundness**：同 signature 的所有允许实例在参数归一后具有相同 abstract trace set。
5. **Completeness**：每一对不同 signature 至少有一个 valid witness，使 abstract traces 不同。
6. **Reachability policy**：明确只要求 generator-valid initial states，还是所有 type-valid states。若只覆盖 reachable states，结论必须写成 reachable-state completeness。
7. **Schedule quantification**：对偏序的全部 linear extensions 枚举，或证明独立操作 confluence。
8. **Fault model**：要识别 archive-before-delete 等依赖边，必须注入 archive failure/中断；无故障最终态不足。
9. **Nondeterminism**：当前 SQLite/tool 环境基本确定；未来若有随机工具，需比较 trace distributions 或对所有 outcomes 量化。
10. **Common observer**：不能让两个程序各自用自己的 terminal predicates 判自己成功；否则 near-miss 当然都通过。必须用统一 canonical observer。
11. **Artifact conformance**：必须证明存下来的 executable IR 确实是当时执行的程序，而非事后声明。

若第 4–5 项无法形成证明，D 只能叫 `catalog-complete mutation suite` 或 \(V_T\)，不能叫 certified P。

---

## 3. F 与 Skill-Pro 的重叠

### 裁决

- **原始 F：降级。** typed pre/postconditions、可执行 workflow、activation/execution/termination conditions、canonical role graph 本身已高度拥挤，不能作为 novelty。
- **F′：保留两项窄 delta，GO to develop。**

保留项正是你提出的：

1. **Pair-discriminating witness**：不是“该 skill 能成功”的普通 unit test，而是能区分某 memory 与候选 near-miss equivalence class 的最小反例。
2. **接口元素的 P-identifiability value**：利用 sealed P 系统测量 text/schema/provenance/executable artifact/witness 分别买到多少 certified coverage。

根据仓库对 Skill-Pro 的已核记录，它生成并验证带 activation/execution/termination 条件的可执行 skill；没有证据表明它做了 pairwise equivalence witness 或 sealed-P interface-ablation。[technical route](/work1/zixuan/projects/agent_memory/tech_report/causalmemagent_top_venue_technical_route.md:87)

但边界必须诚实：

- mutation testing、distinguishing tests、proof/test-carrying artifacts 在 PL/软件测试领域有强近邻；
- “首次在 agent memory 使用 witness”目前不得声称；
- “只有我们能做”也不得声称，应改为“our sealed equivalence labels make this quantity directly measurable”。

本轮公开检索未返回可独立核验的 Skill-Pro 全文材料，因此 F′ 的 novelty confidence 只能给**中等偏低**；正式 claim 前仍需针对 `skill verification / test-carrying agents / mutation-based workflow validation / distinguishing tests` 做一次专门检索。

---

## 4. 接口信息价值曲线是否是正确 estimand？

### 裁决：是，需加三项指标和两层曲线

你的 `Cert/Prec` 是正确核心，但需补：

\[
\mathrm{Validity}(A)
=\Pr[P^*\in\mathcal I_P(O_A)]
\]

以及接口成本：

\[
\mathrm{Cost}(A)
=(\text{bytes},\text{write latency},\text{probe calls},\text{rollback need}).
\]

推荐完整报告：

\[
\begin{aligned}
\mathrm{Cert}(A)&=\Pr[|\mathcal I_P(O_A)|=1],\\
\mathrm{Validity}(A)&=\Pr[P^*\in\mathcal I_P(O_A)],\\
\mathrm{Prec}(A)&=\Pr[\widehat P=P^*\mid |\mathcal I_P|=1],\\
\mathrm{Cost}(A)&=\text{storage/runtime/acquisition cost}.
\end{aligned}
\]

必须再分两层：

1. **Information ceiling**：假设接口字段被无误读取时，理论上能识别多少 P；
2. **Achieved certifier**：实际 parser/canonicalizer/witness checker 达成多少。

否则 parser 失败和接口信息不足会再次混在一起。

接口梯度建议冻结为：

1. T：text；
2. T+S：tool/schema；
3. T+S+V：policy value/version/provenance；
4. T+S+V+X：canonical executable artifact；
5. T+S+V+X+W：pair-discriminating witness。

主结果必须同时在：

- 当前 natural explicit set；
- signature-obscured collision set；

上报告。只在 natural set 上跑，T 点会接近 ceiling，曲线没有科学信息。

### 贡献定位

- **identification/interface contribution：成立。**
- **不能伪装成 admission baseline win：正确。**
- **进入本文 main section：有条件 GO。**
- **单独支撑一篇顶会论文：当前 NO_GO。**

进入 main section 的最低门：

- formal collision/lower-bound proposition；
- 非平凡接口曲线：至少一个非文本接口 \(\Delta\mathrm{Cert}\ge0.20\)，family-cluster 95% LB>0；
- final interface 每机制 `Cert≥0.80`；
- singleton precision 的同时校正 LCB≥0.95；
- certifier 冻结后的第五/第六 mutation challenge；
- renderer-disjoint confirmatory set。

若只有“手工隐藏四个位，然后手工 provenance 恢复”，它是构造演示/appendix。要成为独立论文，还需要第二个独立 DSL、真实 workflow system 或真实 write-time artifact pipeline。

---

## 5. 簇数与 pair 数

### 独立单位

- **family 是 cluster**；
- archetype / near-miss mechanism 是 stratum，不是 cluster；
- sibling、target、style、seed 和同 family 内多个 memory pair 都是簇内重复，不能增加独立 n。

最干净的 confirmatory 设计：

- 每个 family 用冻结 hash 预选一个 target sibling；
- 产生一个 A01 和一个 A11 primary pair；
- 其余 sibling/pair 只作 secondary cluster analysis。

### 同时认证四机制 × 两端点

共有 8 个单侧声明：

- 4 个 `A01 accept ≤0.10`；
- 4 个 `A11 retain ≥0.50`。

用 Bonferroni 控制 family-wise 95%：

\[
\delta=0.05/8=0.00625.
\]

精确 CP 结果：

| families/机制 | A01 允许接受数 | A11 至少保留数 |
|---:|---:|---:|
| 49 | 0/49 | 34/49 |
| 60 | 0/60 | 41/60 |
| 80 | ≤1/80 | ≥52/80 |
| **100** | **≤2/100** | **≥63/100** |
| 120 | ≤4/120 | ≥75/120 |

因此：

- 数学最低值：**49 families/机制**，但 A01 必须零误收，脆弱；
- 推荐固定 confirmatory 预算：**100 families/机制**；
- 总计：400 families、**800 primary pairs**；
- 不允许看到 3 个 A01 误收后再加到 120 families。

100/机制还有一个好处：若 singleton cert 全部正确，Bonferroni 后 one-sided precision LCB≈**0.9505**。出现一个错误就过不了 0.95；若预期允许错误，必须事前选更大固定 n，例如 200/机制允许约 2 个错误仍维持该 precision 门。

这解决的是**同一构造分布内的统计认证**，不解决 mechanism/renderer 外推。

### 防 generator 自证

Confirmatory 100 families/机制必须：

- family split 在 rendering 前完成；
- 使用与开发集完全不共享实现的 renderer；
- certifier 和接口规则在 confirm renderer 生成前 hash；
- confirm renderer 由未写 certifier 的人实现；
- 第五/第六 mutation 在 certifier hash 后由独立 challenger 选择；
- challenge 失败不得用四机制结果 pooled rescue。

若 confirm 仍只用同一 renderer、同四 mutation，它只能认证 generator self-consistency。

---

## 6. 最小决定性实验序列

| 步骤 | 成本 | 动作与冻结 | Kill condition | 结果定位 |
|---|---|---|---|---|
| P0. Signature ontology freeze | CPU，0.5 天 | 冻结全部 signature atoms、EXPLICIT/RESOLVABLE/OBSCURED 判据、接口梯度、evidence 规则。允许读公开 DSL 定义，禁止读逐 pair sealed P。 | atom 定义无法和 `program_dsl` equivalence 一一对应则停。 | 工程前置 |
| P1. 532 observability census | CPU，1 天 | 全量逐 atom 审计，不只重分 157。 | 任何 atom 无法归类则修规范一次；第二次仍有语义歧义，停止“signature-explicit”claim。 | 可写 limitation/diagnostic |
| P2. Formal semantics audit | CPU，1 天 | 固化上述三个反例；定义 canonical IR、参数 quotient、trace observer 和 witness 语义。 | 无法证明 canonical hash 与 benchmark P 等价，则 certified-P 主张停止，全部降为 \(V_T\)。 | 形式结果，可进主文 |
| P3. Collision dev set | CPU，20 families/机制 | 逐 atom 制造同 O 反 P；仅验证 byte identity、标签平衡、无残余词泄漏。此集永不用于正式结果。 | 同 O identity、1:1 标签平衡、oracle validity 任一不是 100%，停；不得扩大样本补救。 | 工程件 |
| P4. Protocol/hash freeze | CPU | 冻结 certifier、canonicalization、interface ladder、primary pair hash、n=100/机制、8 个端点、Bonferroni、成本指标、所有 kill gates。sealed instance labels继续封存。 | 任何阈值仍需看 P 结果才能定，则不准进入 confirm。 | 治理件 |
| P5. Renderer-disjoint confirm set | CPU，400 families/800 pairs | 独立 renderer 生成 100 families/机制；提交全部预测/识别集后才启封 P。 | A01>2/100 或 A11<63/100 任一机制即失败；Validity<1；final Cert<0.80；Prec LCB<0.95；ΔCert<0.20 或 LB≤0，任一失败即停。 | **核心论文结果** |
| P6. Canonical+Witness checker | CPU | P 由 canonical hash 判；为每个 P=0 生成最小 distinguishing witness，并做 fault/schedule coverage。 | known catalog 不能 100% pairwise separate，或同 signature 出现 false separation，kill completeness；保留 \(V_T\)。 | 方法/证明件 |
| P7. Frozen fifth/sixth mutation | CPU，建议各100 families | certifier hash 后由独立 challenger 选 mutation；含 P=1 正控。使用与 P5 分开的 4 端点 multiplicity family。 | 任一机制 A01/A11/Cert/Prec 门失败，P5 降为 registered-four benchmark coverage，不得主张 unseen mechanism。 | **决定能否进主文** |
| P8. SFT φ extractor | GPU，可延期 | 仅 P0–P7 全过且确需从 NL 恢复 IR 时才运行既定 300/1k/3k/4k 曲线。checkpoint 只看字段质量，不看 P-AUC。 | 沿用已冻结 parse/grounding/coverage/LOAO 门；失败即停，不追加模型或数据。 | 工程实现；过外部 renderer 才可主文 |
| P9. 第二 DSL/真实 pipeline | CPU/GPU 视环境 | 证明接口曲线不只是 RelationalOps 构造。 | 无独立系统则不投独立 interface 论文。 | 独立论文门 |

### sealed oracle 之外必须冻结的内容

在 P5 前全部冻结：

- equivalence ontology 与 canonicalization；
- interface 元素及嵌套顺序；
- \(\Gamma(O_A)\) 构造规则；
- singleton/conflict/unresolved 决策；
- evidence/span/ABSENT/UNKNOWN 规则；
- collision 模板和 primary pair 抽样 hash；
- sample size、端点、multiplicity、CI 方法；
- Cert/Validity/Prec/Cost 和所有阈值；
- certifier代码 hash；
- confirm renderer 与开发 renderer 的隔离契约。

sealed oracle只能用于：

- confirm 数据构造者的独立 validity 检查；
- 预测提交后的最终评分；
- completeness proof 的逐 signature 对照审计。

**最终投资决定：**暂停 4,000-text SFT 扩建，把 CPU 资源先投入 P0–P7。若 renderer-disjoint collision curve 和 frozen unseen mutations 过门，再决定是否值得等 GPU 做 P8；否则整条线以“signature-explicit benchmark + text-only nonidentifiability construction”的负/边界结果收尾，不追加算力。