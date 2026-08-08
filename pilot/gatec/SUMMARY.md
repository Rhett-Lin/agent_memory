# Gate C-lite 汇总（2026-08-08）

## cond1：Memory Transplants 2×2 在此 harness 下能否覆盖 P×S 的问题？——**不能（PASS for cond1）**

已在现有 rollouts（procedural 两模型 3840×2；H-C raw qwen7b 3840）上实测其 arch×content 2×2（架构轴 procedural vs raw，内容轴 matched✓=A11∪A10 三类含 cross-domain analogue、near-miss=A01、unrelated=A00，family-cluster bootstrap 2000）：

| 关键读数 | 值 | 显著性 |
|---|---|---|
| **P×S split (A11−A10) 拆出的 replay/structural 分解** | procedural 7B +0.144 [Holm m=3 SIG；3B +0.102 SIG]；raw −0.014 n.s. | ✅ 两模型 SIG |
| arch×content 的 "matched content effect"（它们唯一能看到的量） | 7B procedural +0.164、raw +0.035 n.s. | 是 marginal，无 replay/structural，无 surface-trap |
| **A11 腿占 matched effect 的份额（procedural 7B）** | **72%**（replay-dominated，三格唯一可见结果——Transplants 框架内不可见） | ✅ |
| arch×content 交互（匹配效果依赖表示层） | procedural−raw I_match = **−0.129 SIG** | ✅ 需 P×S 才能解释 |

**cond1 结论**：arch×content 矩阵在本项目揭示的程序级信号上**系统性失明**——它能说"matched content 有效"，无法说"增益的 72% 来自 replay 而非结构"。P×S 与它是互补问题，且只有 P×S 能问后者。Transplants 基线的"互补性论证"在实测中得到支持，非口头区分。

## cond2：F-MED 的量能否由 Proced-Mem / STITCH 的信号预测？——**大部分不能（PASS for cond2）**

(a) Proced-Mem embedding-rescue 信号（对 pilot rollout 的 memory↔task 配对）：

| 测项 | 结果 | 显著性 |
|---|---|---|
| 用 sim 预测 P（τ_struct 平面） | AUC 0.60（char n-gram 更强：S1 区分接近 1.0，S0 平面 0.35–0.38 = 干净） | S0 干净，S1 预期 |
| sim → uplift 斜率 | 3B +0.50 n.s.；**7B +3.38（raw p=0.008, Holm adj 0.032 SIG）** | **7B SIG——有限冗余** |
| sim → harmful flip | sim_embed n.s.；sim_tf 7B OR 8.31 p=0.028（Holm 后 n.s.） | 不预测 |

→ Proced-Mem 信号在 7B 上与 **aggregate uplift 的边际**有部分重合（与 audit 中"LLM probe 捕获 τ_struct 的 0.75"一致，列为 F-MED 增量必须量化的项——**而非**可替代）；**不预测 harmful flip**，无法替代 P×S 的正交随机化。

(b) STITCH-style intent-mismatch judge（frozen prompt，Qwen2.5-7B，509/512 verbatim judgments 存档）：

- 每 cell alarm 率：A00 100%、A01 93.8%、A10 100%、A11 90.6%——**近乎全报警，无区分**。detector AUC 0.508（heritage-conflict alarm-as-detector 退化为常数预测）。
- family 层 alarm vs HFR 弱负或不相关（n=8，欠功效）。
- 与 audit 的 eq-judge 一致：本 harness 中"结构相似表面的程序等价/不等价"超出 7B LLM 浅层 judge 的能力——但这正是 F-MED 随机化估计量要回答的问题，judgment-based 方法给不出这个答案。

→ STITCH 信号**不预测** F-MED 的 P/τ_trap/harmful flip，Gate C-lite cond2 通过。

## cond1+cond2 合成判定与下一步

- cond1 ✅：P×STransplants 式 2×2 回答不了的问题，实测互补（数据级而非口头级）。
- cond2 ✅：最近的两篇实质邻文（Proced-Mem 检索信号、STITCH intent 信号）均不能预测 F-MED 的核心量；Proced-Mem 在 7B 的 sim→uplift 有限冗余已如实登记（**论文必须报告这个部分冗余，不可文学化**）。
- cond3（published systems profile 逆序）：**不追求**——H-C/H3 已出示形式系统间无显著反转（GPT-5.6 两次裁决；强追即 power chasing）。

**与 §11 的接口**：Gate C-lite 的两项通过，主路径 Go 条件 #1/#2 达成（强基线实测对照完成），论文叙事锚定 **measurement + identification**；published-system profile 逆序 （Go 条件 #3） 不成立已入账、不影响主线 GO 的判断——但该失败必须如实写入论文（第四节后会话）。下一轮动作：PAPER_PLAN（main，measurement/identification 核心 + 覆盖完备性部署含义 + 全部闭环）。

## 工件存档

- `pilot/gatec/transplants_2x2.py`, `transplants_2x2_results.json` — cond1 全表
- `pilot/gatec/procedmem_stitch.py`, `procedmem_results.json` — cond2(a) 模型级
- `pilot/gatec/stitch_probe_judgments.jsonl`（verbatim 512 条 LLM 判定原件）、`stitch_probe_parsed.json`、`stitch_results.json` — cond2(b)
- 代理过程说明：agent-10 中途 timeout，STITCH 判定原始数据已在盘上，parse/汇总由 parent 接手完成（parse 错误修复：原 LLM 输出带自由文本前缀，用正则判 mismatch；原始文件逐字保存）。
