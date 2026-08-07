# BOTTLENECK_PROFILE — Round 1 Pilot（已填数，2026-08-07）

> 此处"瓶颈" = 当前 memory gain 中最大的**未识别混淆来源**（identification gap），非计算瓶颈。
> 数据：`/work1/zixuan/outputs/agent_memory/pilot/`（7680 rollouts = 40 fam × 4 sib × 6 cells × 4 seeds × 2 模型）；estimand 经 family-cluster bootstrap（2000 reps，seed 1234）按 GATE_PROTOCOL §2 预注册公式重算。

## 0. Pilot 要回答的问题

在 RelationalOps（SQLite）单环境、frozen Qwen2.5-3B/7B、fixed injection 下，P×S 正交析因能否产生 Memory Transplants（系统/域级 architecture×content）与 Proced-Mem（检索侧 embedding cliff）设计**无法产生**的稳定可解释信号。**答：能。**

## 1. 四张核心图 → 实测判读

**图1 P×S 四格成功率（n=640/cell/model）**

| cell | 3B rate [CI] | 7B rate [CI] |
|---|---|---|
| N | 0.420 [0.331,0.506] | 0.547 [0.433,0.658] |
| Q | 0.402 [0.306,0.497] | 0.573 [0.455,0.688] |
| A00 | 0.373 [0.286,0.458] | 0.497 [0.386,0.603] |
| A01 | 0.362 [0.283,0.442] | 0.578 [0.463,0.692] |
| A10 | 0.308 [0.223,0.394] | 0.589 [0.483,0.688] |
| A11 | 0.409 [0.323,0.497] | 0.733 [0.641,0.820] |

**图2 预注册 estimand（cluster bootstrap 95% CI，SIG = CI 不含 0）**

| estimand | 3B | 7B |
|---|---|---|
| τ_context = Q−N | −0.019 [−0.067,+0.031] n.s. | +0.027 [−0.023,+0.080] n.s. |
| **τ_struct = A10−A00** | **−0.066 [−0.131,−0.002] SIG−** | **+0.092 [+0.036,+0.152] SIG+** |
| τ_trap = A01−A00 | −0.011 [−0.072,+0.047] n.s. | +0.081 [−0.006,+0.173] n.s. |
| τ_replaylike = A11−A10 | +0.102 [+0.039,+0.161] SIG+ | +0.144 [+0.087,+0.200] SIG+ |
| τ_P×S | +0.113 [+0.041,+0.189] SIG+ | +0.063 [−0.031,+0.156] n.s. |

**图3 连续 embedding 相似度 vs uplift**：Spearman 3B −0.020 / 7B +0.074；Pearson 3B +0.002 / 7B +0.105 → 聚合 similarity 几乎不预测 paired uplift（支持 H3 方向）。

**图4 A01 paired harmful flip**：`P(N=1 & A01=0)` = **3B 18.8%** [15.1, 22.5] n=640；**7B 9.2%** [6.3, 12.0] n=640。

## 2. 混淆逐项排除表

| 候选混淆 | 排除手段 | 结果 | 判定 |
|---|---|---|---|
| 模型不读 memory | parseable 率 + compliance 启发式 | 3B 98.9%、7B 99.6% parseable；step_action_coverage A01=0.14/A11=0.16 vs A00/A10≈0（高相似 cell 的 memory 被逐步跟随；低相似 cell 预期低 echo，不否决） | **通过**（弱启发式，标记为局限） |
| oracle/evaluator 错误 | oracle walker 全量执行 | 800/800 合法终态 | 通过 |
| 难度区间失控 | N 条件需 30–70% | 3B 42.0%、7B 54.7% | 通过 |
| 难度不等价 | N 条件 sibling TOST ±7pp | 3B diff≈0.001 [−0.060,+0.063] **等价通过**；7B −0.019 [−0.077,+0.038] **未通过**（见 §3-1） | **部分通过/记录** |
| token 长度伪影 | 六 cells 长度平衡 | 均值 248–256 tokens（max−min < 9，A01/A10/A00/A11 几乎重合） | 通过 |
| 弱泄漏 probe | (tf,embed)→cell label；length→P | sim→S: AUC=1.000（S 由构造决定，预期内）；sim→P: AUC=0.60；length→P: AUC=0.512 | **通过但标记 0.60 待强 probe 复核** |

## 3. 当前最大的未识别混淆来源（结论）

1. **7B difficulty TOST 未过（margin±7pp，左端 −0.077）**：在 N 条件下 7B 的 sibling 间难度差超出预注册 margin 上限约 0.7pp。这是当前最大的识别威胁——7B 的 τ_struct/τ_trap 部分可能由 sibling 难度异质性贡献。处置：Gate B 阶段对 P×S 效应内加 sibling 难度协变量/family random effect 稳健性复核，若结论方向不变则记录为受控局限，否则降级。**这是唯一阻断性标记。**
2. **τ_trap 的方向在 7B 为正（+0.081, n.s.）**——与"near-miss 有害"直觉相反：A01（错程序、高相似）比 A00（无关内容）反而略好。说明 7B 对 near-miss 的利用模式不是简单受害：它可能从高相似文本中获取实体/工具线索，同时对程序差异有相对鲁棒的过滤（harmful flip 仅 9.2% vs 3B 的 18.8%）。这是本轮最重要的**反直觉现象**，也是 Headroom 的直接证据：aggregate 掩盖了模型×cell 的交叉。
3. **模型方向的结构性反转**：3B τ_struct 显著为负（正确程序但低相似 → 比无关内容还差 6.6pp），7B 显著为正（+9.2pp）。同一 memory 内容造成相反方向的因果效应——这是"aggregate-equivalent systems 的 profile divergence"的 pilot 版证据，但当前仅为模型间差异，Gate C 需要替换为**已发表系统**间差异。
4. **compliance 启发式过弱**：echo/coverage 指标在高相似 cell 有信号、低相似 cell 近零，不能单独证明"低相似 cell 中 agent 读了 memory"。Gate B 需要更强的 memory-use 审计（例如 memory-content ablation 一致性：A10 memory 注入 vs 不注入的 action 序列差分分析）。
5. **弱 probe 的 P-AUC=0.60**：tf/embed 两视角对 P 有轻微可预测性（主因 A11/A10 与 A00/A01 的 sim 分布构造性不同——P 与 S 在格子中并不正交可分于 sim 空间）。不算 artifact，但强 probe（LLM probe、char-ngram、action 序列统计）必须在 held-out template 上复核。

