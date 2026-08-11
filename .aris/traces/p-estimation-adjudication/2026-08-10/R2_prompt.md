# Round 2：接受更正 + 三个必须由你裁决的新问题

## 0. 我接受的更正（不再辩护）

第 4 节 1/2/3/4/5/9/10 全部接受。特别是：

- **29.5% 偷换 estimand 成立**。我已复核 `program_dsl.py:10-16`：等价类 = 步骤集 + 偏序 + **算子极性** +
  写目标角色，"Concrete thresholds / entity values are instance parameters, not part of the
  equivalence class"。θ 不可判定与 P 不可识别无关。你的 exact-text collision 检查（0 组同 O 反 P）
  我也认可为当前唯一有效的下界证据。
- "16 对里 A10 仅 8 对"、"532 唯一单侧文本 ≠ 640 对"、"P̂ v1 只证明未迁移到未见机制而非排除所有程序信号"——
  全部接受，我会照此改写台账措辞。
- "全部发现都被部署 P 卡死"确属过度框定：coverage/decision+finish 保留/压缩策略这三条部署结论不需要在线知道 P。

## 1. 但我要提一个把你两个结论**合并**的观察，请裁决它是否成立

你说（a）当前经验 Bayes 下界为 0，故不存在不可识别下界；（b）外部效度担忧成立，本 benchmark 是
explicit-policy 上界评测。

我认为这**是同一个事实的两面**，而且可以被精确化：

等价类里唯一"文本可变"的判别位是**算子极性 / 方向 / 门控子集 / 必需步骤是否缺失**。我已核实四种 near-miss
就是这四个位的参数级翻转（`generate_families.py:336` `"<=" if near_miss else prm["op"]`、
`:587` `("west","east") if near_miss`、`:828/:862` 门控子集、P4 跳过 archive）。而 `:383` `:506`
把翻转结果**逐字写进文本**（"at or below" vs "above"）。

于是：**下界为 0 恰恰是因为签名相关位在本 benchmark 里是逐字明写的**。这不是"P 可识别"的好消息，
而是"我们的 identifiability 结论只在 signature-verbatim 条件下成立"的坏消息。

**可执行的精确化（我打算做，请你裁决是否值得）**：把 157/532 符号化文本按"被遮蔽的是 θ（实例参数）"
还是"被遮蔽的是签名相关位（极性/方向/子集/缺失步骤）"重新分类。若后者 ≈ 0，则本 benchmark 的
text-only P 识别是**构造性 trivial**，必须在论文里明说；且这直接给出制造真正 collision set 的配方
（把极性移出文本、放进 policy 表 / tool schema / 版本 provenance），即你说的"同 O 反 P"数据集。
这是 CPU-only、无需 rollout 的一天工作量。

**请裁决**：(i) 这个合并论断成立吗？(ii) signature-obscured collision set 是否应作为下一步的
**第一个交付物**（它同时是不可识别下界的证据、是 F/D 的试验台、也是审稿人最可能要求的东西）？

## 2. 关于 D：我核到的构造事实，可能把它从 V_T 升级为可证完备

你给 D 的修正是："只有 bounded DSL 上的穷举/符号执行/SMT 完备证明才能称得到 P，否则只能叫
verified-on-test-set conformance V_T"。我核了代码，认为在**本 DSL 内**完备性可能是可构造达成的：

- **四种 z′ 都是完全可执行、且到达自己合法终态的程序**（`README.md:88` 设计说明 + 上述代码）。
  所以"跑一步看崩不崩"零判别力——你的"单步 dry-run 常常什么也没识别"完全正确。
- 但**判别性探针状态按构造必然存在**：θ 两侧各一行（抓极性翻转）、源/目标两侧非对称库存（抓方向反转）、
  混合完成度的子集（抓门控子集错误）、archive 表非空性（抓 skip-archive）。
- 基础设施**已经存在且是 CPU-only**：`env_relationalops.py:77` 环境是 `sqlite3.connect(":memory:")`
  由 tables dict 的 `deepcopy` 构建、有 `snapshot()`；`program_dsl.py:306`
  `run_oracle_plan(env, program, plan)` 可对活环境执行程序并断言终态；
  `topological_order_ok` 已实现偏序合规检查。**克隆 + 差分执行的成本近乎零，不需要 GPU，不需要新 rollout。**

**请裁决**：在本 DSL 的签名定义（步骤集 + 偏序 + 极性 + 写目标角色）下，是否存在一个**可证完备的有限探针
集**，使得"在该探针集上两程序的状态转移函数逐点相等 ⟺ 签名相等"？

- 若**是**：D 的 estimand 就不是 V_T 而是 certified P（在 DSL 内），请给出完备性证明义务清单
  （需要覆盖哪些状态维度、如何处理不可达状态、如何处理非确定性）。
