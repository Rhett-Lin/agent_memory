# Part V(草案 v2)— ALFWorld 主动 near-miss + structured admission gate 外部验证

> **状态:DRAFT v2,按 2026-08-09 GPT-5.6 一轮裁决(thread 019fe550)修订单全部重写,待二次裁决。v1 留存于 `PART_V_PREREG_DRAFT.md` 备查,不再有效。**
> 冻结流程:本草案 → GPT-5.6 二次裁决 → 落入 `GATE_PROTOCOL.md` Part V → 实现。
> 目的:存在性服务验证——「程序不兼容的 memory 会伤害 agent」与「结构化 admission gate 能拦住它而(本实验冻结的)surface gate 不能」,在非合成环境 ALFWorld 中能否以功效充足的设计复现。不做 novelty 声明;gate 是工程件,不进论文贡献;拒绝把 E-serve 当独立因果证据。

## 0. v2 相对 v1 的裁决修正对照(全部含在正文)

| # | 一轮裁决 | v2 落点 |
|---|---|---|
| 1 | pick_two/look_at_obj 的 object-class 翻转不是 P=0 | 族改为 **heat/cool 两类**(互为 PDDL 状态冲突),pick_two 废弃 |
| 2 | 功效 3.6%、12 cluster 不足、seed 减半非法 | 网格 **120 distinct games × 4 seeds = 480 triads(1,440 rollouts)**;删 seed 减半,不完整 = NOT_ESTIMATED |
| 3 | sim(X)≥sim(R)−0.05 不足以证 S-gate 拦不住;τ_s 中位数不公平 | τ_s 用独立无 outcome 校准集定到 **R-recall 95%**;断言改为接受率口径(见 §5) |
| 4 | provenance 15% 规则不足 | GO estimand 只收 **model_harvest/model_harvest 配对**(§3.3);gold 永远单独报告 |
| 5 | E-oracle 须入同一 Holm;要 policy-value 显式公式;cluster=game | §6 全部重写 |
| 6 | bootstrap 2,000→不够 | 20,000 reps,stratified over task type |
| 7 | 需 manipulation/headroom 检查 | §7 行为级 headroom(前 10% 确定性子集,不看成功率) |
| 8 | "engineering-internal null vs paper-relevant negative" | §8 出口定义重写 |
| 9 | 9 项冻结清单 | §3/§4/§5/§9 各自落位 |

## 1. 假设(冻结后不得改)

- **H-harm(前提)**:主动 near-miss(X)显著降低成功率相对 N。
- **H-serve(服务)**:G-struct 的 policy value 显著优于 G-S(本实验冻结的那个 bge 阈值 gate),且对 oracle gate 非劣(−5pp)。
- 预声明:G-struct 是**手工 structured-oracle 代理**——词典与设施别字段编码了翻转构造知识,label-free at inference 但非 supervision-free;E-oracle 主要测量 parser 保真度,不构成学习型泛化证据。

## 2. 家族与翻转(冻结,仅两类)

| family | R(P=1 参照) | X-active(P=0) | 冲突的 PDDL 依据 |
|---|---|---|---|
| pick_heat_then_place(train 459 局) | 成功 heat-prep episode:同对象类、异 room/trial、异 recep 实例(同类) | 成功 **cool-prep** episode:**同对象类、同 recep 类**(cooling 与目标 heat 目标互斥:isCool 阻碍 hot 判定的目标描述) | heating removes isCool |
| pick_cool_then_place(train 533 局) | 成功 cool-prep episode,同上 | 成功 **heat-prep** episode,同对象类、同 recep 类 | cooling removes isHot |

- **翻转仅此一类**(prep-verb 状态冲突),两类家族同一机制——claims 条件于这两个 task type,不外推"near-miss in general"。clean 可逆型翻转、实体替换均不注册。
- X 铁律:X 源 episode 在其自身 goal 下 env-verified `won`;矛盾只存在于 X goal 与目标 goal 之间。
- 已知残余风险(预登记,不补救只判 NO_GO):goal 每轮可见、admissible-command 接口、30 步帽、错误轨迹仍教导航——若 X≈N,不能只靠"构造看起来对"就声称效应不存在;出口按 §8。

