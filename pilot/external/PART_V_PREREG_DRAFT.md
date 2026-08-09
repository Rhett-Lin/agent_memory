# Part V(草案)— ALFWorld 主动型 near-miss + structured admission gate 外部验证

> **状态:DRAFT,未冻结、未执行。** 冻结流程(治理规则):本草案 → 自分析(已完成,见文末)→ GPT-5.6(Codex MCP)裁决 → 修正后落入 `GATE_PROTOCOL.md` Part V → 才开始实现。裁决前不得启动任何 GPU 作业。
> 目的:验证论文发现并不仅仅在合成 SQLite 环境成立——「程序不兼容的 memory 会主动伤害 agent」与「基于程序兼容结构的 admission gate 能拦住它而表面相似度 gate 不能」这两条,能否在一个非合成环境(ALFWorld)中以真实 rollout 复现并转化为系统收益。这是"发现服务于 agent system"的服务验证,不是新贡献声明;文献空间拥挤不构成阻碍,不做 novelty 声明。

## 1. 与上次外部检查的关系(为什么这次不同)

上次(`pilot/external/EXTERNAL_VALIDATION.md`,144 rollouts):R>S>N 方向弱复现,但 **near-miss 危害未复现(X≥N)**——根因已识别:X 是 **recoverable omission**(关键步骤缺失的成功轨迹),目标 goal 文本始终可见,7B 可自行补回。本 Part V 的 X 改为 **active flip**(成功轨迹,但关键程序元素与目标主动矛盾);新增 admission gate 对照。上次已登记的信条保留:「方向而非量值才是可辩护声明」。

## 2. 假设(冻结后不得改)

- **H-harm(前提性假设)**: 主动型 near-miss memory(X)显著降低成功率相对 N。
- **H-serve(服务假设)**: 结构化 admission gate(G-struct,只用 instruction+card 文本、无训练、无标签)的期望成功率显著优于 surface gate(G-S),且不劣于 oracle gate 5pp 以内。

两条必须同时成立才 GO。若 H-harm 不成立:整个前提再次在 ALFWorld 失败 → 记 NO_GO,按治理规则自分析 + GPT-5.6 讨论后才能在"near-miss 在 ALFWorld 是否可伤害"上做任何再设计。**不 grafting 新翻转类型直到生效(power chasing 禁令适用)。**

## 3. 构造(冻结)

### 3.1 家族与翻转机制(每族一种,共 3+2 族)

| family | R(P=1 参照) | X-active(P=0, 主动矛盾) | 关键程序元素(设施别) |
|---|---|---|---|
| pick_clean_then_place | 同对象类、同 clean prep、异 room/trial/recep 实例的成功轨迹 | **prep-verb 翻转**:同对象类、把 clean 换成 heat/cool 的成功轨迹(同 recep 类) | prep verb |
| pick_heat_then_place | 同上(heat) | **prep-verb 翻转**:heat→clean,同对象类、同 recep 类 | prep verb |
| pick_two_obj_and_place | 同对象类×2、同 recep 类的成功轨迹 | **object-class 翻转**:同 recep 类、异对象类×2 的成功轨迹 | object class |
| (可选)pick_cool_then_place | 同 clean 行 | prep-verb 翻转 cool→heat | prep verb |
| (可选)look_at_obj_in_light | 同对象类的成功轨迹 | object-class 翻转 | object class |

可选项仅在实现期若前 3 族顺利才追加;不追加是合法结局。**X 构造铁律:X 源 episode 必须在其自身 goal 下 env-verified `won`**(与 R 同标准);矛盾只存在于 X 的 goal 与**目标**任务的 goal 之间。

### 3.2 卡片

- 形式:transcript card(沿用上次 card builder:从 won episode 的 action/observation 序列截取),200–300 Qwen-2.5 tokens,R/X 配对 |Δtokens| ≤ 30,逐对记录。
- **表面匹配断言(构造审计)**:对每对 (X, target) 与 (R, target),TF 余弦与 bge 余弦双指标须满足 sim(X) ≥ sim(R) − 0.05;不满足则换源实例重造,并把重造次数如实登记。该断言是"X 与 R 同为表面匹配、只有程序兼容性不同"成立的证据——**S-gate 因此而注定拦不住 X 的论断才合法**。
- 隔离 grep:卡片不得含 family/cell/R/X 等标签(token 级零命中)。

### 3.3 Provenance(H-DC 教训,预披露)

- 首选:**模型自 harvest**——目标族兄弟 instance 的无记忆 rollout(k≤4 次尝试/instance,temperature 0.7,先跑先存)中取 won 轨迹;
- 兜底:**expert gold 轨迹**(AlfredExpert,与上次同一 stack),逐卡登记 `provenance ∈ {model_harvest, expert_gold}`。
- gold 占比 ≤15% 时只做主分析;>15% 时必报 provenance-分层 secondary(主口径仍 pooled,如实降级声明)。**禁止静默 fallback。** harvest 尝试全部计入 rollout 账本。

## 4. 网格与算力(冻结)

- 主网格:3 族 × 4 siblings × {N, R, X} × 4 seeds = **144 rollouts**;可选项若追加 +96。**封顶 240。**
- harvest 尝试封顶上节。环境/harness 沿用上次:alfworld 0.4.2 + textworld per-episode envs + Alfred wrappers;Qwen2.5-7B vllm 0.6.6.post1, fp16, temp 0.7, top_p 0.9, max 30 steps,admissible-command 接口(解析失败→`look`),per-(game,seed) decode seed。
- 预算:grid ≤ 4 A5000·h,harvest ≤ 4 A5000·h,硬顶 8;超时减半 seeds(4→2)并如实登记降级。
- 输出:`/work1/zixuan/outputs/agent_memory/external_gate/`(cards.json、manifest、rollouts.jsonl、gate 评分、分析 JSON);日志 `/work1/zixuan/logs/agent_memory/`。

