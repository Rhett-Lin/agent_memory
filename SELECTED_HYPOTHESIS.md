# SELECTED_HYPOTHESIS — Round 1 选定（2026-08-08）

> **状态更新（2026-08-08 深夜）：HC minimal gate = NO_GO，本假设已归档。** 归档全文（判据/实测/GPT-5.6 复审）见 `analysis/HC_NEGATIVE_RESULT_MEMO.md` 与 `DECISION.md` 决策链第 6 行。以下为原始选定记录，保留不改。

**选定：HC — Published write-path systems 的 F-MED profile 逆序**（评分 3.95 / 5；另两候选 HA=3.70、HB=3.60 存档为次级发现）。

## 一句话形式

> 在同一 harness/候选集/预算下，已发表的 raw episodic / summary / procedural(+ReMe、MCMA 变体) 表示系统中，至少两个 aggregate-equivalent 的系统将在 τ_struct 与 τ_trap/harmful-flip 上发生显著反向排序——且该排序跨 3B/7B 与 held-out archetype 保持。

## 为什么是 HC（而不是 HA/HB）

1. **Gate C 是顶会叙事的瓶颈**：三条 Gate C GO 条件中最难的是"stabil、反直觉的 profile divergence between published systems"。HA/HB 即使完美成立也只能作为发现 2/发现 3，不决定论文档次。
2. **pilot 已提供拆解的工具**：P×S 正交 + sealed oracle + 4 张核心图管线已在 7680 rollouts 上验证（parseable 99%、oracle 800/800、审计六项全过），只剩"把多个表示系统接进同一注入接口"这一工程增量。
3. **HA/HB 的关键结果可以免费带出**：HC 的实验矩阵天然包含 single-system（现有 procedural）的 replay/structural/share ρ（HA 的 estimand）与两模型的 scale 对比（HB 的方向）——选中 HC 不牺牲 HA/HB 的证据。

## 不做什么（纪律）

- 不同时推进 TRU-Mem（等 F-MED profile 结论后按 loop §10 决定升级与否）；
- 不扩展 Stage B/C/D（E 嵌套、P×D/I/V、retrieval）——那是 Gate C 之后的事；
- 不调 Gate B 已登记阈值；
-"忠实复刻"只保证表示层（prompt/schema/write-side 规则）贴近原论文，不声称复刻其完整在线管线；每个系统在 README 写清对照映射，留给审稿人可查。

## 最小 Gate（先跑这个）

3 系统（raw / summary / procedural）× pilot 40 fam × 6 cells(A00/A01/A10/A11/N/Q) × 4 seeds × qwen7b 一档 ≈ 3 × 3840 rollouts（约为 pilot 的 1.5 倍 GPU 时长）：
- raw：源 sibling 的完整成功 trajectory（原样截断到 200–300 tokens 的同预算窗口）；
- summary：对同一 trajectory 的 LLM 摘要（Qwen2.5-7B 生成一次，冻结）；
- procedural：现有 pilot 表示（控制组，可直接复用已有 rollouts）。

**升级触发**：任两系统间 |Δτ_struct| ≥ 8pp 且 bootstrap CI 分离，或 τ_trap 排序反转。**失败处置**：三系统 profile 统计不可分 → 记录负面结果、回 Loop Step 1、考虑 §12 Direction D 转向（near-miss-aware retriever 或 capability interaction 方向），不硬撑系统实现。

## 与 Gate C 的路径

HC 最小 Gate 通过后：(i) 补齐 5 系统 + 3B/14B；(ii) 在同一 harness 实现 Memory Transplants 的 architecture×content 2×2 方法基线（Gate C 条件 1）；(iii) 对 Proced-Mem 的 structural 信号与 STITCH 的 intent 信号做"能否预测 pilot 的 P/τ_trap/harmful flip"预测力对比（Gate C 条件 2，复用 audit probes 管线）；(iv) 报告 profile divergence 是否改变任一已发表结论（Gate C 条件 3/4）。
