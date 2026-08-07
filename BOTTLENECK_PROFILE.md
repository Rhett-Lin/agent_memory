# BOTTLENECK_PROFILE — Round 1 Pilot

> 此处"瓶颈" = 当前 memory gain 中最大的**未识别混淆来源**（identification gap），非计算瓶颈。
> 状态：**框架冻结于 pilot rollout 前（2026-08-07）；数值区待 analyze.py 输出后填入，未经填数不得改动框架。**

## 0. Pilot 要回答的问题

在 RelationalOps（SQLite）单环境、frozen Qwen2.5-3B/7B、fixed injection 下，P（latent program match）× S（surface similarity）正交析因能否产生 Memory Transplants（系统/域级 architecture×content）与 Proced-Mem（检索侧 embedding cliff）设计**无法产生**的稳定可解释信号。

## 1. 四张核心图 → 判定映射

| 图 | 数据 | 判读 |
|---|---|---|
| 图1 P×S 四格成功率（分模型，family-cluster bootstrap CI） | 待填 | A11↑、A10≈0、A01↓ → benchmark-inflation 强信号；A10 显著>0 → 存在 clean structural transfer |
| 图2 相对 N、相对 Q 的 uplift（risk difference） | 待填 | τ_context≈0 才能谈内容效应；cells vs Q 的 uplift 是主证据 |
| 图3 连续 embedding similarity vs paired uplift（Spearman ρ） | 待填 | ρ 高 → similarity 即可解释增益，identification 增量受限；ρ 低是老假设 H3 的支持 |
| 图4 A01 paired harmful flip（HFR） | 待填 | HFR 显著>0 → near-miss 因果危害证据；不可严格配对时按预注册报 marginal risks + CI |

## 2. 混淆逐项排除表（Gate A 前置 → BOTTLENECK 判定）

| 候选混淆 | 排除手段 | 结果 | 判定 |
|---|---|---|---|
| 模型不读 memory | parseable-action 率 >90% + compliance 启发式 | 待填 | 待填 |
| oracle/evaluator 错误 | oracle walker 100% 合法终态 + 抽样人工复核 | 待填 | 待填 |
| 难度区间失控 | N 条件 30–70% | 待填 | 待填 |
| token 长度伪影 | 六 cells 长度平衡（SMD） | 待填 | 待填 |
| sibling 难度不等价 | N 条件 TOST ±7pp | 待填 | 待填 |
| 弱泄漏 | token-overlap/length/embedding 弱 probe AUC≈0.5 | 待填 | 待填 |

## 3. 当前最大的未识别混淆来源（结论区）

待 pilot 数据填入。填写格式：
1. 效应层面：哪个 estimand（τ_struct / τ_trap / τ_P×S）最不可靠、被什么残余混淆威胁；
2. 工程层面：生成器/oracle/harness 中最大的 validity 威胁；
3. 对下一轮的含义：最需要 Loop Step 3 强 probe 或设计修正的点。

## 4. 与 Gate A 的接口

本文件第 1–2 节填数后即 `GATE_FINDINGS.md` 与 `DECISION.md` 的证据底稿；判定阈值见 `GATE_PROTOCOL.md` §4–6（登记后不得放宽）。
