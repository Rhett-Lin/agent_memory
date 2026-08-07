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
