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
