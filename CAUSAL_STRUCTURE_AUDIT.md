# CAUSAL_STRUCTURE_AUDIT — Round 1

> 对应 loop 文件 §6 Loop Step 3 / §8 Gate B（技术报告 §6.9 数据质量闸门）。状态：**框架冻结（2026-08-07），待 Gate A 通过后执行强审计并填数。** "识别优势"定义与 NO_GO 触发器已登记，不得事后修改。

## 1. 审计范围与触发条件

仅当 Gate A = GO 后执行本节全部强审计；Gate A 之前只做 GATE_PROTOCOL.md §4 的弱版（弱 probe + 难度等价 + 长度平衡）。

## 2. 审计清单（Gate B GO 条件逐条对应）

> 审计执行：2026-08-08（agent-5，pilot/audit/，全部实跑，AUDIT_RESULTS.json 存档）。判定在 §6 登记。

| # | 审计项 | 方法 | 通过阈值（预注册） | 结果 |
|---|---|---|---|---|
| 1 | Program equivalence 一致性 | ≥10% families 独立标注 | 一致率 >0.85 | **未达标（工具层），但标签本身经结构复核正确**：7B 独立 judge（2 措辞 + 1 CoT 变体，8 fam 16 对 48 判定）总一致率 0.250（A 措辞 0.062 / B 0.438 / CoT 0.250），远低于 0.85。逐案复核（`pilot/audit/eq_disagreements.md`，36 条不一致）：judge 对全部跨域同程序（A10）对误判为 different（显式锚定域名词），对 P2 方向反转与 P3 子集 near-miss 全部漏检。对照：8 fam 与其 a10 partner 抽象签名 8/8 逐字符相等；near-miss 签名逐案恰差设计的一处（极性/方向/子集/缺步骤）。**结论：标签结构正确，LLM judge 工具表面锚定失效；后续若再需等价标注，不得用此工具（入 §7 审计教训登记表）。** |
| 2 | Executable consistency | oracle walker 对全部 sibling 执行 | 100% 合法终态 | **通过**：生成时 800/800；审计抽样 8 fam 重跑 160/160 合法终态 PASS。 |
| 3 | 强 leakage probe | char 3-5g TF-IDF + 长度/风格 + bge 嵌入 + LLM probe（1.5B）；family-held-out 30/10 + leave-2-schemas 28 折 | probe AUC 接近 0.5 + calibration；不使用"零泄漏证明"措辞 | **τ_struct（关键平面 S=0，A00 vs A10）全部 probe AUC≈0.35–0.38（arch 折 0.07–0.09），无表面信号**：(a) char-ngram 0.378 [0.150,0.624]；(b) 长度/风格 0.346 [0.111,0.627]；(c) bge 0.380 [0.200,0.589]；(d) LLM probe（1.5B）0.724 [0.653,0.796]——LLM 门控仅可捕获 τ_struct 的 0.75（7B），见 §6 影响评估。family_idx 40-way acc 0.087 vs chance 0.025（卡片几乎不带家族指纹）。**τ_trap 平面（S=1，A01 vs A11）char-ngram AUC 0.996 / bge 0.993**（家族特定实体/措辞层，跨 archetype 降至 0.80/0.57，判为"near-miss 特定该怎样被识别"而非泄漏）；Brier 0.2167（a）。 |
| 4 | No-memory sibling 难度等价 | TOST，预注册 margin ±7pp | 差异落在 margin 内 | **3B 通过**（diff −0.001 [−0.060,+0.063]）；**7B 初测未过**（−0.019 [−0.077,+0.038] 左端越界 0.7pp）→ **修剪攻击后补救通过**：丢 4 个最差错配 sibling 对（8/160 单元）后 TOST [−0.060,+0.036] 通过，且 τ_struct 反增至 +0.105 [+0.049,+0.171] 仍 SIG。per-family 去均值经代数证明恒等无效（平衡网格，max diff 2.8e-17，如实记录）。难度分层：7B hard half +0.068 n.s. / easy half +0.118 SIG——效应非难度假象。 |
| 5 | S 操作化敏感性 | 连续 S（token overlap + embedding 双指标）下重估 τ_struct / τ_trap | 主结论在二值化与连续 S 下方向一致 | **通过**：P=1 内 sim_tf/sim_embed 斜率均 SIG 正（replay premium 以连续趋势复现）；S=1 内斜率全 n.s.（uplift 对 S 平坦 → 非连续 S 驱动，而是 P 驱动）；S=0 内重叠带 τ_struct 复现（7B sim_tf +0.122 [+0.063,+0.188] SIG）；3B 负号反转亦带内复现（−0.097/−0.106 SIG）。二值化与连续结论同向。 |
| 6 | 效应存在性复核 | τ_struct 或 τ_trap 至少一个 | 统计显著、非零、跨 seed 稳定 | **通过**：7B τ_struct +0.092（Holm adj p=0.0048），修剪后 +0.105 仍 SIG；τ_trap 修剪后 +0.099 [+0.015,+0.192] SIG；replay premium 两模型 SIG+；4 seeds 原始 JSONL 逐 seed 分布一致（见 AUDIT_RESULTS.json）；3B τ_P×S Holm SIG+。 |

