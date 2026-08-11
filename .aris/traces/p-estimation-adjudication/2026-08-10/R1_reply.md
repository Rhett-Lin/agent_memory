# Round 1 裁决

**总裁决：GO with strategic redefinition。**

- **NO_GO**：把“提高 text-only P̂ 的 AUC”继续当作部署主目标。
- **NO_GO**：把 `157/532=29.5%` 宣称为“P 的不可识别下界”。
- **GO**：把 P 改成“可观测信息下的部分识别对象”，输出 `match / conflict / unresolved`。
- **GO**：A 继续一次严格受限的 SFT 可行性检验，但定位为 benchmark 验证件。
- **GO**：战略主线转为“新增信息通道的验证 D/F + 选择性弃权 E + 因果 utility B”。
- **NO_GO**：C 作为独立的 harmful-flip 文本分类器；应并入 B 的随机化 outcome 模型。
- **第三贡献门**：仅同-generator 上把 P̂ 做高，必须留 appendix；只有在独立环境、隐式任务和已发表 admission baseline 上形成胜出结果，才可升主文。

---

## 1. 两个核心论断

### 1.1 “29.5% 是 P 不可识别下界”：不成立

这 29.5% 测的是**具体数值参数 θ 没有在文本中展开**，不是 P 无法判定。

更关键的是，本 benchmark 的 P 等价类明确**排除具体 threshold/entity 值**：P 只取决于抽象步骤、偏序、算子方向和写目标角色；具体 θ 是 instance parameter，不属于 equivalence class。这在 [program_dsl.py](/work1/zixuan/projects/agent_memory/pilot/program_dsl.py:10) 已写死。

`FEASIBILITY.md` 还明确说明：

- 符号化案例仍然命名了 quantity，状态是 `present-symbolic`，不是 `unknown`；
- 12/372 join 冲突在 `z→text→IR` mint 流程中被消解；
- identical text 会得到 identical projected IR。[FEASIBILITY.md](/work1/zixuan/projects/agent_memory/pilot/peval/phi_d/sft0/FEASIBILITY.md:140)

我额外对 640 对做了 exact-text collision 检查：

- 640 个完整 `(instruction, memory_text)` 对全部唯一；
- 相同完整文本对、相反 P：**0 组**；
- 单独 memory 文本确有 73 个重复组，其中 37 组在不同 target 下对应不同 P，但 P 本来就是 pair relation，不能由 memory 单侧决定。

所以当前数据只能支持：

> 一些 latent parameter 无法从单侧文本恢复，text-only P 可能需要部分识别与弃权。

不能支持：

> 至少 29.5% 的 P 不可识别。

若要建立真正的下界，必须新造**同一完整可观测 O、相反 P**的 collision set，例如保持 instruction+memory 字面相同，只改变隐藏 policy snapshot。此时可报告经验 Bayes error 下界：

\[
R^*_{\text{text}}\geq
\frac{1}{N}\sum_o \min\{n_o(P=0),n_o(P=1)\}.
\]

当前这个和为 0。

### 正确的 P estimand

设完整程序为 \(z_x,z_m\)，部署可观察信息为：

\[
O=(x_{\text{text}},m_{\text{text}},\text{tool schema},\text{policy/version provenance},\text{probe results}).
\]

Benchmark 诊断量保留：

\[
P^*=1[z_x\equiv z_m].
\]

部署侧不应假装直接观测它，而应定义与 O 一致的程序集合：

\[
\Gamma_x(O),\quad \Gamma_m(O),
\]

以及识别集合：

\[
\mathcal I_P(O)=
\{1[z_x\equiv z_m]:
z_x\in\Gamma_x(O),z_m\in\Gamma_m(O)\}.
\]

它只有三种结果：

- \(\{1\}\)：certified match；
- \(\{0\}\)：certified conflict；
- \(\{0,1\}\)：unresolved，必须弃权或获取新信息。

若输出概率，应叫：

\[
\eta_P(O;\Pi)=\Pr_\Pi(P^*=1\mid O),
\]

其中 \(\Pi\) 是明确的部署分布。它不是 P 本身；near-miss mechanism mix 一变，概率就会变。

### 1.2 外部效度担忧：成立，但“真实部署零迁移”尚未被证明

担忧有直接证据：

- policy/comparator 在文本中近乎明写；[README.md](/work1/zixuan/projects/agent_memory/pilot/peval/README.md:123)
- family-CV 0.935 到 LOAO 0.590；
- 论文自身承认 trap-plane 文本可读、family-holdout AUC 达 0.996；[discussion.tex](/work1/zixuan/projects/agent_memory/iclr2027/sections/discussion.tex:18)
- ALFWorld 的 near-miss harm 取决于 trap construction；
- Part V 外部线因 pool 天花板 `NOT_ESTIMATED`，没有补上该缺口。[RESEARCH_LEDGER.md](/work1/zixuan/projects/agent_memory/RESEARCH_LEDGER.md:172)

但“真实任务语言都是隐式的”“必然零迁移”太强。真实系统有时能提供 tool schema、policy document、workflow version、typed API 和审计日志。正确结论是：

