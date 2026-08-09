# Part V(v4,冻结定稿)— ALFWorld 主动 near-miss + structured admission gate

> **状态:v4 冻结定稿,三轮裁决(2026-08-09,thread 019fe550)全部修正案落地;待 GO to freeze 确认后原文移入 `GATE_PROTOCOL.md` Part V。v1–v3 留存备查,不再有效。**
> 目的:存在性服务验证——「预注册的主动程序矛盾 memory 会伤害 agent」(E-harm,唯一功效保障端点)与「冻结的 structured-oracle proxy gate 服务价值」(E-serve/E-oracle,条件性端点)在 ALFWorld 中以受控设计检验。gate 是工程件,不做 novelty 声明。

## 0. v4 相对 v3 的三轮裁决修正对照

| # | 三轮裁决 | v4 落点 |
|---|---|---|
| 1 | bootstrap 公式要与 null-centered 口径一致;§10 边界不可执行 | §6 公式改写为 null-centered;§10 加 UB=95th / Bonferroni 97.5th 具体算法 |
| 2 | 提示词仍是"稍后附加"承诺;builder hash 有替换缝;tokenizer 口径与钉档实现不符 | §9+附录 A:prompt 包全文 SHA-256 钉死(`PART_V_PROMPTS.json`);builder 字节不动;卡片计量一律用 7B tokenizer `a09a3545` |
| 3 | 8 候选的分配规则有歧义 | §3.4:R/X 各 8 独立候选、各 4 次尝试、R 先 X 后、任一角色失败→目标拒绝;PRNG=numpy PCG64(20260809) |
| 4 | power 文件三处数值/措辞错 | PART_V_POWER.md 已同步改写(~24%、E-serve 条件功效、E-oracle 无功效保障) |

## 1. 假设(冻结后不得改)

- **H-harm(前提,功率保障端点)**:主动 near-miss(X)显著降低成功率相对 N。
- **H-serve(条件性端点)**:G-struct 的 policy value 显著优于 G-S,且对 oracle 非劣(−5pp)。功效按条件接受(见 §11)。
- G-struct = 手工 structured-oracle 代理(inference 无标签非 supervision-free);E-serve 在 G-struct≡oracle 且 G-S 双收时 = ½·E-harm,系统后果非独立证据。

## 2. 家族与翻转(冻结,仅两类,同一机制)

| family | R(P=1) | X-active(P=0) |
|---|---|---|
| pick_heat_then_place(train 459 局) | model-won **heat**-prep episode:同对象类、同 recep 类、异 room/trial/recep 实例 | model-won **cool**-prep episode:同对象类、同 recep 类(heating removes isCool) |
| pick_cool_then_place(train 533 局) | model-won cool-prep episode,同上 | model-won **heat**-prep episode,同对象类、同 recep 类(cooling removes isHot) |

claims 限于两类等权混合;X 源必须自身 goal 下 env-verified `won`。

## 3. 采样、cluster 与 harvest(全冻结)

- `target_cluster = 目标 game + 冻结 R/X 卡`;`rollout_unit = cluster × seed × cell`。
- **采样框**:train split 两类全部 game,canonical path = 相对 `ALFWORLD_DATA` 的 POSIX relpath,按 sha256(path) 升序;PRNG = `numpy.random.Generator(numpy.random.PCG64(20260809))`;对过量候选列表逐个做源筛查,取满 **60 heat + 60 cool valid model-only clusters**;耗尽不满 → NOT_ESTIMATED。
- 三方互斥:confirmatory/校准/headroom 的目标与源两两不相交;同一源 episode 不服务超过一个 cluster。
- **§3.4 Harvest 规则**:每目标先取列表前 **8 个唯一 R 候选、再取 8 个唯一 X 候选**(R 先 X 后);每候选 ≤4 次无记忆尝试(decode seed 见附录 A);取首个 won;任一角色失败 → 该目标拒绝并按序递补(递补目标总数 ≤ 40,超出 → NOT_ESTIMATED);全部尝试入账本;triad 的 R/X 必须同为 model_harvest。
- 不设 missing 容忍:未完成 run 续跑补齐;完整 60+60 不可得 → NOT_ESTIMATED。

## 4. 卡片构造与 τ_s / 哑点审计(全冻结)

- builder:`run_alfworld_check.py` 的 transcript-card 代码路径,**字节不动**,SHA-256 `96ef23ea8516fc95c11d34b7c639e7474ada4f1b9dfd0a153c036b964f11eec3`;卡片 token 计量 = 该 builder 现有行为(Qwen2.5-7B-Instruct tokenizer,rev `a09a35458c702b33eeacc393d103063234e8bc28`);200–300 tokens,R/X 配对 |Δ| ≤ 30。
- 存活断言(逐卡自动):含源 prep 动作行(prep verb + 对象类字面);不含目标 goal 文本;无 family/cell/R/X 标签 grep。
- **τ_s 校准(先于一切 rollout、无 outcome)**:40 个独立校准目标 × 其 R 卡;经验第 5 百分位(numpy.percentile,linear 插值)= 95% R-recall;bge = BAAI/bge-small-en-v1.5,rev `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`。
- **哑点断言**:confirmatory 卡片池 X-acc ≥ 90% 且 |X-acc − R-acc| ≤ 5pp;不达标对按 sha256 序逐对重建(源递补同 §3.4,每对 ≤3 次);仍有 → 哑点 claim NOT_ESTIMATED 且 service GO 不成立(E-serve 仅描述)。

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
- **GO 判据**:三条 Holm p<.05 且 E-harm 观测点 ≥ +5pp(仅声称观测效应);**外加五前提**:§4 哑点断言、§5 parser 判据、§3 完整 60+60 model-only 网格、§7 headroom 通过、§4 builder/prompt hash 核验一致。缺一按 §10 出口。
- 分析脚本 `pilot/external/analyze_gate.py` 于 outcome 检视前 commit(hash 入档),并在报告头重算 q/ICC/DE 与规划值并列(PART_V_POWER.md)。

