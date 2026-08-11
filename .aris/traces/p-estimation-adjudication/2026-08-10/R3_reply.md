总裁决：

- **禁止把 generator 的 \(z\)、oracle plan 或由其渲染的 procedural card 记作 X。**
- 在本 benchmark 现有资产中，合法 X 只能来自真实执行，但“trace→IR”仍不等于“当时执行的程序”；它首先是一个**与轨迹相容的程序版本空间**。
- **X 必须拆成 X1/X2。现有数据只够做 X1 诊断，不够形成合格 X2，因此 X 应从当前 confirmatory interface curve 删除。**
- 资源上裁决为 **(c)，但默认出口是 (b)**；P0–P2 可以否决延期投稿，却不足以授权把新线塞进当前论文。
- 下周唯一值得跑的决定性切片是：**blind lawful-interface ceiling census**。它失败就终止“用现有 benchmark/资产把 interface curve 做成当前论文第三贡献”的路线，不准转向 SFT/GPU 加码。

## 1. X 的合法来源

### 1.1 X 不必普遍等于 trace→IR，但本 benchmark 中必须如此

最强、最干净的 X 来源其实是：

> 执行前已存在、被 hash、并实际驱动工具调用的 workflow AST / controller bytecode / typed plan。

它在因果上位于执行上游，能满足“这确实是当时执行的程序”。但当前 harness 是模型逐步输出调用，仓库里没有这种上游程序件；现有 procedural card 又直接来自 sealed program roles，[MAPPING.md](/work1/zixuan/projects/agent_memory/pilot/systems/MAPPING.md:15)，不能充当 X。

因此对当前 benchmark：

- generator \(z\)：**非法，oracle laundering**。
- `oracle_trajectory()`：**非法**；它直接从 archetype、`program_params` 和 `oracle_plan` 重建，[build_raw_cards.py](/work1/zixuan/projects/agent_memory/pilot/systems/build_raw_cards.py:156)。
- 真实 agent trajectory：**可作为输入证据**；harness 确实记录了实际调用和结果，[harness.py](/work1/zixuan/projects/agent_memory/pilot/harness.py:280)。
- 但由 trajectory 事后推得的 IR 只能叫 **trace-consistent IR**，不能未经证明称“实际执行程序”。

正确形式是：

\[
\Gamma_k=\{\sigma(z):z\in\mathcal H_{\mathrm{DSL}},
\ z\text{ 与 }k\text{ 条真实轨迹、schema、provenance 一致}\}.
\]

只有当 \(|\Gamma_k|=1\) 时，才可报告 certified signature；否则必须 abstain。

### 1.2 “机械泛化”的合法边界

结构输出中的每一个签名位都必须带可机器验证的证书：

- 参数化：该槽在不同实例中实际变化，或执行前 schema 已声明其为 typed placeholder。
- 数据依赖：有明确的 producer→consumer 数据流、schema precondition，或顺序干预证据。
- 分支：两个分支均被实际覆盖；未覆盖分支记 UNKNOWN。
- 缺失步骤：单条轨迹未出现只能记 UNKNOWN，不能推出 ABSENT。
- 独立操作：仅观察到固定顺序，不能推出偏序关系；必须看到反序执行成功或进行调度干预。

LLM 边界裁决：

- 可以做不进入 canonical hash 的命名、自然语言注释和角色显示名。
- 可以提出结构候选，但候选只有通过冻结的确定性 verifier 后才能进入 IR。
- 不得决定 polarity、方向、写目标角色、required/optional、branch、dependency edge。
- “temperature=0”不等于机械合法；关键是语义位是否有独立、确定性的证明检查。

同时必须记录 `trace_hash + initial_state_hash + tool/schema/policy version + generalizer_hash`。没有这些 provenance，X 不合格。

### 1.3 必须拆成 X1 / X2