- 若**否**：请给出反例结构，我按 V_T 措辞执行。

我意识到一个陷阱并主动登记：**要执行 memory 的程序，就要先把 memory 文本变回可执行程序——那又是抽取**。
所以 D 单独并不闭合；它只有和 F（写入时就保留可执行件）组合才闭合。这也是我认为你把 F 排第一是对的原因。

## 3. 关于 F：你自己登记过的 collision，这轮没有触发，请正面裁决

你在 2026-08-10 的 pivot 裁决里亲自把 **Skill-Pro (arXiv 2602.01869, ICML 2026 Spotlight)** 核验为
"**activation / execution / termination conditions**"，并据此冻结了措辞护栏（禁用 "procedural
signature" 等）。

而你本轮提出的 F = "写入时保存 typed preconditions/postconditions + canonical role graph +
tool/schema/policy version + branch-covering unit tests + provenance"。

**这在我看来与 Skill-Pro 的占位高度重叠**（前三项几乎就是它的 activation/execution/termination
conditions），加上 AWM / Memp / ExpeL 这一族"结构化写入"的既有空间。请正面裁决：

1. F 里**还剩下什么是没被占的**？我的候选答案是两项：
   (a) **witness/counterexample 而非 declarative condition**——不存 "条件"，存**能把该程序与其近错变体
       区分开的最小可执行测试**（差分测试而非契约声明）；
   (b) **用 sealed oracle 去测量每一种接口元素买到多少 P 可判定性**——这是**只有我们做得到**的实验
       （真实系统没有 P 真值），也是把整条线从"又一个 memory 格式"抬成识别性结果的唯一杠杆。
2. 若 (a)(b) 也被占，请直接说 F 降级为 domain engineering，我不做。

## 4. 我提议的 estimand 重定义（请裁决是否是这条线的正确交付物）

不做"更强的 P 分类器"，而做 **memory 接口的信息价值测量**：

对接口元素集合 \(A\)（文本 / +tool schema / +policy provenance / +执行轨迹 / +差分测试 witness），
用 sealed oracle 测量

\[
\mathrm{Cert}(A)=\Pr[\mathcal I_P(O_A)\ \text{是单点}],\qquad
\mathrm{Prec}(A)=\Pr[\text{单点判定正确}\mid \text{单点}]
\]

即**每加一件写入侧信息，certified 覆盖率涨多少、精度是否保持 ≥0.95**。输出是一条
"要在部署中获得 P，你必须在写入时保留什么"的**可操作曲线**，而不是一个 AUC 数字。

这直接回答用户的问题（"如何得到 P"→"文本上得不到；把这几件东西写进去就得到，代价是覆盖率 X"），
用的是我们唯一不可复制的资产（oracle），并且**天然把外部效度写进结论**（曲线的每一点都标注需要环境提供什么）。

**请裁决**：(i) 这是不是正确的交付物形态？(ii) 它属于 identification/interface 贡献（你 §3 末尾提到的
第二条路线），因此**不能**伪装成"打赢 admission baseline"——我接受这个定位，只要你确认它本身足以支撑
一篇独立论文或本文的主 section，而不是 appendix。

## 5. 功效：你给的 29/42 簇约束，我认为可以靠生成器解掉，请确认

你指出：零误收时单侧 95% CP UCB≤0.10 需 ≥29 独立簇，四机制 Bonferroni 需 ≥42/机制；当前
10 families/archetype，UCB≈25.9%，认证不了 10% 风险门。

但**生成器可以无限造族**（SFT 计划本来就要 ≥4,000 文本 / ≥200 族，CPU-only）。所以这不是天花板，
是采样预算问题。请确认：

- 需要多少 families/机制、多少 (target, memory) 对，才能同时认证 A01 accept UCB≤0.10 与
  A11 retain LCB≥0.50，**逐机制**且经多重性校正？请给具体数字与 cluster 单位定义
  （family 是簇？还是 archetype 是簇？——这决定了独立性假设）。
- 新造的族是否会引入"同一 generator 指纹"问题，使得认证只是自我一致？如何设计才能避免
  （renderer-disjoint？第五、第六机制？外部构造者？）。

## 6. 我要的最终输出

请给一个**最小决定性实验序列**，满足：

- CPU 优先，GPU 只在不可替代处使用（本项目 10×A5000 现被别的项目占着，且有"不得为把效应推过显著性
  阈值而追加算力"的既定禁令）；
- 每一步有前置门与 kill condition，失败即停不加码；
- 明确哪一步产出的是"可写进论文的结果"，哪一步只是工程件；
- 明确哪些步骤**必须**在 sealed oracle 之外冻结（防止 oracle 参与阈值/规则选择）。

约束同上：只读检视，不修改仓库任何文件。给数字与判据，不要方法学套话。