## 3. 目标采样与源 harvest(全冻结)

1. **目标采样框**:train split 两类全部 game,按 sha256(path) 排序;seed=20260809 的 PRNG 抽 60+60;eligibility(源存在性,见下)不满足时按序递补,递补次数登记;两类型任一可用 < 60 → 总网格 < 120 → **NOT_ESTIMATED**(不允许缩减网格)。
2. **Target/source 不相交**:目标 game 不出现在任何候选源池。
3. **R 源**:同 family、同对象类、不同 trial/room 的 model-won episode。**X 源**:异 family(对照翻转)、同对象类、同 recep 类的 model-won episode。候选列表确定性生成(排序规则同上)。
4. **Harvest 规则**:每候选 ≤4 次无记忆尝试(temp 0.7),按序取首个 won;全部尝试计入 rollout 账本。配对纪律:triad 的 R 与 X 必须**同为 model_harvest**;任一 harvest 失败 → 该 triad 整体不进 GO estimand。
5. **Model-only 下限**:有效 triad ≥ 100(120 容量中)且两类各 ≥ 45,否则 NOT_ESTIMATED;**禁止 gold 填充主分析**。
6. **Gold 角色**:expert gold 卡只为 §7 headroom 的对照参照单独构造(≤24 triads),单独报告,标注 gold-card 结论;不进入任何 GO/E 量。

## 4. 卡片构造(冻结)

- builder:复用 `run_alfworld_check.py` 的 transcript-card 代码路径,**实现首日 commit 其 hash 入档**;token 计数 tokenizer 固定(Qwen2.5-1.5B-Instruct,revision 记录于 cards manifest),预算 200–300 tokens,R/X 配对 |Δ| ≤ 30。
- **存活断言(逐卡,自动)**:card 含源 episode 的 prep 动作行(含 prep verb 与对象类字面);不含目标 goal 文本;不含 family/cell/R/X 标签(grep 零命中)。
- 声明措辞:卡片是"源自合法完整 episode 的 transcript 截窗",不声称是 agent 自然会写的 memory。

## 5. G-S(surface gate)定义与校准(冻结)

- 唯一被考察的 surface gate:**bge-small-en-v1.5(pin revision)cos(goal, card) ≥ τ_s**。"surface gates 不行"的结论永远限于本 gate,不做概念外推。
- **τ_s 校准(先于 rollout、无 outcome)**:独立校准集 = 40 个不进 120 网格的目标×其 R 卡(确定性采样,同上规则);τ_s = 校准集 R-sim 的 **第 5 百分位(R-recall 95%)**。数值一次性写入 JSON 并入档,不再调。
- **G-S 哑点断言(构造审计)**:在 confirmatory 卡片池上要求 X-acceptance ≥ 90% 且 |X-acc − R-acc| ≤ 5pp;不满足则按 §3.3 源递补重造,每 triad 重造 ≤ 3 次;仍不满足 → 相应 claim 记 NOT_ESTIMATED(E-serve 照常测,哑点表述降级为实测接受率)。
- TF 指标仅作描述存档,不参与任何判定。

## 6. Estimands、推断与多重性(冻结)