## 5. Admission gates(冻结定义)

所有 gate 输入仅限 (goal text, card text) 与由二者可算出的相似度;**禁止**任何 sealed/构造标签。离线评估:g取值为 1→取该 (family,sibling,seed) 的 R/X 结局;0→取 N 结局。

- **G-struct(主)**:确定性规则,只解析两文本的关键程序元素(§3.1 设施别列):prep-verb 族检查 card 的 prep verb 与 goal 的 prep verb 是否同类(clean/heat/cool 三类词典在实现前写出并附于本文件附录);object 族检查 goal 对象类集合 ⊆ card 对象类集合。match→admit,contradict→abstain,无法解析→abstain(保守偏置,登记解析失败率)。
- **G-S(主对照)**:bge-small 余弦 ≥ τ_s;τ_s 冻结为 **R 卡对目标 sim 分布的中位数**(实现首日由 cards.json 一次性算出并登记,不调参)。
- **G-learn(secondary,允许失败)**:pilot/peval 的 TF-IDF+LR P̂,用既有 640 pilot 对 + 本次构造标签对训练,族留出 CV;只报 AUC,不进 GO 判据(循环性如实披露:标签来自构造规则)。
- **oracle gate(上界参照)**:admit R,abstain X。

## 6. Estimands 与多重性(冻结)

推断:family-cluster bootstrap(2,000 reps, seed=20260809);成功率 CI 用 Wilson;配对翻转按 (family,sibling,seed) 三元组。primary family **Holm m=3**:

1. **E-harm** = succ(N) − succ(X),单侧正;GO 档:Holm p<.05 且点估计 ≥ +5pp。稳健佐证(secondary):配对 sign test,N赢X输 vs X赢N输。
2. **E-serve** = succ(G-struct) − succ(G-S),单侧正,Holm p<.05。
3. **E-oracle** = succ(G-struct) − succ(oracle),非劣性:bootstrap 单侧 95% CI 下界 > −5pp(禁止用 n.s. 冒充非劣,E3a 同 Part IV-A A5 口径)。

Secondary(不经 Holm,只报 CI):各族分率(上次教训:heat 族曾整体无效应)、G-learn AUC、HFR 类比量、step 数、解析失败率、provenance 分层(若触发)。

## 7. GO / NO_GO(冻结)

- **GO**:E-harm Holm SIG(≥+5pp) ∧ E-serve Holm SIG+ ∧ E-oracle 非劣成立。
- **NO_GO(premise fail)**:E-harm 不显著或 <+5pp → 记 NO_GO,冻结不再改;处置走治理规则。
- **PARTIAL(service fail)**:E-harm 成立但 E-serve 不成立或 E-oracle 非劣被违反 → 如实记「危害复现、gate 未显服务价值」;同样走治理规则后才允许任何后续动作。

## 8. 审计纪律(冻结)

- A6 同款时间混杂断言:grid 全部 rollout 的 config_hash/env_versions/git_commit 扫描入档;A6_CHECKS 风格 JSON 落盘。
- env 确定性:每源 episode 二次 env-verified;vllm batch 调度不确定性沿用上次披露口径。
- 任务成功率合理性:N 臂成功率须落在已有 ALFWorld 7B 报告区间(10–40%);越界则查 harness 故障而非解释效应。
- 全部分析脚本 CPU;rollout 分析前不做任何 outcome 检视(分析代码先 commit)。
- 偏差日志照 EXTERNAL_VALIDATION.md 规格另存 `EXTERNAL_GATE_DEVIATIONS.md`。

## 9. 不做的事(纪律)

不引入新模型族;不做"真实机器人/over-the-web"外推声明;不把 G-struct 包装为方法贡献;不在 GO 前写论文段落;不为凑显著加族加 seed(减 seed 的降级倒允许,见 §4)。

## 10. 自分析记录(冻结前已完成,供 GPT-5.6 裁决参考)

1. **为什么 X 不能用 receptacle 翻转**:上次 R 构造本身允许源/目标 recep 不同(依然 helpful),若 X 的错误点也是 recep,G-struct 无法用 recep 作判据——区别特征只能是 prep verb 与 object class,故翻转机制定为这两类。
2. **为什么 G-struct 作 GO 判据而不用学习型 P̂**:ALFWorld 构造标签对太少(≤40),学习型 gate 不可能有诚实的族留出评估;其风险与 LOAO 负结果一致。G-struct 零训练、零循环;G-learn 只做 secondary 探索。
3. **为什么接受"两族内各只有一种翻转"的窄设计**:本实验的 claim 是「**存在**主动型 near-miss 且结构 gate 有用」的存在性服务验证,不是翻转机制普查;窄设计换判据干净。
4. **预期反驳与答辩**:「G-struct 是人写规则,不公平?」——它被显式定位为 upper-anchor/P 可推断性的构造证人,G-learn/真实学习版的失败如实上报;「X 的成功率仍≥N 怎么办?」——即 NO_GO,与上次负结果合并为「ALFWorld 下 near-miss 伤害不出现」的稳定结论,同样是资产。