| 点 | 定义 | 可做的声明 |
|---|---|---|
| X1 | 单条真实轨迹，\(k=1\) | 排除与已观察动作冲突的程序；通常不能认证参数、未走分支或偏序 |
| X2 | 多个不同实例的真实轨迹，加必要干预 | 若版本空间成为单点，可认证 bounded-DSL signature |

X2 不以固定 \(k\) 自动成立，而以覆盖证书成立。对当前四类 DSL，冻结如下最低门：

- 进入 X2 评估：\(k\ge6\) 个**不同初始状态/绑定的实例**。
- 每个拟参数化角色至少出现 3 个不同绑定。
- 每个二值 guard 两侧至少各 2 次。
- 每个门控元素至少出现一次 eligible、一次 ineligible。
- 方向角色至少覆盖 3 个非对称绑定/状态。
- 每对可能独立的操作必须观察两种顺序，或有 fault/schedule intervention；否则 dependency 保持 UNKNOWN。
- 预注册预算点 \(k\in\{1,2,4,6,8,12\}\)；到 \(k=12\) 仍非单点就 abstain，不再追加执行。

同一初始任务上的不同 decode seed、retry 不算不同实例。仓库明确说明四张卡共享同一 source task，只是使用不同 rollout seed，[build_raw_cards.py](/work1/zixuan/projects/agent_memory/pilot/systems/build_raw_cards.py:19)。

### 1.4 对现有数据的直接裁决

现有 640 条来源中：

- 188/640 是 oracle reconstruction，必须从 X1/X2 排除，[deployment.tex](/work1/zixuan/projects/agent_memory/iclr2027/sections/deployment.tex:11)。
- 剩余 452 条虽是真实 rollout，但大量只是同一具体 source task 的重复采样，不构成多实例泛化。
- source-task join 本身依赖 sealed family/cell mapping，[build_raw_cards.py](/work1/zixuan/projects/agent_memory/pilot/systems/build_raw_cards.py:10)，泛化器不得读取该 mapping。

因此：

> **当前 confirmatory curve 删除 X。X1 可保留为 diagnostic“observed-trace constraint”，不得命名为 canonical executable artifact；X2 等未来前瞻性写入采集。**

W 也不能自动保留。若 witness 是从 \(z\) 生成，同样属于 oracle laundering；只有写入时生成、外部作者提供，或由冻结 mutation generator 从合法执行件生成并经环境验证的 W 才可进入曲线。否则当前曲线只能是 T / T+S / T+S+V。

## 2. 当前论文的资源裁决

选择 **(c)，五个工作日封顶；其默认出口是 (b)**。选项 (a) 当前为 NO_GO。

原因是：P0–P2 是识别性和合法来源审计，最多证明“值得继续”，不能产生 Gate 0 所缺的已发表 baseline 方法胜绩。因此它可以杀死 (a)，不能单独授权 (a)。

具体分流：

1. 若冻结 canonicalizer 与 sealed P 在 640 对上出现任何不一致：

   - 门：`mismatch = 0/640`。
   - 若 `>0`：暂停当前投稿，修 benchmark/P 定义或论文事实。这是 validity repair，不是增加新贡献。

2. 若 canonical audit 通过，但下述一周切片失败：

   - 当前论文按 (b) 投稿。
   - 明确把部署态 P 获取写成 open problem。
   - interface line 不进入 main section；现有资产上停止 SFT/GPU。

3. 若一周切片通过：

   - 允许投资 P3–P7，默认作为论文 #2。
   - 仍不推迟当前稿。

4. 只有完整 confirmatory 结果在投稿锁定前已经完成，才可重开 (a)。最低门为：

   - lawful interface 的 \(\Delta\mathrm{Cert}\ge0.20\)；
   - 最终 \(\mathrm{Cert}\ge0.80\)；
   - certified singleton 在有限 DSL 上 0 个逻辑错误；
   - 若是经验 certifier，单侧 95% precision LCB ≥0.95；
   - lawful source availability ≥0.80，整体及逐机制；
   - 0 条 oracle-derived X/W；
   - 独立 renderer/challenger collision set；
   - confirmatory 规模仍按 R2：100 families/机制、800 primary pairs；A01 错误≤2，A11 正确≥63。

