# Part V(v5 最终,冻结版)— ALFWorld 主动 near-miss + structured admission gate

> **状态:FINAL v5,四轮裁决(2026-08-09,thread 019fe550)全部修正案落地;经 GO to freeze 确认后本文原文移入 `GATE_PROTOCOL.md` Part V。v1–v4 留存备查,不再有效。**
> 目的:存在性服务验证——「预注册的主动程序矛盾 memory 会伤害 agent」(E-harm,唯一功效保障端点)与「冻结的 structured-oracle proxy gate 服务价值」(E-serve/E-oracle,条件性端点)在 ALFWorld 中以受控设计检验。gate 是工程件,不做 novelty 声明。

## 0. v5 相对 v4 的四轮裁决修正对照

| # | 四轮裁决 | v5 落点 |
|---|---|---|
| 1 | prompt 包字节 hash 不符(尾部 LF) | `PART_V_PROMPTS.json` 已修正为无尾 LF,实测 = `46da398a…`(复算通过) |
| 2 | power 文件残留旧句(14–15 行矛盾) | 已删除并以更正句为权威;小效应出口改述为 INCONCLUSIVE |
| 3 | 源/RNG 规格仍有自由裁量缝 | §3.5 可执行算法块(池保留顺序、拒绝源永久不可用、双独立 RNG 流、MD5 字面规则) |
| 4 | 终态不穷尽 | §10 增加 INCONCLUSIVE;NOT_ESTIMATED 逐端点限定;审计失败不抹杀有效 E-harm(→PARTIAL) |

## 1. 假设(冻结后不得改)

- **H-harm(前提,唯一功效保障端点)**:主动 near-miss(X)显著降低成功率相对 N。
- **H-serve(条件性端点)**:G-struct 的 policy value 显著优于 G-S,且对 oracle 非劣(−5pp)。
- G-struct = 手工 structured-oracle 代理(inference 无标签非 supervision-free);E-serve 在 G-struct≡oracle 且 G-S 双收时 = ½·E-harm,系统后果非独立证据。

## 2. 家族与翻转(冻结,仅两类,同一机制)

| family | R(P=1) | X-active(P=0) |
|---|---|---|
| pick_heat_then_place(train 459 局) | model-won **heat**-prep episode:同对象类、同 recep 类、异 room/trial/recep 实例 | model-won **cool**-prep episode:同对象类、同 recep 类(heating removes isCool) |
| pick_cool_then_place(train 533 局) | model-won cool-prep episode,同上 | model-won **heat**-prep episode,同对象类、同 recep 类(cooling removes isHot) |

claims 限于两类等权混合;X 源必须自身 goal 下 env-verified `won`。

## 3. 采样、cluster 与 harvest(全冻结)

- `target_cluster = 目标 game + 冻结 R/X 卡`;`rollout_unit = cluster × seed × cell`。
- 三方互斥:confirmatory/校准/headroom 的目标与源两两不相交;同一源 episode 不服务超过一个 cluster。
- 不设 missing 容忍:未完成 run 续跑补齐;完整 60+60 不可得 → NOT_ESTIMATED。

### 3.5 确定性与随机性算法块(冻结,逐字执行)

1. **canonical path**:相对 `$ALFWORLD_DATA` 的 POSIX relpath(去前导 ./,统一 `/`)。
2. **RNG 流(两条,互不混用)**:`rng_screen = numpy.random.Generator(numpy.random.PCG64(20260809))`(筛查/抽样/打散候选序);`rng_rollout = numpy.random.Generator(numpy.random.PCG64(20260810))`(主网格 (cluster,seed,cell) 顺序打散)。
3. **候选排序**:每池先按 sha256(canonical_path 的 UTF-8 字节)升序;`order = np.argsort(rng_screen.random(n), kind="stable")` 作用于该排序列表得筛查序(float tie 以 sha 序保序打破)。NumPy 版本钉死 = **1.26.4**(causalmemagent 环境实测)。
4. **池保留顺序(全局唯一,固定)**:confirmatory-heat(取满 60)→ confirmatory-cool(取满 60)→ 校准(**恰 20 heat + 20 cool**,按各自筛查序取首个合格剩余目标,配 model-harvest R 卡)→ headroom-A(12,heat/cool 各半)→ headroom-B(12,同上)。任何 game/源一经为某池保留(无论后续 harvest 成败),**永久移出**后续一切池与候选列表(含尝试失败的源)。
5. **目标筛查(每类型)**:按筛查序遍历 game;对其做 §3.4 harvest;成功(获唯一可用 R 与 X)→ 保留为 valid cluster;取满 60 即停;全部遍历完仍 <60 → NOT_ESTIMATED。
6. **MD5 字面规则**:`md5((canonical_path + "|" + decimal_integer).encode("utf-8")).digest()[:4]`,小端转 int,mod 2^31。