## 7. Headroom(全部移出 confirmatory grid,全冻结)

- 两组 disjoint headroom 集,各 12 targets × 4 seeds(heat/cool 各半),永不进 confirmatory/校准/E 量。
- **操纵量(纯行为)**:P(目标对象被施加 X 的冲突 prep verb | X 臂) − P(同冲突 verb | N 臂) ≥ +10pp;无该动作计 0;不设步数窗。
- A(prompt 包中 MEM_A)达标 → 主网格用 A;否则 B(MEM_B)于第二组上测;B 达标 → 主网格用 B + protocol 修正案登记;两组均败 → NOT_ESTIMATED。不看成功率。

## 8. 执行顺序(冻结)

builder hash 核验 → prompt 包 hash 核验 → harvest → 卡片池 + 存活断言 → parser 判据 → τ_s 校准 → 哑点断言 → headroom A/(B) → 主网格(PCG64 打散 (cluster,seed,cell),wave 化,wave/batch id 入 meta)→ analyze_gate.py。分析脚本 commit 前不检视任何成功率。

## 9. 运行时冻结

- 模型:Qwen2.5-7B-Instruct,rev `a09a35458c702b33eeacc393d103063234e8bc28`;环境:alfworld 0.4.2 / textworld 1.7.0 / jericho 3.3.1 / vllm 0.6.6.post1 / torch 2.5.1+cu124 / transformers 4.57.6;fp16,gpu_mem_util 0.85,max_model_len 4096。
- 解码:temp 0.7,top_p 0.9,**max_tokens=24**,≤30 steps;admissible-command 接口,`normalize_cmd`+`parse_command`(exact / difflib cutoff 0.65 fuzzy / fallback `look`),规则即钉档 builder 代码。
- 观测/历史:obs 截断 500 字符;prompt token 预算 3200,超出则中段删历史(保留前 2 轮)——即钉档 builder 行为。
- **seed 函数(附录 A)**:`int.from_bytes(md5(canonical_path + "|" + seed)[:4],'little') % 2**31`;harvest:`md5(candidate_path + "|" + role + "|" + attempt)` 同式。
- tokenizer revisions:卡片计量 7B `a09a354`;Qwen2.5-1.5B(若有描述用途)rev `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`;bge rev `5c38ec7c`。
- 预算:harvest ≤ 20 A5000·h,主网格 ≤ 24,headroom ≤ 4,硬顶 48;超顶 → NOT_ESTIMATED。
- 产物:`/work1/zixuan/outputs/agent_memory/external_gate/`;偏差日志;A6 风格 meta 扫描 JSON。

### 附录 A:提示词包

`pilot/external/PART_V_PROMPTS.json`(canonical JSON,indent=1,sort_keys):
- 包 SHA-256:`46da398ab41e173155c48fde247a12e14e3b0359cb3ba0eb898370694884d739`
- MEM_A SHA-256:`707adb37ca25ccb2b2955fc3a0bc9805ec8a6b980e32d5c10e29f8bd7546274b`
- MEM_B SHA-256:`51b0d8d5fb51dbb4aecaa8a09e5efce85e137494e75b287d6607a380946124ae`
- A == 钉档 builder 现用 framing(逐字);B 在 A 的 memory 头内加入"可能与当前任务冲突、先核对 prep 要求"两句,其余逐字相同(全文见 JSON)。

## 10. 出口定义(冻结,出版边界最终版)

- **GO**:§6 判据 + 五前提。
- **NO_GO(paper-relevant)**:(a) 哑点断言与主动翻转审计过;(b) 完整 60+60 model-only 网格;(c) 等权混合 E-harm 上单侧界 < +5pp,**其中**:混合 UB = 其 bootstrap 估计的 95th percentile;两类各自 simultaneous UB = 单侧 Bonferroni 97.5th percentile 且均 < +10pp(措辞限"两类预注册 task type 等权混合的平均");(d) headroom/parser/provenance/missing 全过 → "在此 ALFWorld 接口下,预注册的主动程序矛盾不降低成功率至少 5pp"。**必写回论文 app:alfworld/discussion。**
- **NOT_ESTIMATED**:前提任一失败 → 无信息量,工程内部处理,不进结果表/效应声称;**appendix/limitations 保留一句话披露**未达可估计门槛及原因(不可省);台账全量。
- **PARTIAL**:E-harm 成立而 E-serve/E-oracle 未过 → E-harm 必进论文;gate 失败留台账(论文无 gate 声称)。
- 红线:看结果后不追加新翻转类型、不调整已冻结量。

## 11. 功效地位声明(冻结)

E-harm 是唯一 +10pp-alternative 功率保障端点(~82% @ 240 独立当量,frozen 假设);真实 +5pp 时本设计仅 ~24%(Holm 最坏 α)——小效应大概率落入 NOT_ESTIMATED 而非 paper-relevant NO_GO,此前置不对称性登记在案。E-serve/E-oracle 功效有条件,未过即 PARTIAL,不作负面推断。
