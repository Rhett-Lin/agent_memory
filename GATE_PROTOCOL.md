# GATE_PROTOCOL — Round 1 Pilot 预注册（Stage A）

状态：**pilot rollout 完成前冻结**。本文件登记 mini-pilot 的主 estimand、推断方案、合规检查与 Gate A 判定阈值。rollout 数据分析不得偏离登记内容；任何探索性分析必须显式标注 exploratory。

登记时间：2026-08-07（pilot 网格启动前）
依据：`loop_file/loop.markdown` §7（Gate A）、§4.3（Headroom）；`tech_report/...` §7、§12、§16。

---

## 1. 实验单位与随机化

- 单位：family × target sibling × cell × model × decoding seed（fixed injection，无 retriever）。
- 配对：同一 (sibling, seed) 组合下，A00/A01/A10/A11/N/Q 六 cells 共用同一初始 DB 状态与解码随机种子，仅注入 memory 不同。
- 网格：40 families × 4 siblings × 6 cells × 4 seeds × 2 模型（Qwen2.5-3B / Qwen2.5-7B，frozen backbone，temperature 0.7, top_p 0.9, max_steps 12）。
- 文本模板 Latin-square counterbalancing；train/dev/test 按 family 隔离（pilot 只含 dev 集概念，不做训练）。

## 2. 预注册主 estimand（技术报告 §7 记号，identity-link risk difference）

主（primary，多重性校正范围）：

1. **τ_context** = E[Y_Q − Y_N] —— context/format effect；
2. **τ_struct** = E[Y(1,0) − Y(0,0)] = E[Y_A10 − Y_A00] —— clean structural transfer；
3. **τ_trap** = E[Y(0,1) − Y(0,0)] = E[Y_A01 − Y_A00] —— near-miss surface trap；
4. **τ_P×S**（interaction）= {E[Y_A11 − Y_A01] − E[Y_A10 − Y_A00]} —— replay-like premium 主信号。

次（secondary）：

5. τ_P（program main effect）、τ_S（surface main effect）、τ_replaylike = E[Y_A11 − Y_A10]；
6. paired harmful-flip rate HFR = P(Y_N=1, Y_A01=0)（配对种子；若解码不可严格复现 → 改报 marginal risks + bootstrap CI 并在文中注明，不得把 unobservable individual flip 当作已识别）；
7. embedding similarity vs paired uplift 的 Spearman 相关（exploratory）。

## 3. 推断方案

- family-cluster bootstrap（重采样单位 = family），10,000 次，报告 percentile 95% CI；
- 主模型：identity-link risk difference（二值 success）；logistic mixed model（family 随机截距）作稳健性；
- 4 个主 estimand × 2 模型的 8 个检验用 Holm 校正；
- near-miss / unrelated cell 的 token 长度与模板的平衡性报告 SMD；
- 难度等价：no-memory 条件下四 sibling 两两 TOST（margin ±7pp）；
- 模型间比较只做描述性方向一致性检验 + 交互项（exploratory）。

## 4. 合规前置检查（Gate A 进入条件，全部通过才看效应）

1. 模型遵循 memory 协议：parseable action 率 >90%；compliance 启发式指标显示 agent 读取了注入 memory（具体定义见 `pilot/README.md`）；
2. oracle/evaluator 正常：oracle walker 100% 合法终态；终态谓词与 rollout DB 复核抽样一致；
3. 任务难度：N 条件 cell-level 成功率处于 30–70%（全 aggregate 与该区间偏离需解释）；
4. 弱 leakage probe（pilot 阶段）：token-overlap / length / 冻结 embedding 无法从 memory 文本预测 cell 标签（AUC 接近 0.5；Gate B 阶段再做 LLM probe / n-gram / trajectory 统计的强版，见 CAUSAL_STRUCTURE_AUDIT.md）。

## 5. Gate A 判定（loop §7 原文执行）

**GO**（满足全部前置检查，且至少一条）：
- 出现稳定、可解释的 cell difference：如 A11 大幅正、A10≈0、A01 显著为负（benchmark-inflation 信号），或 A10 稳定为正（存在可迁移结构）；
- 即 |τ_trap| 或 |τ_struct| 的 95% CI 不含 0，且 family-cluster  bootstrap 下跨 seed 稳定。

