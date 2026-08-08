# NEXT_ACTION — 写作与对外评审阶段（2026-08-08）

**Loop 状态**：Gate 0 → Round 1（pilot/GateA/GateB/H-C/H3）→ Round 2（文献复核 + Gate C-lite + §11 + 论文计划）**完整闭环**。

**完成位置**：
- §11 最终审查：通过（贡献 2/3：`identification design` + `会改变结论的经验发现`；Findings/Workshop 档立即可写，main 档路径已铺通后`Gate C-lite cond1+cond2`通过）
- **主交付物**：`PAPER_PLAN.md` — main 档、measurement+identification 主线、完整贡献声明/相关工作差异化矩阵（全 VERIFIED）/主结果表/图序/大纲/部署含义/写作纪律红线/转向规则

**下一步（唯一）**：进入写作阶段——由 `paper-write` skill 按 `PAPER_PLAN.md` 起稿 Section 1–2 与 Findings 三节；写作冻结禁忌见 `PAPER_PLAN.md` §11（不向 frontier 外推、不声称 coverage-confirmed、不把 H-C 截断差异写成形式机制差异、3B 结论必须条件化）。投稿前由 `auto-review-loop` skill 跑 2 轮外部评审加 90 天 fresh-arxiv 对照。

**纪律保持**：
- Gate C cond3（published-system profile 逆序）放弃追求（H-C/H3 已显示信号空；GPT-5.6 判 power chasing 禁令生效中）。
- TRU-Mem 不启动（与 ReMe/A-MAC/RSCB-MC 的空间关系已如实写成边界）。
- 每个新负结果仍走：自分析 → GPT-5.6 讨论 → 落档（已走两轮，台账第 §外部讨论记录 节为证）。

**Run 命令**：若此时停止 loop，证据链与产出已满足 §13 全部归档文件（见 RESEARCH_LEDGER 轮次记录）；"继续 loop"的默认意思是继续写作阶段而非实验阶段。

**当前状态**：pilot/GateA/GateB GO；H-C NO_GO；H3 formal NO_GO + clarification（完整 transcript 兑现 replay、方向非 script>transcript、覆盖解释 supported-but-unresolved）；§11 审查完成（PAPER_POTENTIAL_REVIEW.md）：贡献计 2/3，Findings/Workshop 档现在可写，main 档唯一缺口 = Gate C 三条件。

**下一步（唯一）**：执行 Gate C 精简模块——不追求 cond3 的系统层逆序（H-C/H3 已显示系统形式间没有显著反转，硬追只会变成 power chasing）：

1. **cond1**：在同一 harness 实测复刻 Memory Transplants 的 architecture×content 2×2（冻结注入版），证明 P×S 与其回答互补问题（不可只在 Related Work 口头区分）。
2. **cond2**：测 Proced-Mem 的 structural 信号与 STITCH 的 intent 信号能否预测 pilot 的 P、τ_trap、harmful flip（若能，F-MED 增量价值降级写入论文）。

两项结果回齐后由 §11 裁定：(a) 通过 → 论文以 measurement+identification 为核心、把覆盖完备性写为关键部署含义，投 main；(b) 任一关键失败 → GPT-5.6 路径，写 Findings 档并结题。

**纪律**：不重跑已否定实验；TRU-Mem 不启动；每个负结果仍走"自分析 → GPT-5.6 讨论 → 落档"三件套。

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