> CausalMemBench 上的 text-only P̂ 是 explicit-policy、单 generator 条件下的 upper-bound evaluation；不构成 implicit-task deployment evidence。

因此 A 即便成功，也必须过 renderer-disjoint、机制留出及真实任务三层门，否则只能留 appendix。

---

## 2. A–E 排序、组合及 kill condition

### 战略排序

1. **D + E：bounded verification，而不是 one-step dry-run**
2. **B + E：因果 utility 控制面**
3. **A + E：benchmark 静态解析基线**
4. **C：并入 B，不独立立项**
5. **E：不是单独路线，而是所有不完美判定器的强制外壳**

真正漏掉、且在“如何得到 P”上优于 A–E 的是下面的 **F：改变 memory interface，让信息随 memory 一起产生**。

| 路线 | 裁决 | Kill condition |
|---|---|---|
| A：SFT φ+d | **GO，benchmark-only** | 最终 macro-LOAO S=1 AUC 必须从 v1 的 **0.6472 提至 ≥0.7472**，且 cluster-bootstrap ΔAUC LB>0；最差 archetype ≥0.60；A00/A01 接受≤0.10、A10/A11 保留≥0.50，整体和逐族全过。抽取还须满足既定 parse/evidence≥0.99、hard-veto precision LB≥0.95、关键召回≥0.90、双侧 branch/effect coverage≥0.80。任一失败即停止，不做 SFT judge 补救。只在 640 上成功而 leave-renderer-out/第五机制失败，则 appendix。 |
| B：utility U | **GO，部署主线** | 无合法 randomized canary 或无法记录 propensity，直接 kill；不能用历史 retrieved-success 替代 uplift。主结果须在完全 holdout candidate generation 上，效用 superiority LB>0，同时 harm 非劣 U95<+5pp，并直接对比 A-MAC、RSCB-MC、Decision-Aware Memory Cards。若只能在 CausalMemBench oracle labels 上成立，kill 主文 claim。 |
| C：harmful-flip 预测 | **NO_GO standalone** | Harmful flip 是联合反事实 \(Y_m=0,Y_0=1\)；普通单臂日志不可点识别。除非有同 snapshot 双执行/emulator 或随机化设计，否则不得训练该标签。即使可得，也必须证明比直接 U/H 风险估计更好；7B A01 平均 **+3.1pp** 已说明 P=0 不等于负 utility。[README.md](/work1/zixuan/projects/agent_memory/pilot/peval/README.md:135) |
| D：执行式验证 | **GO with major amendment** | “执行一步”立即 kill P claim：它只能检查 active prefix，无法排除后续 skip-archive、错误 branch 或未触达状态。只有 bounded DSL 上的穷举/符号执行/SMT 完备证明，才能称得到 P；否则 estimand 必须叫 `verified-on-test-set conformance V_T`。若 probe 结果不是按构造满足 \(I(P;r\mid x,m)>0\)，或无可回滚副本、状态恢复、terminal predicate，则 kill。 |
| E：风险控制 | **Mandatory wrapper** | CRC/conformal 不创造信息，也不抗任意 mechanism shift。必须直接校准 A01-accept loss，并分别报告 A11 coverage；只给 marginal guarantee 不算逐机制保证。若 exchangeability 不成立或 coverage<0.50，kill deployment claim。 |

E 的样本量问题不能略过：若某机制上观察到 **0 次 A01 误收**，要让单侧 95% Clopper–Pearson UCB≤0.10，至少需要 **29 个独立簇**。四机制同时用 Bonferroni 保证则至少 **42 个独立簇/机制**。当前只有 10 families/archetype；即使零误收，单机制 UCB 仍约 **25.9%**，无法认证 10% 风险门。

### 漏掉的路线

**F. Contract-/test-carrying memory，最高优先级**

不要等 memory 变成自然语言后再猜 P。写入时同时保存：

- typed preconditions/postconditions；
- canonical role graph；
- tool/schema/policy version；
- environment snapshot hash；
- branch-covering unit tests或反例 witness；
- source trajectory provenance。

在有限 DSL 中，P 可变为 canonical equivalence 或 symbolic-refinement 检查。这不是“更强分类器”，而是**改变观测设计，使 P 可识别**。它直接规避 renderer 指纹和隐式 θ 问题，也是最像系统方法贡献的路线。

Kill：若真实 memory 生产路径不能可靠生成这些 contracts，或 contract 对真实行为的 conformance precision LB<0.95、coverage<0.50，则降为 domain-specific engineering。

**G. Active information acquisition**

遇到 \(\mathcal I_P(O)=\{0,1\}\) 时，不直接执行 memory，而是：

- 查询 policy table/tool schema；
- 请求用户澄清；
- 对 sandbox 生成能区分候选程序的最小 witness；
- 人工/强模型 escalation。

每个 query 必须事先证明可能缩小 \(\Gamma_x\) 或 \(\Gamma_m\)，满足信息增益条件；否则只是换一种 CoT。