**NO_GO**：
- 前置检查全部通过后，τ_P、τ_S、τ_P×S 均接近零且 CI 足够窄（CI 半宽 < 3pp 且点估计 |τ| < 2pp 判定为"接近零"，登记于此后不作事后放宽）；
- 或合规前置检查无法修复（如模型无法遵循协议）→ 记录为资源性 NO_GO 并转向可执行的最小修复。

Gate A 结果写入 `GATE_FINDINGS.md` 与 `DECISION.md`；NO_GO 与 GO 同等详细记录。

## 6. Headroom 测试（loop §4.3，与 Gate A 同证据）

扩展任何 family 前必须证明：至少两个（pilot 阶段可为系统×模型组合，如 3B vs 7B 原始/摘要两种 representation）aggregate-equivalent 配置出现稳定可解释的 cell difference，且不能被难度/token 长度/leakage 混淆解释。失败 → NO_GO，不扩展 240–320 families，不做 TRU-Mem。

## 7. 不做清单（本轮）

Stage B（E 嵌套）、Stage C（P×D/I/V）、Stage D（retrieval）、TRU-Mem、外部 benchmark、240–320 families。

---

# Part II — H-C Minimal Gate 预注册（2026-08-08 冻结，启动前登记）

## 8. 选定假设与 estimand

假设全文见 `SELECTED_HYPOTHESIS.md`。定义每个表示系统 \(h\) 的 profile（沿用 §2 估计程序）：\(\mathcal P_h=(\tau_{context},\tau_{struct},\tau_{trap},\tau_{replaylike},\mathrm{HFR}_{A01})\)。主对比：

- **H-C-1（主 estimand）**：\(\Delta\tau_{struct}(h_i,h_j)=\tau_{struct}^{h_i}-\tau_{struct}^{h_j}\)，对 (raw, procedural) 与 (summary, procedural) 与 (raw, summary) 三对，模型=qwen7b；
- **H-C-2（主 estimand）**：\(\Delta\tau_{trap}\) 与 \(\Delta\mathrm{HFR}\) 同上三对；
- **H-C-3（GO 判据）**：至少一对系统满足 |\(\Delta\tau_{struct}\)|≥8pp 且 cluster bootstrap 95% CI 不含 0，或两个 aggregate gain 差 <3pp 的系统的 τ_trap 排序方向相反且各自 CI 支持。

## 9. 实验设计（冻结）

- 系统（write-path 表示层，忠实映射表另写 `pilot/systems/MAPPING.md`）：
  - `procedural`：pilot 现有表示，**rollouts 直接复用**（不重跑）；
  - `raw`：先在相同 source tasks 上用 qwen7b 各跑一次成功 rollout（仅保留成功 trajectory；失败重试 ≤2，仍失败则该 source 用 oracle 轨迹替代并打标 `oracle_fallback=True`，数量与清单登记）→ 截取到同 token 预算截窗；
  - `summary`：对 `raw` 的同一 trajectory 用 Qwen2.5-7B 摘要（prompt 冻结，温度 0）。
- 网格：3 系统 × 40 fam × 4 sib × 6 cells × 4 seeds × qwen7b；procedural 复用 pilot 已有 3840 条；raw/summary 各新跑 3840 条；source 轨迹采集 800 条。
- token 预算对齐：memory 注入窗口 200–300 tokens（同 pilot）；各系统卡长分布报告 SMD。
- Harness/解析/终态判定/budgets 与 pilot 完全一致（同 commit 的 harness.py，同 config hash 记录）；raw/summary 注入模板与 pilot 相同，仅 [MEMORY] 内容更换。
- 随机化：cell 分配沿用 pilot 的 family 内分层 + Latin square（同一 (fam,sib,seed) 的六 cells 用同一 DB 初始态）。

## 10. 推断（冻结）

- 每系统每 cell 成功率：family-cluster bootstrap 2000 reps；
- Δ profile：两系统 paired（同 family 单元）差异的 cluster bootstrap CI；
- 多重性：主对比 6 个（3 系统对 × {τ_struct, τ_trap}）Holm 校正；HFR 差异与 archetype 分解标 exploratory；
- aggregate-equivalent 定义（预注册）：两系统 A-cells 平均成功率差 <3pp。

## 11. GO / NO_GO（冻结）