### 3.4 Harvest 规则(冻结)

- 每目标:先列表前 **8 个唯一 R 候选、再 8 个唯一 X 候选**(R 先 X 后);每候选 ≤4 次无记忆尝试,attempt decode seed = §3.5.6 规则,字符串为 `candidate_path + "|" + role + "|" + attempt_idx`(attempt_idx ∈ 1..4,十进制);取首个 env-verified `won`。
- 任一角色失败 → 该目标拒绝,按筛查序递补目标(总递补 ≤ 40,超出 → NOT_ESTIMATED);全部尝试计入账本;triad 的 R/X 必须同为 model_harvest。

## 4. 卡片构造与 τ_s / 哑点审计(全冻结)

- builder:`run_alfworld_check.py` 的 transcript-card 代码路径,**字节不动**,SHA-256 `96ef23ea8516fc95c11d34b7c639e7474ada4f1b9dfd0a153c036b964f11eec3`;卡片 token 计量 = 该 builder 现有行为(Qwen2.5-7B-Instruct tokenizer,rev `a09a35458c702b33eeacc393d103063234e8bc28`);200–300 tokens,R/X 配对 |Δ| ≤ 30。
- 存活断言(逐卡自动):含源 prep 动作行(prep verb + 对象类字面);不含目标 goal 文本;无 family/cell/R/X 标签 grep。
- **τ_s 校准(先于一切 rollout、无 outcome)**:40 个独立校准目标 × 其 R 卡;经验第 5 百分位(numpy.percentile,linear 插值)= 95% R-recall;bge = BAAI/bge-small-en-v1.5,rev `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`。
- **哑点断言**:confirmatory 卡片池 X-acc ≥ 90% 且 |X-acc − R-acc| ≤ 5pp;不达标对按 sha256 序逐对重建(源递补同 §3.4,每对 ≤3 次);仍有 → 哑点 claim NOT_ESTIMATED,service 端点整体 NOT_ESTIMATED(E-serve 仅描述,E-harm 不受影响,见 §10)。

## 5. G-struct 定义(全冻结)

- **goal parse**:`hot|heated|heat` → heat;`cool|cooled` → cool(goal 小写化;同含两词 → parse-fail)。
- **card parse**:源 prep 动作行同词典;appliance/object 归一(小写、去形容词 {clean,hot,heated,cool,cooled,cold,chilled,sliced}、单复数折叠);同含两 prep → parse-fail。
- **决策**:card_prep==goal_prep → admit;相反 → reject(contradiction);parse-fail → abstain(记 parse-failure,不计 contradiction)。
- **保真判据(rollout 前)**:每 (type×arm) parse coverage ≥95%;R admission ≥95%;X contradiction-rejection ≥95%(经解析矛盾而非 parse-fail)。允许 ≤5% 误差,E-oracle 保持随机项,留 Holm m=3。
- **G-S**:bge(goal,card) ≥ τ_s。**G-learn**:零样本 pilot P̂(冻结权重),只报 AUC,不进 GO。

## 6. Estimands 与推断(全冻结)

- 候选分布:每 (target,seed) R/X 等权 ½;V(g) = E_c[ g·succ_c + (1−g)·succ_N ]。类型等权 ½+½,类型内 target/seed 等权;配对 (target,seed)。
- **Holm m=3(单侧)**:① E-harm=succ(N)−succ(X),θ0=0;② E-serve=V(G-struct)−V(G-S),θ0=0;③ E-oracle-noninf,θ0=−0.05。
- **p 值(null-centered cluster bootstrap,冻结公式)**:cluster=target,stratified(60/60),B=20,000,seed 20260809;
  `p_raw = (1 + #{ (θ̂_b* − θ̂) ≥ (θ̂ − θ0) })/(B+1)`;
  Holm:p_raw 升序,第 k 个对 α/(m−k+1),tie 按 ①②③ 保序记录。描述性 CI:percentile(2.5/97.5)。
- **GO 判据**:三条 Holm p<.05 且 E-harm 观测点 ≥ +5pp(仅声称观测效应);**外加五前提**:§4 哑点断言、§5 parser 判据、§3 完整 60+60 model-only 网格、§7 headroom 通过、§4+附录 A hash 核验一致。
- 分析脚本 `pilot/external/analyze_gate.py` 于 outcome 检视前 commit(hash 入档),报告头重算 q/ICC/DE 与 PART_V_POWER.md 规划值并列。

## 7. Headroom(全部移出 confirmatory grid,全冻结)

- 两组 disjoint headroom 集,各 12 targets × 4 seeds(heat/cool 各半),永不进 confirmatory/校准/E 量。
- **操纵量(纯行为)**:P(目标对象被施加 X 的冲突 prep verb | X 臂) − P(同冲突 verb | N 臂) ≥ +10pp;无该动作计 0;不设步数窗。
- A(MEM_A)达标 → 主网格用 A;否则 B(MEM_B)于第二组上测;B 达标 → 主网格用 B + protocol 修正案登记;两组均败 → 全实验 NOT_ESTIMATED。不看成功率。