也就是说，**P0–P2 通过不等于延期投稿；只有完整结果通过才可能改变这一点。**

## 3. 下周唯一的决定性切片

运行一个完整的：

> **Blind Lawful-Interface Ceiling Census（BLICC）**

它不是训练模型，而是在 532 个单侧文本、640 个 pair 上计算冻结接口下的版本空间信息上限。

### 二值 PASS 门

必须同时满足：

1. `Canon(signature)` 与 benchmark P：**640/640 一致**。
2. T-only 存在实质缺口：  
   \(\mathrm{Cert}_T\le0.80\)。
3. 至少一个合法非文本接口 \(A\) 达到：  
   \(\mathrm{Cert}_A\ge0.80\)。
4. 信息增量：  
   \(\mathrm{Cert}_A-\mathrm{Cert}_T\ge0.20\)，整体及四机制分别成立。
5. 所有 singleton 均由冻结逻辑蕴含：有限 benchmark 上 **0 个错误**。
6. 接口来源可用率：整体及逐机制均 ≥0.80。
7. X/W 若进入计算，必须满足上述 provenance 门；否则自动从 \(A\) 删除。

任一失败即记 `NO_GO_CURRENT_INTERFACE_CONTRIBUTION`：

- 杀死“把 interface curve 做成当前论文第三贡献”；
- 杀死“利用现有 trace 构造 X2”；
- 不得用 SFT/GPU补救；
- 论文 #2 只有在重新做前瞻性 write-path instrumentation 后才能复活。

PASS 只授权进入 P3–P7，不自动授权选项 (a)。

### 五天执行划分

- Day 1：冻结签名 atom ontology、合法接口字段和版本空间规则。
- Day 2：完成 532 文本的 signature-explicit/obscured census。
- Day 3：计算 640 pair 的 T 与合法接口 information ceiling。
- Day 4：完成 trace provenance、distinct-instance、X1/X2/W 来源审计。
- Day 5：一次性 sealed scoring，输出 PASS/FAIL；不做逐例反馈迭代。

### 开跑前必须 hash

- 532/640 个 opaque ID 及公开文本字节。
- DSL signature 定义与 canonicalizer；签名仍以[program_dsl.py](/work1/zixuan/projects/agent_memory/pilot/program_dsl.py:10)中的步骤集、偏序、极性、写目标角色为准。
- T/S/V/X1/X2/W 各自字段 allowlist。
- set-valued inference、UNKNOWN/ABSENT 和 abstain 规则。
- trace authenticity、distinct-instance 和 skill-grouping 定义。
- oracle fallback 排除规则。
- 全部阈值、指标、表格空壳、停止规则。
- 代码 commit、依赖版本、输入 manifest 和 scorer hash。

### sealed 防火墙

开发和规则制定阶段不得读取：

- `P`, `S`, `cell`；
- `family_idx`, `archetype`, `near_miss/nm_kind`；
- generator `signature`, roles dict, `program_params`；
- `oracle_plan`, sealed terminal；
- A10/A00 partner、source family/kind 等映射。

独立 scorer 在全部 hash 后，只能：

- 读取 `P` 做最终 singleton 正确性；
- 读取机制标签做预先规定的聚合；
- 在 canonical integrity 子审计中读取 oracle signature；
- 返回固定聚合表与一个 PASS/FAIL。

在裁决锁定前，不得返回逐例错误、字段失败模式或允许改规则。

最后一句直判：**现有证据已经强烈预示 BLICC 会 FAIL——T 很可能过于显式，同时当前 X2 来源又不合法。这个失败不是坏结果；它会及时阻止把 generator oracle 包装成部署接口，并把当前论文安全地送入 (b)。**