- **GO**：满足 H-C-3 → 升级 5 系统 × 3B/14B 并进入 Gate C；
- **NO_GO**：三系统 profile 全对比 CI 覆盖 0，且没出现任何排序反转迹象 → 归档负面结果，回 Loop Step 1，按 §12 Direction D 评估转向（不得继续扩系统数）。

## 12. 防自欺清单（冻结）

- raw/summary 的记忆同样通过 signed sealed 管线生成，注入前跑 `FORBIDDEN_RE_CS` 隔离 grep；
- summary 由 7B 生成时**禁止**接触 sealed 标签（prompt 只含 task instruction + trajectory）；
- 报告 summary 质量抽查：人工（我）抽 10 份，登记"是否复述了错误步骤/丢关键步骤"，失败率 >30% 即触发 kill condition（SELECTED_HYPOTHESIS 已登记）；
- 所有 rollout 记录 commit、config hash、模型版本、GPU、seed；失败 rollout 原样入库，不得补造。

---

# Part III — H3: representation × semantic-coverage 2×2 预注册（2026-08-08 冻结，实现前登记）

> 依据 GPT-5.6（thread 019fdba5-1a9c-79c3-a691-f026e9801544）对 H-C 负结果的裁决条款逐条落实。本实验用**新数据**回答表示/覆盖混杂，绝不复用 H-C 的观测作确认。

## 13. 假设与主 estimand（冻结）

问题：H-C 观测到的 Δτ_replaylike(raw−procedural)=−0.158 由表示形式（form）、语义覆盖（coverage）、或其交互造成。

**析因**（全部卡片从同一 canonical proposition set 组装）：

- **Form A：surface form** ∈ {transcript/dialogue, imperative/script}
- **Form B：semantic coverage** ∈ {complete（含 write-decision + finish 的完整 episode）, prefix（同 canonical 内容但按 H-C raw 的截断规则截去尾段，缺失决策/收尾）}

第 5 生态臂（不进 2×2 推断）：H-C 原样 300-token 硬截 transcript（部署现实对照）。

**主 estimand**（family-cluster bootstrap 2000 reps；Holm 校正以下 3 项）：

1. ε_form = τ_replaylike(script, complete) − τ_replaylike(transcript, complete) ——纯形式效应（内容固定）；
2. ε_cov = τ_replaylike(·, complete) − τ_replaylike(·, prefix)（两形式各自，报告较大者并做 Holm）；
3. ε_int = 交互项（script 相对 transcript 在 complete vs prefix 的 τ_replaylike 差之差）。

**次要 estimand（exploratory 标注）**：生态臂 vs (transcript, prefix) 差异（验证 H-C 条件是否复现）；τ_struct/τ_trap 全谱。

**判定树（冻结）**：
- ε_form 95% CI 不含 0 且方向与 H-C 一致 → 表示机制成立；
- ε_form CI 含 0 且 ε_cov 显著 → 覆盖/截断解释成立；
- 两者均含 0 且生态臂差异显著 → 预算帽系统效应；
- 全部 n.s. 且效应点估计 <4pp，同时 CI 半宽 <4pp → 归档表示假设，回测量论文。
**等价性判定（补 GPT-5.6 对"only"的批评）**：若主张"transcript 不实现 replay 收益"，必须给 transcript-complete 的 τ_replaylike 做 TOST（preregistered margin ±3pp，CI 全落 margin 内才算等价零）。

## 14. 数据与构造（冻结）

1. **family**：新 generator seed 生成的 **24 个新 families**（每 archetype 3 个），与 pilot/H-C 的 40 fam 完全不相交；freshness 用 sealed generator seed 记录。每 family 4 target siblings。
2. **canonical proposition set**：对每个 (family, sibling-lending source episode)，从 sealed program spec 导出**唯一有序命题序列**（proposition = (op, role, content)），transcript 与 script 从同一序列渲染：transcript = 对话式逐步记录（含 tool_result 摘要行），script = 祈使句卡。除措辞外，事实集合、顺序、数字、WHERE 条件**逐一对齐**；渲染差异只允许语态/格式。对齐由程序化 diff 校验（proposition coverage SA）（见 §15 验收 #2）。
3. **coverage=prefix**：对 complete 的 canonical 序列按 H-C raw 的**实测截断分布**（300-token 处截断的规则）截去尾段；保证 prefix 缺失的恰是 write-decision+finish。
4. **token 均衡**：5 臂 token 数（Qwen2.5-1.5B tokenizer）分布 SMD < 0.2；实在做不到时按 arm 报告并纳入协变量稳健性。
5. **provenance**：complete/prefix 双覆盖的 transcript/script 均用 qwen7b 真实成功 rollout 的 trajectory 作为 transcript 素材（**禁止 oracle fallback**——本次失败 source 直接替换该 source 并重采样 family 位，登记替换数）。script 由抽象器（同 pilot procedural 规则）从同一 canonical set 生成：**不是** LLM 摘要，避免同一模型的表述偏好混杂（GPT-5.6 批评项）。
6. **feature 盲标注（outcome-blind）**：由 LLM（1.5B）在不知道 outcome 的条件下给每张卡标注：imperative density、ordered-steps count、是否有显式 postcondition、write-decision 覆盖布尔、完成步覆盖布尔。储存供机制层描述（**禁止**用该特征调参/筛选）。