- **候选分布**:每 (target, seed) 上 R 与 X 各权 1/2。**policy value**:V(g) = E_{c∼{R,X}}[ g(x,c)·succ_c + (1−g(x,c))·succ_N ],配对于同一 (target,seed)。
- **三个主 contrasts(Holm step-down,单侧 bootstrap p)**:E-harm = succ(N)−succ(X)(单侧 +);E-serve = V(G-struct)−V(G-S)(单侧 +);E-oracle-null: H0: V(G-struct)−V(oracle) ≤ −5pp(非劣,单侧)。
- GO 判据:E-harm Holm p<.05 **且观测点 ≥ +5pp**(只声称观测效应,不声称真值 ≥ 5pp——若要后者需 simultaneous 下调界 >5pp,本设计不主张);E-serve Holm p<.05;E-oracle-null Holm p<.05。三条全过 = GO。
- 推断:cluster = target game,stratified bootstrap over task type(60/60 保持),**20,000 reps**,seed 20260809。报 Holm-adjusted p、未校正 95% CI、以及点估计。解析失败率、各 gate 边际接受率如实上报。
- E-serve 的派生性预声明:G-struct≡oracle 且 G-S 双收时,E-serve = ½·E-harm——它不构成独立证据,只度量系统后果。
- **missing-run**:任一 cell 缺失的 triad 整组剔出并计数;剔除率 >10% → NOT_ESTIMATED。

## 7. Headroom / manipulation check(先于成功率检视)

- 在 rollout 顺序的**首个 10% 确定性子集**(48 triads 等距抽样)上,只测行为、不看成功率:trajectory 前 8 步内对目标对象类执行 card 的 prep 动作的比例,R 臂 vs N 臂差须 ≥ +10pp;gold-卡子集(≤24 triads)同测作参照。
- 不达标 → **暂停**,只允许一类预先登记的修正:memory 呈现格式(prompt framing,不改内容/判据),作为 protocol 修正案登记(GPT-5.6 知会)后可继续;修正后只对剩余网格生效,已完成子集丢弃并如实登记。

## 8. 出口定义(冻结,含"负结论是否进论文"的预先边界)

- **GO**:三个 p 值与观测下限全过 → 存在性服务验证成立。
- **NO_GO(paper-relevant)**:仅在以下**全部**成立时——(a) 主动翻转审计与哑点断言通过;(b) model-only 网格完整(§3.5 下限);(c) E-harm 的单侧 95% 上界 < +5pp;(d) headroom/provenance/parser/missing 全过;(e) 单类家族内无反向大子群——结论措辞限为:"在此 ALFWorld 接口下,预注册的两类主动程序矛盾不降低成功率至少 5pp"。**该结论必须写回论文 app:alfworld/discussion 的边界措辞**(预先承诺)。
- **NOT_ESTIMATED / engineering null**:宽区间、p≥.05、功效不足、网格不完整、审计未过的任何零结果——无信息量,不声称效应不存在,工程内部处理,不进论文;台账如实记录(与论文声明无关,因为论文从未声称 gate 有效)。
- **PARTIAL**:E-harm 成立而 E-serve/E-oracle 未过 → gate 无服务价值的工程结论,不进论文(同上理由);E-harm 成立即找新写作措辞小幅强化 app:alfworld。
- 红线:跑完后不得为本实验的"好看"而修改任何已冻结量;不得用"翻转类型不对"为由在看结果后追加新翻转(power chasing 禁令)。

## 9. 执行纪律(冻结)

- Rollout 顺序:PRNG(20260809)打散 (triad,cell) 并分 wave,wave/batch id 入每行 meta;config_hash/env_versions/git_commit 全扫描(A6 风格 JSON)。
- 算力预算:harvest ≤ 20 A5000·h,主网格 ≤ 24 A5000·h,硬顶 48;超出 → NOT_ESTIMATED,不允许砍规模换完成。
- 分析代码先于 outcome 检视 commit;判定脚本(§6)与 builder/calibration 代码 hash 入档。
- 偏差日志 `EXTERNAL_GATE_DEVIATIONS.md`;全部产物 `/work1/zixuan/outputs/agent_memory/external_gate/`。

## 10. 待二次裁决确认点

1. heat↔cool 双族同机制是否满足"最终 task types"(claims 限于这两类);
2. 120×4=480-triad 网格与其 power 假设(+10pp alternative)是否接受;
3. τ_s 第 5 百分位校准与哑点断言口径;
4. E-oracle 非劣并入 Holm m=3 的实现规格;
5. §8 出口与"负结论进/不进论文"的预先边界是否与提交策略一致。
