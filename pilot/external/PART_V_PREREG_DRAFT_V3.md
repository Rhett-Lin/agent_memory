# Part V(草案 v3,冻结候选)— ALFWorld 主动 near-miss + structured admission gate

> **状态:DRAFT v3,按 2026-08-09 二轮裁决(thread 019fe550)6 项残余修正 + §8 出版边界修正全部落入;待 GO to freeze 确认后原文移入 `GATE_PROTOCOL.md` Part V。v1/v2 留存备查,不再有效。**
> 目的:存在性服务验证——「预注册的主动程序矛盾 memory 会伤害 agent」与「冻结的 structured-oracle proxy gate 能拦住它而本实验冻结的 bge surface gate 不能」,在 ALFWorld(非合成)中以功效充足的设计复现。gate 是工程件,不是论文贡献;不做 novelty 声明。

## 0. v3 相对 v2 的二轮裁决修正对照

| # | 二轮裁决 | v3 落点 |
|---|---|---|
| 1 | 120×4 vs ≥100/10% 自相矛盾;源复用造 crossed 依赖 | §3:精确定义 cluster/unit;**恰好 60+60 valid model-only clusters**;R/X 源逐 cluster 唯一、三方互不重用;R 同 X 同 recep 类;候选上限与 decode seed 全冻结 |
| 2 | G-struct 只有名字没有定义 | §5:parser/词典/决策函数/保真判据全冻结 |
| 3 | headroom 在 confirmatory grid 内、R/N 正确 prep 不识别 memory 使用、prompt B 未冻结 | §7:headroom 全部移出主网格(12+12 disjoint targets),操纵量改为 X 冲突 verb 的采纳率,A/B prompt 附全文 hash |
| 4 | 推断不可执行 | §6:权重/null-centering/+1 校正/Holm 排序/非劣 p/CI 方法/power artifact 全冻结 |
| 5 | 表面审计与 GO 定义有自由裁量缝 | §4/§8:τ_s 算法/重建算法/GO 全体前提全冻结 |
| 6 | 运行时冻结不完整(v1 作废后未继承) | §9:模型 revision/环境/解码/提示词/批量规则全冻结,builder 以 SHA-256 钉死 |
| §8 | 子群措辞与 NOT_ESTIMATED 全免写被拒 | §10:混合解释冻结;NOT_ESTIMATED 保留一句话披露;PARTIAL 必含 E-harm |

## 1. 假设(冻结后不得改)

- **H-harm(前提)**:主动 near-miss(X)显著降低成功率相对 N。
- **H-serve(服务)**:G-struct 的 policy value 显著优于 G-S(本实验冻结的 bge gate),且对 oracle gate 非劣(−5pp)。
- 预声明:G-struct 是**手工 structured-oracle 代理**——词典与设施别字段编码翻转构造知识,inference 无标签但非 supervision-free;E-oracle 主要测量 parser 保真度,不构成学习型泛化证据;E-serve 在 G-struct≡oracle 且 G-S 双收时 = ½·E-harm,是派生系统后果,非独立证据。

## 2. 家族与翻转(冻结,仅两类,同一机制)

| family | R(P=1) | X-active(P=0) |
|---|---|---|
| pick_heat_then_place | model-won **heat**-prep episode:同对象类、**同 recep 类**、异 room/trial/recep 实例 | model-won **cool**-prep episode:同对象类、同 recep 类(heating removes isCool,PDDL 状态互斥) |
| pick_cool_then_place | model-won cool-prep episode,同上 | model-won **heat**-prep episode,同对象类、同 recep 类(cooling removes isHot) |

- 仅两 task type 一类翻转(prep-verb 状态冲突);claims 限于该两类的等权混合,不外推。
- X 铁律:X 源在其自身 goal 下 env-verified `won`,矛盾只在 X goal 与目标 goal 之间。

## 3. 采样、cluster 定义与 harvest(全冻结)

- `target_cluster = 一个目标 game + 其冻结 R/X 卡`;`rollout_unit = target_cluster × seed × cell`。
- **采样框**:train split 两类全部 game,按 sha256(game 路径) 排序;PRNG(seed 20260809)对**过量候选列表**逐个做源存在性筛查(eligibility:§3.4 能找到唯一可用 R 与 X),按序取满 **60 heat + 60 cool valid model-only clusters**;候选耗尽仍不满 60+60 → **NOT_ESTIMATED**(不允许缩减网格)。
- Target/source 三方互斥:confirmatory 目标、τ_s 校准目标与源、headroom 目标与源两两不相交;**同一源 episode 不得服务超过一个 cluster**。
- **Harvest**:每目标确定性候选源列表(排序规则同上 sha256);每候选 ≤4 次无记忆尝试(temp 0.7,decode seed = hash(candidate_path, attempt_idx) 冻结);取首个 env-verified won;**每 cluster 候选源尝试上限 8 个**(超出 → 该目标按序递补,递补总数 ≤ 40,超出 → NOT_ESTIMATED);全部尝试计入账本;triad 的 R/X 必须同为 model_harvest。
- ✂ **不设 missing 容忍**:未完成 run 一律续跑补齐;完整 60+60 网格不可得 → NOT_ESTIMATED。