## 3. "识别优势"登记（对应 EAGLE 的"张量优势"）

**登记定义**：在相同 token 预算、相同 retriever（pilot 为 fixed injection）、相同模型下，P×S 正交析因揭示出的稳定效应，必须不能由以下两者完全解释：

1. Memory Transplants 式 architecture×content 主效应（系统/域级 2×2）；
2. Proced-Mem 式 embedding generalization cliff（检索侧相似度断崖）。

**操作化判定**（pilot 版本）：若 τ_struct 与 τ_trap 的 cell-level 模式可由 (a) memory/target 的 aggregate embedding similarity + (b) architecture/content 两个哑变量的线性组合完全吸收（残差 CI 含 0），则识别优势不成立 → **立即 NO_GO**。

**Round 1 实测（BOTTLENECK §6 饱和模型）**：控制 sim_tf+sim_embed 后，7B 的 P 系数 +0.165 [+0.092,+0.238] 显著（未被吸收，且不饱和原始 τ_struct=+0.092 反而被低估）；3B P≈0 n.s.。两模型 sim_tf 系数均显著为负（3B −1.20、7B −0.96），与图 3 联证 S 操作化无倒错。**识别优势在 7B 成立** → 不进入 NO_GO 分支。

## 4. 失败处置（预登记）

- 任一审计项未过：记录失败细节 → 返回 Loop Step 1；已扩展 family 不得强行保留，诚实报告识别失败；
- 连续 3 次 Gate A/B NO_GO 后必须修正研究对象（重定义 program equivalence 操作化或换环境），不得只调 family/seed 数。

## 5. 证据存档位置

- 审计结果 JSON：`pilot/audit/AUDIT_RESULTS.json`、`pilot/audit/results/{probes,difficulty_robust,continuous_s,equivalence}.json`
- 不一致裁判逐字记录：`pilot/audit/eq_disagreements.md`
- 本文件填数后同步更新 `GATE_FINDINGS.md`、`DECISION.md`、`RESEARCH_LEDGER.md`。

## 6. Gate B 判定（2026-08-08）

**判定：GO（六项结果汇总见 §2 表，全部至少补救后通过）。**

逐项对照 loop §8 GO 条件：

1. 强 leakage probe 无法高精度预测 P/family → **通过（关键平面）**：τ_struct 平面（S=0）四种 probe 全部 AUC≈0.35–0.38；family_idx acc 0.087。τ_trap 平面 0.996 已登记语义（near-miss 在文本内可读，架构内 AUC 0.80），按"不使用零泄漏证明措辞"如实报告。
2. No-memory sibling 难度等价 → **补救后通过**：7B 修剪 8/160 单元后 TOST 通过，且结论性效应（τ_struct）不依赖被修剪单元。
3. 人工审查双人一致率 >0.85 → **工具层未达标，实体层通过**：LLM judge 0.25 一致性是该工具在此 benchmark 的已知失效（judge 被明确要求忽略域名词时仍 100% 锚定域名词——这本身是对"模型读不懂跨表面程序等价"的独立证据，与 pilot 核心发现方向一致）；签名 8/8 相等 + oracle 160/160 执行验证构成更强的标签背书。**登记：Gate D/论文阶段若需外部可信度，必须用人工标注替代 LLM judge。**
4. Continuous-S 复现 → **通过**。
5. τ_struct / τ_trap 至少一个显著非零跨 seed 稳定 → **通过**（修剪前后均 SIG；3B τ_P×S 亦 SIG）。

**审计引入的机制层修正（写入论文诚实叙事）：**

- 7B 的 τ_struct **不应叙述为**"模型识别出了同一程序"——等价 judge 连被直接询问时都无法识别跨域程序等价（判错率 100%）。τ_struct 更可能来自对"操作模板/步骤 schema"（读→查→分支写→验证）的迁移，或实体的统计 grounding。这一机制限制本身就是论文发现的一部分（模型效益的机制与"learning"叙事不一致）。
- 效应集中于 ticket_purge_spam（+0.312 SIG）与 cal_move_headcount（+0.188 SIG）两个 schema；gate 条件"单 archetype 不驱动总体"已验证（6/8 为正），但异质性真实存在，主实验需 240+ family 才能估计 archetype 级精度。

## 7. 审计教训登记表（Gate B 沉淀）

| 教训 | 处置 |
|---|---|
| LLM judge 做 program-equivalence 标注在跨表面上不可靠（0.25 一致） | 后续只用可执行签名 + oracle；需要标注时上人工；该结果本身可以写成论文的一个 side-finding |
| 平衡网格下 per-family 去均值恒等无效 | 难度稳健性只做修剪与分层，不再做无意义调整 |
| τ_trap 平面文本可读性高 | harmful flip 按 branch 分解（BOTTLENECK §5）——危害集中在程序语义真正分歧处，正是"陷阱有效"的直接证据，不算泄漏 |
| LLM probe（1.5B）可捕获 τ_struct 的 0.75（7B 效应） | F-MED 相对"LLM probe 基线"的识别增量必须在论文中量化报告（剩余 25% + judge 另有系统误差，但说明 surface-only 不能无关引用为"识别优势"） |