## 4. 与 Gate A 的接口

→ 判定结论与理由写入 `GATE_FINDINGS.md` / `DECISION.md`。本文件 §3 的 5 项残余混淆全部转入 Gate B 审计清单（`CAUSAL_STRUCTURE_AUDIT.md`）。

## 5. 补充：harmful flip 的结构性分解（2026-08-07，parent 补充分析）

按 schema × oracle-branch 分解 A01 paired harmful flip，发现危害**精确集中在程序语义真正分歧的状态上**：

| 模式 | 3B | 7B |
|---|---|---|
| P3 cal_finalize（near-miss = 门开在错误子集上） | A=0.100, **B=0.325** | A=0.050, **B=0.175** |
| P3 ticket_gate_close（同上） | A=0.125, **B=0.300** | A=0.000, B=0.000 |
| P1 crm_escalate（near-miss = 极性翻转） | A=0.325, B=0.250 | A=0.125, B=0.025 |
| P1 inv_overstock（极性翻转） | A=0.400, B=0.250 | A=0.100, B=0.275 |
| P2 transfer（方向反转） | 0.000 | **0.287** |
| P4 purge（删除不归档） | 0.225–0.237 | 0.013 |

三点含义：

1. **Near-miss 危害的因果特异性成立**：P3 的伤害几乎只在 near-miss 程序与正确程序产出不同的 branch 出现（B 分支 17.5–32.5% flip，A 分支 0–12.5%）。如果伤害来自泛化干扰/上下文成本，应均匀分布于分支；实测不然。这是 τ_trap 设计有效性的独立证据。
2. **受伤面随模型能力变化**：3B 在所有高相似 archetype 上普遍受害（P1 最严重 0.400），7B 的整体伤害减半且集中于 transfer 方向反转。τ_trap 边际值在 7B 为正、harmful flip 在非零水平的共存由此可解释——near-miss 对强模型兼有"高相似文本提供实体线索"的收益和"特定程序点上击溃"的伤害。**写 H4 时必须按模型与 family 分层，不得写成"near-miss 普遍有害"。**
3. **Gate B 审计需控制该异质性**：连续-S 与稳健性分析应对 archetype 固定效应做检查，避免 π 把 branch 结构错当难度差异（与 §3-1 的 TOST 标记联动复核）。

## 6. 补充：识别优势的饱和模型检验（2026-08-07，CAUSAL_STRUCTURE_AUDIT §3 预登记的操作化测试）

对 5120 条 memory-cell rollout 拟合线性概率饱和模型 `success ~ 1 + sim_tf + sim_embed + P + S + P×S`（cluster bootstrap 2000 reps by family）：

| 系数 | 3B | 7B |
|---|---|---|
| sim_tf | −1.204 [−1.689,−0.524] SIG | −0.956 [−1.605,−0.085] SIG |
| sim_embed | −0.077 n.s. | −0.425 n.s. |
| **P（=S=0 处的 program effect，即 τ_struct）** | −0.007 [−0.106,+0.094] n.s. | **+0.165 [+0.092,+0.238] SIG+** |
| S | +0.711 [+0.343,+1.013] SIG+ | +0.739 [+0.349,+1.035] SIG+ |
| P×S | +0.092 n.s. | +0.023 n.s. |

判定：**识别优势成立（7B）**。控制两种连续 similarity 视角后，program-match 的干净结构效应不仅未被吸收，反而从 raw +0.092 增至 +0.165 ——"embedding similarity + architecture/content 哑变量"（Memory Transplants / Proced-Mem 路径能提供的全部表面解释）无法覆盖 P 的效应（CAUSAL_STRUCTURE_AUDIT §3 操作化判据通过）。sim_tf 在两模型均为显著负系数，说明在 fixed-injection 设计内，"与目标文本重叠更高的卡片反而更差"——与图 3 的零相关一起排除了"S 的操作化定义倒错"这一自我指控。3B 的 P 效应近零且为负，与 raw 估计一致：弱模型不存在可被掩盖的结构效应。

## 7. 补充：行为层 compliance 补强（§3-4 的 A10 ablation follow-up，2026-08-07）

对 640 对同 (sibling,seed) 的 A10-vs-N 动作序列算 LCS/multiset overlap，与 960 对 N-vs-N 不同 seed 复制品对照：3B 0.684 vs 0.726（Δ=−0.042）；7B 0.843 vs 0.864（Δ=−0.022）。低相似 memory 确实改变 agent 行为轨迹，但改变温和——排除"memory 在 prompt 里没被用"与"机械照抄"两种极端解释。至此合规证据链为 parseable 率（98.9%/99.6%）+ 高相似 cell step coverage + 低相似 cell 序列差异 + 饱和模型 P 系数，四层一致。