## 8. 执行顺序(冻结)

builder hash 核验 → prompt 包 hash 核验 → §3.5 池保留 → harvest → 卡片池 + 存活断言 → parser 判据 → τ_s 校准 → 哑点断言 → headroom A/(B) → 主网格(rng_rollout 打散,wave 化,wave/batch id 入 meta)→ analyze_gate.py。分析脚本 commit 前不检视任何成功率。

## 9. 运行时冻结

- 模型:Qwen2.5-7B-Instruct,rev `a09a35458c702b33eeacc393d103063234e8bc28`;环境:alfworld 0.4.2 / textworld 1.7.0 / jericho 3.3.1 / vllm 0.6.6.post1 / torch 2.5.1+cu124 / transformers 4.57.6;fp16,gpu_mem_util 0.85,max_model_len 4096。
- 解码:temp 0.7,top_p 0.9,**max_tokens=24**,≤30 steps;admissible-command 接口,`normalize_cmd`+`parse_command`(exact / difflib cutoff 0.65 fuzzy / fallback `look`),规则即钉档 builder 代码。
- 观测/历史:obs 截断 500 字符;prompt token 预算 3200,超出中段删历史(保留前 2 轮)——即钉档 builder 行为。
- seed/decode 规则:§3.5.6;tokenizer/model revisions:7B `a09a35458c702b33eeacc393d103063234e8bc28`;1.5B(仅描述用途)`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`;bge `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`。
- 预算:harvest ≤ 20 A5000·h,主网格 ≤ 24,headroom ≤ 4,硬顶 48;超顶 → NOT_ESTIMATED。
- 产物:`/work1/zixuan/outputs/agent_memory/external_gate/`;偏差日志 `EXTERNAL_GATE_DEVIATIONS.md`;A6 风格 meta 扫描 JSON。

### 附录 A:提示词包

`pilot/external/PART_V_PROMPTS.json`(canonical JSON;**文件字节** SHA-256 = `46da398ab41e173155c48fde247a12e14e3b0359cb3ba0eb898370694884d739`;MEM_A `707adb37ca25ccb2b2955fc3a0bc9805ec8a6b980e32d5c10e29f8bd7546274b`;MEM_B `51b0d8d5fb51dbb4aecaa8a09e5efce85e137494e75b287d6607a380946124ae`)。A == 钉档 builder 现用 framing(逐字);B 在 memory 头内加"可能与当前任务冲突、先核对 prep 要求"语义,其余逐字相同(全文见 JSON)。

## 10. 终态定义(冻结,穷尽且逐端点)

- **GO**:§6 判据 + 五前提。
- **PARTIAL**:E-harm 显著且观测 ≥+5pp,但 service 端点未过、或其前提(parser/哑点审计)失败而 E-harm 前提不受影响 → **E-harm 必进论文**(app:alfworld);gate 结果留台账(论文无 gate 声称)。**Keystone 规则(冻结)**:service 端点前提失败时,该端点 `p_raw=1` 进入 Holm 排序;E-harm 始终留在冻结 m=3 族内,故至少面对 α/3 阈值,不因无效 service 端点而放松。
- **NO_GO(paper-relevant)**:E-harm 前提全过(完整 60+60 grid、headroom、provenance、missing)、混合 UB(95th percentile bootstrap)< +5pp、两类各自 Bonferroni 97.5th UB < +10pp → "在此 ALFWorld 接口下,预注册的主动程序矛盾不降低成功率至少 5pp(两类等权混合)"。**必写回论文 app:alfworld/discussion。**
- **INCONCLUSIVE**:E-harm 前提全过、效应已估,但既未达 GO/PARTIAL 正判据、也未达 NO_GO 负边界 → 台账记录 + appendix/limitations 披露 E-harm 点估计与区间(一句话)。
- **NOT_ESTIMATED**:某端点自身前提失败(网格不完整、headroom 败、provenance 不足、hash 不符)→ 该端点无信息量,工程内部处理;不进结果表/效应声称;**appendix/limitations 一句话披露**未达可估计门槛及原因(不可省);不影响其他端点结论。
- 全部终态在 RESEARCH_LEDGER 如实记录,与是否进论文无关。红线:看结果后不追加新翻转类型、不调整已冻结量。

## 11. 功效地位声明(冻结)

E-harm 是唯一 +10pp-alternative 功率保障端点(~82% @ 240 独立当量,frozen 假设);真实 +5pp 时 power ≈ 24% → 小效应大概率入 INCONCLUSIVE。E-serve/E-oracle 功效有条件,未过即 PARTIAL,不作负面推断。详见 `PART_V_POWER.md`。