## 4. 卡片构造与 τ_s / 哑点审计(全冻结)

- builder:`run_alfworld_check.py` transcript-card 代码路径,以 **SHA-256 `96ef23ea8516fc95c11d34b7c639e7474ada4f1b9dfd0a153c036b964f11eec3`**(冻结提交时若实现有改动,以新 commit 的对应 hash 替换并如实记录)钉死;tokenizer = Qwen2.5-1.5B-Instruct(revision 写入 cards manifest);200–300 tokens,R/X 配对 |Δ| ≤ 30。
- 存活断言(逐卡自动):含源 prep 动作行(prep verb + 对象类字面);不含目标 goal 文本;无 family/cell/R/X 标签 grep。
- **τ_s 校准(先于一切 rollout、无 outcome)**:40 个独立校准目标 × 其 R 卡;经验第 5 百分位(numpy `percentile`,linear interpolation,ties 按实现默认;bge-small-en-v1.5 HF snapshot revision 钉死于校准 JSON)→ 95% R-recall。
- **哑点断言**(confirmatory 卡片池):X-acc ≥ 90% 且 |X-acc − R-acc| ≤ 5pp;不达标对(同 R 配对)按 sha256 序逐对重建,源递补规则同 §3,每对 ≤3 次;仍有不达标 → 哑点 claim 记 NOT_ESTIMATED 且**整体 service GO 不成立**(E-serve 仅描述上报)。

## 5. G-struct 定义(全冻结)

- **goal parse**:`hot|heated|heat` → heat;`cool|cooled` → cool(对 goal 文本小写化后词典匹配;两类同含 → parse-fail)。
- **card parse**:源 episode 的 prep 动作行同上词典; appliance/object 归一化(小写、去形容词 {clean,hot,heated,cool,cooled,cold,chilled,sliced}、单复数折叠);同含两 prep → parse-fail。
- **决策**:card_prep == goal_prep → admit;互为相反(heat↔cool)→ reject(记为 contradiction-rejection);parse-fail → abstain(**记为 parse-failure,不计入 contradiction-rejection**)。
- **保真判据(rollout 前,卡片池 + 校准集)**:每 (type × arm) parse coverage ≥ 95%;R admission ≥ 95%;X 的 contradiction-rejection ≥ 95%(经解析矛盾,非 parse-fail)。parser 允许存在 ≤5% 误差,E-oracle 保持随机项,留在 Holm m=3。
- **G-S**:bge(goal, card) ≥ τ_s。**G-learn**:零样本 pilot P̂(冻结权重,不重训),只报 AUC,不进 GO;Part V 标签重训仅探索性。

## 6. Estimands 与推断(全冻结)

