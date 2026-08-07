# NEXT_ACTION — Round 1 in flight（2026-08-07）

唯一下一步动作：

Gate A=GO、Gate B=GO（2026-08-08）。Loop Step 4/5 完成：选定 H-C（published write-path systems 的 F-MED profile 逆序，评分 3.95），GATE_PROTOCOL Part II 已预注册冻结。当前 agent-6 正在实现 minimal gate：

1. `pilot/systems/build_raw_cards.py`（800 源任务真实轨迹采集，含 oracle_fallback 标注）；
2. `pilot/systems/build_summary_cards.py`（7B 温度 0 摘要，禁 sealed 标签）；
3. raw + summary 各 3840 rollouts 网格（10 GPU）；
4. `analyze_hc.py` 产出 6 个预注册对比（3 系统对 × {τ_struct, τ_trap}，Holm）。

回来后我做 GO/NO_GO 判定（H-C-3：任一对 |Δτ_struct|≥8pp 且 CI 分离，或 aggregate-equivalent 系统 τ_trap 排序反转）。同步按 loop §14 产出 Round 1 正式汇报（在结果齐后）。

## 状态：H-C minimal gate = NO_GO（2026-08-08 落档）

按冻结判据 NO_GO；GPT-5.6 复审确认。唯一注册新假设（重回 Loop Step 4 评分，不可同数据确认）：

**H3: representation × semantic-coverage 2×2 factorial on τ_replaylike**（GPT-5.6 指定的最高杠杆实验）
- factor 1：surface form（transcript/dialogue vs imperative/script）
- factor 2：semantic coverage（完整决策步骤 vs matched-prefix 缺失）
- 同 canonical proposition set、同来源、同 token 量、同 harness；plus 生态臂 = 原 300-token 截断 transcript
- 两 estimand 分离：deployed-policy effect（300-token cap 下的自然行为）vs pure-form effect（内容固定、语法互换）
- 功效按 family-level covariance 设计；优先加 family 数而非 seed；如可行加一个非 Qwen 模型重复
- 判定树：完整卡下效应仍在→表示机制成立；仅在截断卡下出现→覆盖/截断解释；只在预算帽下→有意义的系统级结论；全灭→归档并进入测量论文写作

执行顺序：
1. ✅ 完成自分析 → 2. ✅ GPT-5.6 讨论 → 3. ✅ 归档 NO_GO → 4. ✅ H3 正式评分选定（4.20 > HA 3.70 > HB 3.60）→ 5. ✅ GATE_PROTOCOL Part III 预注册冻结（含 GPT-5.6 全部条款：fresh families、canonical proposition set、TOST ±3pp、盲标注、两 estimand 分离、功效杠杆=family 数）→ 6. **当前：agent-7 实现 H3（24 fresh families + 5 arms × 2 models，含 acceptance 门槛与 power 模拟）** → 7. 返回后按 §13 冻结判定树判 GO/NO_GO → 8. Round 1 总收尾汇报（loop §14 九段式）；同步评估是否并行起草测量论文骨架。

Gate A 通过前**不做**：Stage B/C/D、TRU-Mem 任何实现、240–320 families 扩展。

## 轮次文件状态

| 文件 | 状态 |
|---|---|
| RESEARCH_LEDGER.md | Gate 0 已写入 |
| LITERATURE_COLLISIONS.md | 待扫描结果 |
| BOTTLENECK_PROFILE.md | 待 pilot 数据 |
| CAUSAL_STRUCTURE_AUDIT.md | 待 Gate A 后强 probe 审计 |
| HYPOTHESIS_CANDIDATES.md | 待 Gate A/B 后（Loop Step 4） |
| SELECTED_HYPOTHESIS.md | 待 Loop Step 5 |
| GATE_PROTOCOL.md | 待选中假设后预注册 |
| GATE_FINDINGS.md | 待 Gate A 判定 |
| DECISION.md | 待 Gate A 判定 |