## 15. 验收门槛（启动主实验前必须全部通过）

1. 24 新 family 的 oracle 100% 合法终态；N 条件 (prefix-arm 任务）成功率落在 30–70%；
2. Canonical 对齐：抽样 20 卡片对（transcript/script 同 set 各 10 对），程序化命题覆盖率 = 100%，人工（我）再抽 5 对逐条核对；
3. 隔离 grep 零命中；family/cell 盲审通过；
4. 5 臂 token SMD < 0.2 或已声明协变量方案；
5. 盲标注特征至少一个维度在 transcript vs script 间显著分离（否则 form 操纵无效，直接终止并报告）。

## 16. 网格与推断（冻结）

- 网格：24 fam × 4 sib × 5 arms（2×2 + eco）× 3 seeds × qwen7b = 1440 rollouts；qwen3b 副臂同网格（2880 总量）。
- 功效：按 pilot family-level covariance 模拟，目标 ε_form=8pp 时 power ≥ 0.8；不足时先加 family（至 32）不加 seed——GPT-5.6 条款。
- 推断：family-cluster bootstrap 2000；Holm 覆盖 3 个主 estimand × 2 模型 = 6 检验；等价性 TOST 独立于 Holm。
- 记录：git commit、config hash、vllm/torch 版本、GPU、seed 全部落 raw JSONL；失败 rollout 原样保留。

## 17. 防自欺清单（冻结）

- 判定树（§13）、TOST margin（±3pp）、功效模拟参数在实现前封存于本文件，不得事后修改；
- 结果若为 null：**同样详细报告**（治理规则 §1：先自分析 → 与 GPT-5.6 讨论 → 再行动）；
- 所有 fresh family 的 sealed/public 切分与 pilot 相同；生态臂的结论措辞必须用"在 300-token 截断构建下"限定（GPT-5.6 措辞条款）；
- 摘要/摘要类工具不得参与卡片构造（§14.5 条款）；transcript 素材若混有 oracle fallback，整批作废重采。

---

# Part IV — Decision-aware Compression 预注册（2026-08-08 冻结，实现前登记）

> 目的：把 H3 的"覆盖>形式"发现从构造性 arm 上升到可部署的 compression policy 实证。所有判据、kills、对照与口径冻结于本部分；写作中不得事后放宽。负结果处置按治理规则 §1：自分析 → GPT-5.6（Codex MCP）→ 再行动。

## 18. 假设与主 estimand（冻结）

**H-DC**：在 token budget 完全等同（≤300 Qwen-1.5B tokens）、内容同源（同一真实 rollout trajectory）、harness/budget/seed 全部一致的前提下，decision-aware compression（dslice）显著优于 naive top-truncation（H-C raw），因为它保留了决策相关 token。

**对照臂（全部已存在，不重跑）**：`H-C raw`（300-token 幼稚截断的真实 transcript，§Part II）；`pilot procedural`；`N`（no memory）；H3 eco/TC（引用视角，不注入新侧）。新增唯一臂：**`dslice`**。

**构造约束（预注册）**：dslice 从 H-C raw 的**未截断原始 harvest trajectory**（`outputs/agent_memory/pilot/raw_harvest/hc_raw_source_shard*-of-010.jsonl`）生成；只使用公开文本（step、tool action、tool_result），**禁止**使用 sealed 字段（family/cell/task_id、P/S、oracle plan）。策略规则在 §20 写死；文本中间产物可在 `pilot/dslice/` 留痕。

**网格**：40 pilot fam × 4 sib × {A00,A01,A10,A11} × 4 seeds × 2 models（qwen3b、qwen7b）= 640 任务(cell) ×4 seeds ×2 = 5,120 rollouts 新增。N 条件从 pilot 复用，不重复。

**主 estimand（3 contrasts × 2 models，Holm m=6）**：
1. **E1 = τ_replaylike(dslice) − τ_replaylike(raw)**：dslice 相对幼稚截断的回款；
2. **E2 = τ_replaylike(dslice)**：dslice 的独立回放溢价（τ_replaylike = A11−A10，family-cluster bootstrap 2000 reps）；
3. **E3 = trap 回归检查**：τ_trap(dslice) − τ_trap(raw) 与 HFR(dslice) − HFR(raw)，secondary，防止压缩放大 harmful flip。

## 19. GO / NO_GO（冻结）

- **GO**：E1 Holm SIG+ 且 ≥ +5pp（至少一个 model），且 E3 不与 raw 恶化 > +5pp（Holm n.s. 以内）。
- **NO_GO**：E1 两模型 Holm n.s.，或 dslice 显著放大 trap（E3 Holm SIG+ 且 > +5pp）。
- **等价确认（不是同义反复）**：若 E1 SIG+，还须事后补报 dslice 卡长度分布与 token 均值，确保"超预算混入"非借口（dslice ≤300 tokens 实测）。

## 20. dslice 压缩规则（全文冻结，实现按字面执行）

输入 harvest trajectory 的逐步 record：每步有 `completion`（模型的 JSON action）和 `tool_result`（环境的执行结果文本）。规则 D1–D5：

1. **保留全部 action JSON（`completion`）拷本**（read/aggregate/insert/update/delete/finish 及 list_tables，全量保留）；
2. **保留 read/aggregate 的 tool_result，但压缩为单行摘要**：对每行 result，若含多行 row dump，只保留 (table, filter-used, matched-row-count, matched-row-1st 的检索键列）四元组；其余列整体舍弃；
3. **整体舍弃 list_tables 的 tool_result**（表列表），其 action 保留；
4. **整体舍弃 Q-only 动作结果**：delete/insert/update 的 tool_result 一律舍弃（成功标志在 finish_answer 里），action 保留；
5. **finish action 与 finish 的 tool_result 整体保留**。

格式：card text = 以上保留项按原顺序拼接；不引入任何新自然语言；不走 LLM；不做 paraphrase。寻找 200–300 tokens,超限的按 D1→D2→D4→D3 顺序逐步扩大到工具结果删掉。卡片生成时记录 token_count、覆盖 flags（has_decision_args, has_finish）到 `pilot/dslice/cards_map.jsonl`，且抽样宣称 100% 保留决策条件所需 aggregate 数与 finish（由对比 assert 检查）。

## 21. 审计纪律（冻结）

- 隔离 grep：`family_idx|cell|A00|A01|A10|A11` 在 dslice 卡片内零命中；
- Token budget：所有 dslice 与 raw 卡的 token-count 实测均值差 < 15 tokens（同 tokenizer）;
- **禁止自动伪影**：压制 1 个不想看到的压缩器"偷塞合并多个结果"行为——任何 card 若引入 harvest 中没有的实体/数值（grep diff），拒绝并记录为 QA-fail（上限 0）。
- Rollout JSONL 与原 raw 网格字段同构（commit/hash/versions/GPU/seed）。

# Part IV-A — H-DC 分析前修正案（2026-08-08 17:05 +0900 登记，先于任何 outcome 检视）

触发：实现期发现 3 处协议缺口；经外部方法学评审（Codex MCP gpt-5.6-sol，thread `019fe063-f1c1-7be2-9875-eee0be7ab7e9`）裁决，全部在**分析开始前**登记。治理链：负结果/缺口 → 自分析 → GPT-5.6 → 再行动，符合 §1。

## A1. 补齐 raw-qwen3b 对照臂（注册前提更正）

注册文本"对照臂（全部已存在，不重跑）"对 qwen3b 不成立（H-C 只跑了 qwen7b），E1(qwen3b) 在既有数据上不可估。更正：新增 raw caps 在 qwen3b 上的网格 = 40 fam × 4 sib × {A00..A11} × 4 seeds = 2,560 rollouts。卡文本/harness/seeds/Latin square 与 dslice-3b 完全一致，仅 rollout JSONL 为新增；这不是"重跑"（该数据从未存在）。E1 由此在两模型上均可估，冻结的 m=6 设计得以保全。

## A2. token 平衡缺口 ↔ 新增主对照 `raw_matched`（§21极简释义被拒绝）

实测：dslice 卡均值 237.5 tok（min 102, max 299），raw 全部 300 → 均值差 62.5 > 15，§21 gate **形式上失败**。"更短=保守"的抗辩不成立（长度/干扰混杂：仅缩短 prompt 本身可能涨分，E1>0 无法干净归因于"决策相关保留"）。修正（外部评审认可的唯一 no-new-text 办法）：

- 新增系统 **`raw_matched`**：每个 memory_id 取其 raw 卡未截断全文，top-truncate 到**配对 dslice 卡的精确 token 数**（同 tokenizer；逐卡配对，实测 |Δtok| 分布报告）。预算按构造精确同额，无 padding、无新文本。
- **E1/E3 的主口径改为对比 `raw_matched`**；对比 raw(300) 的口径降级为 secondary（"实际部署"视角：300 预算上限下的朴素截断基线）。
- 新增网格：raw_matched × {qwen3b, qwen7b} = 5,120 rollouts。

## A3. D1–D5 执行披露（偏差全报，声明措辞收窄）

- **action 拷贝 = parsed 对象的 canonical dump**（修掉 harness parse 残留的孤儿尾段）。验证：4,510 step 中 junk tail 18 例、首对象解析不一致 4 例、尾段含可恢复 tool dict 5 例 → 这些 step 一律退回**逐字保留** completion，不静默丢内容。canonical dump 值/类型无损（json.loads 往返相等）。
- **dedup**：非变异 step（read/aggregate/list_tables）且 action+result 完全重复者去重；write/finish 从不去重。
- **escalation 阶梯分布**（cards_map.jsonl 实测）：stage0=14, stage1=76, stage2=281, stage3=8, stage4=252, stage5=9（stage≥6 为零，QA-fail=0）。
- 声明措辞：效应归于 **"amended dslice package"整体策略**，不归因于字面 D1–D5 的某一组件；机制句（"because it keeps decision-relevant tokens"）降级为设计动机 + 探索性 coverage 佐证，不作为已识别因果链。

## A4. Holm 族精确枚举（primary m=6）

1. E1-7b: τ_replaylike(dslice) − τ_replaylike(raw_matched)，qwen7b，单侧 +；
2. E1-3b: 同上，qwen3b；
3. E2-7b: τ_replaylike(dslice)，qwen7b，双侧；
4. E2-3b: 同上，qwen3b；
5. E3a-7b: HFR(dslice) − HFR(raw_matched) 的**非劣性**（单侧 95% CI 上界 < +5pp），qwen7b；
6. E3a-3b: 同上，qwen3b。

Secondary（不经 Holm，只报 CI）：E1 vs raw(300)；τ_trap(dslice)−τ_trap(raw_matched) 非劣性（CI 下界 > −5pp，符号约定：τ_trap 更负 = trap 更重）；τ_struct(dslice)；各臂 cell 成功率。

## A5. E3 操作化与符号（回应评审 under-specified）

- 非劣性不使用"n.s. ⇒ 通过"逻辑：一律用 bootstrap 单侧 CI 界限对预设 margin（±5pp）判定。
- HFR 配对单位 = (family, sibling, seed)，与 Part II 实现一致（family-cluster bootstrap 2,000 reps）。
- GO 重述（保持冻结原意）：≥1 个模型 E1 Holm SIG+ 且 ≥ +5pp，且该模型 E3a 非劣成立。NO_GO：两模型 E1 均 Holm n.s.，或 E1 显著之模型其 E3a/τ_trap 非劣被违反。

## A6. 历史对照的时间混杂排除

分析时**断言并报告**：raw(300)-7b 历史 rollouts 与本轮新增网格的 `config_hash`、模型 HF snapshot id、harness git commit（含 dirty 状态）逐项一致；任何不一致如实披露为局限性。

## A7. 总新增算力登记

raw-3b (2,560) + raw_matched ×2 模型 (5,120) = 7,680 rollouts；加已在跑的 dslice 5,120，H-DC 合计 12,800。全部跑完前不做任何 outcome 检视（本登记时点：dslice 网格运行中，其余未启动）。