- 候选分布:每 (target,seed) 上 R/X 等权 ½。**policy value**:V(g) = E_c[ g·succ_c + (1−g)·succ_N ]。
- 类型等权 ½+½,类型内 target/seed 等权。对应对齐配对 (target,seed)。
- **Holm m=3(单侧)**:① E-harm = succ(N)−succ(X),H0: ≤0;② E-serve = V(G-struct)−V(G-S),H0: ≤0;③ E-oracle-noninf,H0: V(G-struct)−V(oracle) ≤ −0.05。
- Original p 值(全冻结):cluster bootstrap over target(60/60 stratified),**B=20,000**,seed 20260809;原始单侧 p = (1 + #{b* ≤ H0 界})/(B+1);Holm:按原始 p 升序,第 k 个与 α/(m−k+1) 比较,tie 按 estimand 序号 ①②③ 保序并如实记录。描述性 CI:percentile 法(2.5/97.5)。
- **GO 判据**:三条 Holm p<.05 且 E-harm 观测点 ≥ +5pp(仅声称观测效应,不声称真值 ≥5pp);外加 §4 哑点断言、§5 parser 判据、§3 完整 60+60 model-only 网格、§7 headroom 通过——**五个前提全部成立才 GO**,缺一即按 §10 对应出口。
- **missing-run**:无容忍(§3 续跑补齐)。
- **Power artifact**:`pilot/external/PART_V_POWER.md`(q=.25 先验 discordance、ICC≈.35、design effect≈2、+10pp alternative → 480 triads ≈ 240 独立当量 ≈ 82% power;E-serve 在冻结 gate 决策下继承 E-harm 功效的推导一并入档;E-oracle 的 parser-误差模型说明)。

## 7. Headroom(全部移出 confirmatory grid,全冻结)

- **集合**:两组 disjoint headroom 集,各 12 targets × 4 seeds(heat/cool 各半),永不进入 confirmatory/校准/任何 E 量。
- **提示词**:A = 现用 memory framing;B = 预写替代 framing(强化"经验可能与当前目标冲突,请核对 prep 要求"),**两份全文连同 sha256 在冻结提交时附档**。
- **操纵量(行为,不看成功率)**:P(X 冲突 prep verb 在 trajectory 中被采纳于目标对象 | X 臂) − P(同冲突 verb 被采纳 | N 臂) ≥ +10pp;无该采纳计 0;不设步数窗。
- A 达标 → 主网格用 A;A 不达标 → B 在第二组上测;B 达标 → 主网格用 B(并在 protocol 修正案登记);两组均不达标 → **NOT_ESTIMATED**。

## 8. G-S 校准/审计的执行顺序(冻结)

builder 钉 hash → 卡片池(含 harvest)→ parser 判据 → τ_s 校准集算 τ_s → 哑点断言 → headroom A/(B) → 主网格(PRNG 20260809 打散 (cluster,seed,cell) → wave 化,wave/batch id 入 meta)→ 分析。任何 outcome(成功率)在分析脚本 commit 前不检视。

## 9. 运行时冻结

- 模型:Qwen/Qwen2.5-7B-Instruct,revision `a09a35458c702b33eeacc393d103063234e8bc28`(A6_CHECKS 钉档)。
- 环境:alfworld 0.4.2 / textworld 1.7.0 / jericho 3.3.1 / vllm 0.6.6.post1 / torch 2.5.1+cu124 / transformers 4.57.6;fp16,gpu_mem_util 0.85,max_model_len 4096。
- 解码:temp 0.7,top_p 0.9,≤512 tokens/step,≤30 steps;admissible-command 接口,解析失败 → `look`;decode seed = hash(game_path, seed)。
- 提示词/observation 截断:沿用上次检查实现(冻结提交时以代码 hash 入档)。
- 预算:harvest ≤ 20 A5000·h,主网格 ≤ 24 A5000·h,headroom/gold ≤ 4,硬顶 48;超顶 → NOT_ESTIMATED,不削规模。
- 产物:`/work1/zixuan/outputs/agent_memory/external_gate/`;偏差日志 `EXTERNAL_GATE_DEVIATIONS.md`;A6 风格 meta 扫描 JSON。

## 10. 出口定义(冻结,含出版边界——二轮裁决修正版)

- **GO**:§6 判据 + 五前提全过。
- **NO_GO(paper-relevant)**:(a) 主动翻转审计与哑点断言过;(b) 完整 60+60 model-only 网格;(c) **等权混合 E-harm 单侧 95% 上界 < +5pp**,且两类各自 simultaneous 上界 < +10pp(措辞必须为"两类预注册 task type 等权混合的平均",不暗示逐类 <5pp);(d) headroom/parser/provenance/missing 全过→ 结论"在此 ALFWorld 接口下,预注册的主动程序矛盾不降低成功率至少 5pp"。**必写回论文 app:alfworld/discussion 边界。**
- **NOT_ESTIMATED**:任何前提失败 → 无信息量工程内部处理,不进结果表/效应声称;**但论文 appendix/limitations 保留一句话披露**:预注册的主动翻转后续实验未达到可估计门槛及原因(二轮裁决强制,不可省)。台账全量记录。
- **PARTIAL**:E-harm 成立而 E-serve/E-oracle 未过 → **E-harm 必进论文**(app:alfworld 强化);gate 失败留台账(论文无 gate 声称)。
- 全部终态在 RESEARCH_LEDGER 如实记录,与是否进论文无关。
- 红线:看结果后不追加新翻转类型、不调整已冻结量。

## 11. 待 GO-to-freeze 确认点

1. 恰好 60+60 clusters 的筛查-到满规则与其耗尽出口;
2. G-struct 保真判据阈值(95/95/95);
3. headroom 操纵量定义与 A/B 两阶段;
4. power artifact 参数(q=.25, ICC≈.35, DE≈2, +10pp);
5. §10 出版边界的最终措辞。
