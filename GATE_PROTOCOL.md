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