**H. Active-path conformance**

完整 P 可能过严。更贴近 D 的 estimand 是：

\[
R_{\mathrm{conf}}(x,m)
=\Pr_{s\sim\nu_x}
[\text{memory action violates target spec at reachable state }s].
\]

它比“程序全局等价”弱，却比 outcome utility 更结构化；可通过 branch-targeted sandbox 测试估计。未覆盖状态上的结论必须保持 unresolved。

---

## 3. 成为第三类贡献的最小可信形态

**当前 A 单独成功仍不是第三贡献。** `PHI_D_EVALUATOR_PLAN.md` 自己把它定位为“工程工具，不是新论文贡献”；论文也已因未打赢 admission 近邻而移除 TRU-Mem。[boundaries.tex](/work1/zixuan/projects/agent_memory/iclr2027/sections/boundaries.tex:24)

升主文至少需要以下完整包：

1. **方法 delta**：`partial identification + contract/test acquisition + selective bounded checker`，不能只是 SFT parser 或 CRC 套壳。
2. **无 oracle 运行**：sealed P 只能最终评分，不能参与 threshold、规则、checkpoint 或 candidate generation。
3. **迁移证据**：
   - frozen 后第五种 mutation；
   - leave-renderer-out；
   - 至少一个独立的隐式任务环境；
   - authentic model-produced memories，而非 oracle reconstruction。
4. **直接 baseline**：A-MAC、RSCB-MC、Decision-Aware Memory Cards，加 always/never/sim/P̂。
5. **冻结主门**：
   - A01 accept U95≤0.10；
   - A11 retain L95≥0.50；
   - end-to-end utility 对最佳 baseline 的差值 L95>0；
   - harmful-intervention 非劣 U95<+5pp；
   - 每个环境、机制分别报告，不允许 pooled rescue。
6. **功效**：按 family/context cluster 预先计算。作为量级参考，检测二项风险从 10% 到15%的 5pp 差异，在简单 IID、α=.05、80% power 下约需 **680/arm**；实际还要按 cluster design effect 膨胀。

若只能做到：

- 同 generator 4,000 条 SFT；
- locked 640 上高 AUC；
- 第五种仍是同 renderer 的显式 comparator flip；
- 没有 published admission baseline 和真实 outcome；

则定位应是：**appendix engineering artifact + negative diagnostic**，不能列 Contribution 3。

另一条可发表但不同的路线，是构造真正的 observation-collision benchmark，加形式化不可识别下界，再展示 F/D 如何通过增加信息解除 ambiguity。但这属于 identification/interface 贡献，不能伪装成“打赢 admission baseline”的方法结果。

---

## 4. 简报中的错误与框定偏差

1. **29.5% 偷换 estimand**：它是 numeric θ symbolic rate；θ 又明确不属于 P equivalence class。
2. **“同一 640 标注集的所有方法”不完全准确**：φ 忠实度审计的单位是 532 个唯一单侧文本，SFT0 是 20-pair mint feasibility，不是 640-pair P estimator。
3. **“7B A10 100% 判错”缺样本量限定**：早期 CoT 是 16 对，其中 A10 仅 8 对；不能写成全 640 上 100%。
4. **“P̂ v1 被证明只是指纹”略强**：LOAO 崩溃和显式手工特征强烈支持 fingerprint diagnosis，但严格说证明的是“未迁移到未见 flip mechanism”，不是排除了所有程序信号。
5. **“真实部署任务都是隐式语言”过强**：外部效度风险成立，但结构化工具契约、policy documents 和 typed workflows 是真实可用的信息源。
6. **“D 天然规避不可识别”不成立**：只有 P-informative、覆盖分歧 branch 的 probe 才增加信息；单步 dry-run 常常什么也没识别。
7. **“C 可能比 P 更容易”缺依据**：harmful flip 是模型、版本、上下文和随机种子相关的联合反事实，标签获取通常比静态 P 更难。
8. **“E 给分布无关的逐族保证”不成立**：常规 risk control 多为校准分布上的 marginal guarantee；新 near-miss mechanism、family conditioning 和多组保证需要额外假设与样本。
9. **“全部发现都被部署 P 卡死”过度框定**：P×S 机制分解和逐候选 admission 确实被卡；但 coverage/H3、保留 decision+finish、压缩策略均不要求在线知道 P。论文已直接部署过这类结论，只是外部效度受 provenance 限制。[deployment.tex](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:4)
10. **Part V 不是 D 的负结果**：Part V 因候选池结构性天花板而 `NOT_ESTIMATED`，0 rollout、0 outcome 检视；它警告可行性，但没有证伪 runtime checking。

**最终投资建议：**立即允许 A 完成一次冻结的 SFT 学习曲线，但禁止据此宣称解决部署 P；同步把下一轮方案中心改成 **F（写入时生成 contract/test）→ D（有证书的 bounded check）→ E（弃权/升级）→ B（随机 canary 学 U）**。这才是既回答“如何得到 P”，又不把部署安全绑死在 P 上的路线。