# PROJECT_HANDOFF — CausalMemAgent / CausalMemBench 全项目交接文档

> **用途**：在另一台服务器上继续本项目。读完本文档应能理解全部研究逻辑、复现已有结果、并接续当前进行中的工作。
> **快照时间**：2026-08-11 17:00 JST ｜ **git HEAD**：`88427e7`（s2 rc1 comparator）
> **注意**：本文档写作时 `pilot/peval/phi_d/s2_rc2/` 有另一会话正在活跃工作，该目录状态可能已变。

---

## 0. 一句话概括

**这是一篇因果测量论文 + 一条正在建的部署方法线。** 论文回答"agent memory 带来的性能提升到底由什么构成"——是真结构迁移、还是照抄见过的答案、还是被表面相似的错误记忆带偏。方法线回答"这个发现怎么用到真实 agent 系统里"。

---

## 1. 研究问题与核心设计

### 1.1 动机

现有 agent memory 系统都报告 aggregate accuracy 提升，但 aggregate 无法告诉你增益的**构成**：

- **replay**：原样重放见过的 episode；
- **clean structural transfer**：表面变化下的真程序迁移；
- **surface trap**：表面相似但程序不兼容 → 有害；
- **context effect**：仅仅多了一段文本带来的影响。

### 1.2 识别设计（论文唯一不可替代的贡献）

在 memory–target **pair 级别**正交随机化两个变量：

| 变量 | 含义 | 部署可得性 |
|---|---|---|
| **P** | program match：memory 与目标任务是否属同一程序等价类 | ❌ evaluator-only（密封） |
| **S** | surface similarity：表面相似度 | ✅ 检索器自己就在算 |

得到 2×2 共 4 个 cell，加 2 个对照 = **6 cells**：

| cell | P | S | 含义 |
|---|---|---|---|
| `A11` | 1 | 1 | 同域同程序（replay 腿） |
| `A10` | 1 | 0 | **跨域真等价**（clean structural transfer） |
| `A01` | 0 | 1 | **near-miss 陷阱**（表面像、程序冲突） |
| `A00` | 0 | 0 | 无关记忆 |
| `N` | — | — | **无 memory 对照**（反事实基线） |
| `Q` | — | — | sham 卡（任务无关填充，控制 context 长度） |

**铁律（Oracle 隔离）**：`z`（潜在程序）、family ID、transformation ID、near-miss label、P/S 标签**只写入 `data/sealed/`**，agent 与 harness 代码不得读取。agent 可见的只有 task text、tool schema、通过工具暴露的 state。

### 1.3 环境与程序 DSL

- **环境**：RelationalOps —— 内存 SQLite（`sqlite3.connect(":memory:")`，由 tables dict 的 `deepcopy` 构建），工具 API = `read / aggregate / insert / update / delete / finish`，终态由**程序化谓词**判定（**不用 LLM judge**）。
- **程序**：`z = (G_prec, C_safety, C_terminal, B_recovery)`。
- **等价类定义（关键，全项目引用此定义）**，见 [pilot/program_dsl.py:10-16](pilot/program_dsl.py#L10)：
  > 两个任务 P=1 当且仅当它们共享同一**抽象签名**——**相同步骤集、相同偏序、相同算子极性、相同写目标角色**——与表面实体、措辞、业务域渲染无关。**具体阈值 / 实体取值是 instance parameter，不属于等价类。**
- **4 个 archetype × 2 个领域渲染 = 8 schema**：
  | archetype | near-miss (z′) 构造 | 性质 |
  |---|---|---|
  | `conditional_write` (P1) | 比较符翻转（`>` ↔ `<=`） | 存在型 |
  | `two_row_transfer` (P2) | 方向反转（source↔destination） | 存在型 |
  | `aggregate_gate` (P3) | 门控子集错误（`none open` ↔ `at least one done`） | 存在型 |
  | `delete_after_capture` (P4) | 跳过 archive | 缺失型（但文本有**显式否定**） |
- **重要构造事实**：四种 z′ **本身都是完全可执行、且能到达自己合法终态的程序**。所以"沙箱跑一跑看崩不崩"零判别力。
- **重要外部效度限制**：翻转结果被**逐字写进文本**（`"at or below"` vs `"above"`，[generate_families.py:383,506](pilot/generate_families.py#L383)）。这使本 benchmark 成为 **explicit-policy 上界评测**。

### 1.4 配对设计

对固定的 `(sibling, seed)`，**六个 cell 的初始 DB 状态逐字节相同**（三条独立 RNG 流：family 参数 / sibling 实体 / per-seed 干扰项），decode seed 也共享。→ 支持成对推断与精确反事实。

---

## 2. 当前状态总览

| 线 | 状态 | 结论 |
|---|---|---|
| Gate 0 新颖性 | 已冻结不可回退 | **PROCEED WITH CAUTION**，5.5–6/10 |
| Gate A（识别） | **GO** (08-07) | 效应可识别 |
| Gate B（因果有效性） | **GO** (08-08) | 六项审计全过 |
| Gate C-lite | **cond1+cond2 通过** (08-08) | 三个最强邻居实测无法复现本分解 |
| H-C（表示形式逆序） | **NO_GO** | 假设层连续 NO_GO 计数 1 |
| H3（form × coverage） | **formal NO_GO + clarification** | 计数 2（阈值：6 次触发终止） |
| H-DC（决策感知压缩部署） | **GO 但限档** | 188/640 oracle fallback 污染 |
| Part V（ALFWorld 主动 near-miss） | **NOT_ESTIMATED** (08-10) | 结构性天花板，0 rollouts |
| 论文本体 | **17pp 完成**，外部评审 6/10 "Almost" 终止 | 贡献 2/3 |
| φ+d lane A（prompted 抽取 + comparator v0） | **DEMOTE** (08-10) | 14/14 kill 门全灭 |
| **φ+d lane C（SFT 抽取器）** | **✅ 成功** (08-11) | 8/8 门，抽取问题解决 |
| **S2 comparator** | **rc1 已冻结未跑**；rc2 撰写中 | 640 对一次跑待执行 |
| Part VI（τ-bench 外部验证） | **v4 定稿候选，冻结包待实化** | ≤60 A5000·h 预算已冻结 |
| P 部署可得性 | **5 轮外部裁决完成**，方案草案已出 | 见 §9 |

---

## 3. 已完成的证据链（按时间）

### 3.1 Gate 0：新颖性核验（2026-08-07，不可回退）

- 总体新颖性 **5.5–6/10**，诚实档位 Findings/Workshop，main 有条件可达。
- **必须实测对比的强 baseline**：Memory Transplants (ICLR26 MemAgents)、OMAC、Proced-Mem、STITCH/CAME-Bench、A-MAC、RSCB-MC、Decision-Aware Memory Cards。
- **禁引**：`RC-MemStop`（经核验为 Analemma FARS 机器自动生成产物，无 arXiv/DOI）。
- **已被占据、不得 claim 的空间**：utility admission/pruning（ReMe/HiMPO/AttriMem）、write/read gate（MemGate/MemRouter/ConsistencyGate）、agent 级 conformal risk control（CORA/ToolChain-CRC）。
- **碰撞**：`arXiv 2602.01869` = **Skill-Pro**（ICML 2026 Spotlight，activation/execution/termination conditions）；措辞护栏已冻结：禁用 "program compatibility belief / procedural signature / progressive program inference"。

### 3.2 主 pilot（Gate A/B）

- 网格：40 families × 4 target siblings × 6 cells × 4 seeds × 2 模型 = **7,680 rollouts**（10×A5000 上约 1h）。
- 验证：parseable 99%、oracle 800/800 合法终态、隔离 grep 零命中、embed 校准 PASS。
- Gate B 六项审计全过：强 probe 关键平面干净（AUC 0.35–0.38）、难度修剪后 TOST 通过、连续-S 复现、签名 8/8 相等、oracle 160/160。
- **重大工具失效登记**：LLM judge 判程序等价**错误率 100%**（后续机制叙事改为"操作模板迁移"而非"程序识别"）。

### 3.3 主结果（论文正文数字）

| 发现 | 数值 |
|---|---|
| **replay dominance** | 7B 中 matched 效应的 **72%** 来自 A11 腿；A11 0.733 vs N 0.547 = **+18.6pp** [+11.4,+26.1] |
| **scale reversal** | τ_struct 7B **+0.092** [+0.036,+0.152] Holm SIG；3B **−0.066** n.s.，τ_P×S +11.3pp SIG |
| **harmful flip** | joint HFR（分母 640）：3B **18.8%**、7B **9.2%**；集中在程序语义真正分歧的 branch |
| replay premium | 7B +0.144 / 3B +0.102，双模型 SIG |
| τ_context | ≈ 0 |
| **LLM judge 失效** | STITCH 式 intent judge AUC **0.508**（全 cell 几乎全报警）；跨域等价 A10 100% 判错 |
| **coverage not form** | 完整 transcript 也能兑现 replay（TOST 拒绝 ±3pp 等价）；300-token 截断几乎归零 |
| Llama-8B 复现 | replay share 79%，τ_struct +0.047 [+0.020,+0.073]，HFR 0.100 |

### 3.4 rollout 总账

| 实验 | rollouts |
|---|---|
| 主 pilot（Qwen 3B+7B） | 7,680 |
| H3 form×coverage（32 fresh families） | 9,216 |
| Llama-3.1-8B 复现 | 3,840 |
| H-DC deployment | 12,800 |
| **合计** | **≈ 33,536** |

### 3.5 负结果与限档（同等重要，必须保留）

- **H-C NO_GO**：三种 write-path 表示形式（raw/summary/procedural）的 profile 差异 |Δτ_struct| 最大 5pp 且 CI 均跨 0。
- **H3 formal NO_GO**：ε_form 方向反转（transcript ≥ script），coverage 结论只能写 **"supported-but-unresolved"**。
- **H-DC 限档**：188/640 (29.4%) 卡是 oracle 重建 fallback；真实模型轨迹上 7B 效应塌为 **+0.041（CI 跨 0）**。最终措辞档位：**"robust mixed-provenance benchmark contrast"**，不是真实部署验证。**blocking follow-up = fallback-free re-harvest，需新算力，未执行。**
- **Part V NOT_ESTIMATED**：ALFWorld 主动 near-miss 的池分配上界 **28 heat / 26 cool < 所需 50+50**，任何胜率下 P(≥50)=0，结构性天花板。**0 rollouts、0 outcome 检视。**
- **comparator v0 DEMOTE**：14/14 kill 门全灭；AUC 0.522/0.512 ≈ 随机。核心科学结论：**幸存的硬否决是结构性（模板指纹）而无语义**——在 A01 与 A11 上同频触发（0.328 vs 0.341，零分离）。

### 3.6 φ+d 线（P 估计评估器）完整历史

| 阶段 | 结果 |
|---|---|
| sim_tf → P | AUC 0.608 / **0.595**（S=1 切面） |
| sim_embed → P | 0.606 / **0.529（等于硬币）** |
| STITCH 式 intent judge | **0.508** |
| 早期分解式 CoT（16 对） | 一致率 25%，A10 0% |
| **P̂ v1**（logistic + TF-IDF pair 特征 + 15 手工特征） | family-CV **0.966/0.935**；**LOAO 0.636/0.590**；conditional_write 留出 **0.408（低于随机）** |
| 分解式 judge（canonical run4766） | 0.597 / **0.664**；A01 误收 19.4%、A10 误杀 85%、A11 保留 45% |
| prompted φ 抽取（guided，救援后） | 532/532 合法，但**扩编忠实度审计：0/11 字段够格硬否决**（假 ABSENT 19.6%、branch 节点 52.8%） |
| **SFT2 抽取器（08-11）** | **✅ 见下** |

### 3.7 SFT2 抽取器（2026-08-11 里程碑）

这是**解开 S2 死结的那一步**。

**数据生产**（`pilot/peval/phi_d/sft2/`）：
- 8/8 schema，**4,000 文本 / 200 个不相交族**（seed 20260812，150/25/25 → 3,000/500/500）+ 嵌套学习曲线 300/1k/3k；
- `validate_ir` 4,000/4,000；**82,151/82,151 全检通过**；全部产物双跑逐字节一致；**对 732 个 sealed hash 零碰撞**。

**LoRA 训练**：
- 3,000 例、376 步、loss 0.33→~1e-4、held-out-family val 6.9e-5；MAXLEN 实测选 2304；
- adapter：`/work1/zixuan/checkpoints/agent_memory/phi_sft/sft2/`（54MB）。

**抽取门（test500，全部 4 archetype 持出族）：8/8 全过且每项地板级**
- parse 1.000（零 repair）、evidence 1.000（6,293/6,293）、precision/recall 1.000、per-arch 召回 1.000、false-ABSENT 0、双侧覆盖 1.000、LCS 1.000；
- **500/500 逐字节全 IR 相等**。

**canonical 532 重抽取 + 扩编审计**（`sft2_eval/`）：
| 指标 | prompted 时代 | **SFT2 时代** |
|---|---|---|
| 532 合法率 | 100%（需救援） | **532/532 首过、零修复** |
| evidence span | 96.9–100% | **6,621/6,621 = 1.000** |
| **pair 双侧 JOINT 覆盖** | **15.6–42.5%** | **1.000（全部 640 对，四 archetype 全 1.000）** |
| **可硬否决字段** | **0 / 11** | **10 / 11**（`scope` 永久排除） |
| roles 假 ABSENT | 0.327 | **0.000** |

→ **S2 比较器解除阻塞。**

### 3.8 S2 comparator（当前活跃）

- **rc1**：`pilot/peval/phi_d/s2/`，规则全文 `S2_SPEC.md`（560 行），确定性实现 `s2_comparator.py`（629 行），29/29 合成 fixture 通过，**冻结 hash `96901e3dfc8346073dfc936ec27a795bde6cfa6fababdd93918a2dfd1184c416`**。**640 对尚未执行。**
- **rc2**：`pilot/peval/phi_d/s2_rc2/S2_RC2_SPEC.md`（撰写中，另一会话）。rc1 永久锁定作证据，rc2 只以 hash-pinned import 读取 rc1。
- 核心规则：完整性证书 + 规范化决策函数（`complement + effect swap = 等价`，`complement 不 swap = 矛盾`）+ **非补偿性矛盾一票否决** + 三值 `{match, contradict, unknown}` + **禁止连续分数**。
- **纪律不变量**：comparator **绝不读取** P/cell/family/archetype/domain 标签或 sealed 真值；输入恰好是两个 IR + 两段源文本；`compare` 内无随机、无时间、无网络、无 I/O。

### 3.9 Part VI（τ-bench 外部验证，未启动 GPU）

- 取代已关闭的 Part V，改用**作者生成的 τ-bench-v1-兼容取消费用-拒绝实例**（命名纪律：**严禁**称 "the τ-bench airline benchmark"）。
- 三个单侧假设（Holm m=3）：E-harm（trap(X) − trap(N) > 0）、X-protection、R-retention（非劣 > −5pp）。
- 主网格 240 × {N,R,X} = **720 cells**；harvest 最坏 2,160 episodes；**outcome-independent 封顶 ≤ 60 A5000·h，耗尽即 NOT_ESTIMATED**。
- 状态：`PART_VI_PREREG_V4.md` 为唯一有效协议；**冻结包待实化 → hash-only 冻结裁决 → 才能开工**。

---

## 4. 代码地图

```
agent_memory/
├── loop_file/loop.markdown          # 研究循环元规则（Gate A/B/C/D 定义、止损规则）
├── GATE_PROTOCOL.md                 # 预注册主文件（Part I–VI，420 行，全部冻结）
├── RESEARCH_LEDGER.md               # 台账：全部外部裁决记录 + 轮次记录（治理核心）
├── DECISION.md                      # 轮次决策链 + 止损计数
├── CAUSAL_STRUCTURE_AUDIT.md        # Gate B 六项审计
├── BOTTLENECK_PROFILE.md / GATE_FINDINGS.md   # Gate A 填数
├── LITERATURE_COLLISIONS.md         # 文献碰撞登记（每轮更新）
├── PAPER_PLAN.md / PAPER_POTENTIAL_REVIEW.md  # 论文规划与 §11 潜力审查
├── NEXT_ACTION.md                   # ⚠️ 已过期（停留在 08-10 上午）
├── iclr2027/                        # 论文本体（LaTeX，17pp，main.pdf 18 页）
│   └── sections/{intro,related,design,setup,findings,realization,
│                 deployment,boundaries,figures,discussion,appendix}.tex
├── analysis/                        # 负结果备忘（HC / H3）
├── review-stage/                    # auto-review-loop 3 轮记录（4/10→5/10→6/10）
├── ref/                             # 参考文献 PDF + 抽取文本（Xiong et al. 2026）
├── .aris/traces/                    # 外部讨论完整记录
│   ├── auto-review-loop/
│   └── p-estimation-adjudication/2026-08-10/   # ★ P 可得性 5 轮裁决（见 §9）
└── pilot/
    ├── SPEC.md                      # ★ 权威规格（验收标准在 §8）
    ├── program_dsl.py               # 程序 DSL + 4 archetype + oracle walker
    ├── env_relationalops.py         # SQLite 环境 + 工具 API + 终态谓词
    ├── generate_families.py         # 生成器（108KB，含 sealed oracle 输出）
    ├── harness.py                   # vLLM 离线 ReAct rollout 循环
    ├── run_pilot.py                 # 网格编排（shard/resume/retry/dry-run）
    ├── analyze.py                   # 四张核心图 + cluster bootstrap + TOST
    ├── configs/pilot.yaml           # 全部超参
    ├── tests/smoke.py               # 端到端冒烟（SPEC §8 验收）
    ├── audit/                       # Gate B 审计脚本与结果
    ├── systems/                     # H-C 三系统（raw/summary/procedural）+ MAPPING.md
    ├── h3/                          # H3 析因
    ├── dslice/                      # H-DC 决策感知压缩
    ├── gatec/                       # Gate C-lite 三个 baseline 实测
    ├── llama8b/                     # Llama 复现
    ├── external/                    # ALFWorld + Part V 代码包（已冻结留档）
    ├── tau_survey/                  # ★ Part VI（τ-bench）
    │   ├── PART_VI_PREREG_V4.md     # 唯一有效协议
    │   └── part6/                   # 生成器/harvest/detector/analyzer/freeze manifest
    └── peval/                       # ★ P 估计线
        ├── README.md                # P̂ v1 + GATE_EVAL 完整说明
        ├── build_pairs.py / p_evaluator.py / gate_eval.py
        ├── pairs.jsonl (640) / pair_scores.jsonl / P_EVAL_RESULTS.json / GATE_EVAL.json
        ├── PHI_D_EVALUATOR_PLAN.md  # φ+d 设计方案（经裁决）
        ├── BLICC_PLAN_DRAFT.md      # 接口信息上限普查方案草案（未冻结）
        └── phi_d/
            ├── SPEC.md / REPORT.md          # S0+S1
            ├── audit_expanded/              # prompted 时代忠实度审计（0/11 硬否决）
            ├── comparator_v0/               # DEMOTE 基线
            ├── sft2/                        # ★ SFT 数据生产 + LoRA 训练 + 门评测
            ├── sft2_eval/                   # ★ canonical 重抽 + SFT 时代审计（10/11）
            ├── s2/                          # ★ S2 rc1（冻结，未跑）
            └── s2_rc2/                      # ★ S2 rc2（撰写中）
```

---

## 5. 环境、数据与产物路径

### 5.1 环境

```bash
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python   # python 3.11
export HF_HOME=/work1/zixuan/cache/huggingface
export HF_HUB_OFFLINE=1          # 推荐，使模型选择确定
export OUTLINES_CACHE_DIR=/work1/zixuan/cache/outlines
```

实测版本：`torch 2.5.1+cu124` / `vllm 0.6.6.post1` / `transformers 4.57.6`
其他依赖：`sentence-transformers matplotlib pandas scipy statsmodels pyyaml peft`

### 5.2 模型

| 用途 | 模型 | revision |
|---|---|---|
| 主网格 worker | `Qwen/Qwen2.5-7B-Instruct` | `a09a3545` |
| 次级 worker | `Qwen/Qwen2.5-3B-Instruct` | — |
| smoke | `Qwen/Qwen2.5-1.5B-Instruct` | — |
| 二家族复现 | `Llama-3.1-8B-Instruct` | — |
| 嵌入（S 的第二视角） | `BAAI/bge-small-en-v1.5`（pinned），fallback `thenlper/gte-small` | — |
| **φ 抽取器 LoRA** | `/work1/zixuan/checkpoints/agent_memory/phi_sft/sft2/` (54MB) | — |

### 5.3 数据与产物

| 路径 | 大小 | 内容 |
|---|---|---|
| `/work1/zixuan/data/agent_memory/public_view/` | 19M | agent 可见：tasks / memories / tool_schema.json |
| `/work1/zixuan/data/agent_memory/sealed/` | 3.8M | **密封**：families/tasks_sealed/memories_sealed/cells/manifest/oracle_report/sim_report |
| `/work1/zixuan/data/agent_memory/alfworld/` | 2.3G | ALFWorld 数据（Part V 留档） |
| `/work1/zixuan/data/agent_memory/h3/` | 21M | H3 的 32 fresh families |
| `/work1/zixuan/outputs/agent_memory/pilot/` | 203M | **全部 rollouts JSONL + 分析产物** |
| `/work1/zixuan/outputs/agent_memory/part6_*` | ~3M | Part VI 计划与 detector 检查 |
| `/work1/zixuan/logs/agent_memory/` | — | 运行日志 |

**rollout 行结构**（关键，分析脚本都依赖它）：
```json
{"success": true, "meta": {"task_id","memory_id","cell","seed","family_idx","sibling_idx",
 "model","config_hash","git_commit","env_versions"}, "trajectory":[...],
 "compliance":..., "terminal_ok":..., "steps":..., "prompt_tokens":...}
```
文件名：`rollouts_{model}_shard{i}-of-{n}.jsonl`（主网格）、`rollouts_hc_*`、`rollouts_h3_*` 等。

---

## 6. 复现步骤

### 6.1 生成 benchmark（CPU，~分钟）

```bash
cd pilot
$PY generate_families.py --config configs/pilot.yaml
# → /work1/zixuan/data/agent_memory/{public_view,sealed}
# oracle validation 必须报 800/800，否则非零退出
```

### 6.2 隔离检查（必须无输出）

```bash
grep -r "family_id\|cell_id" /work1/zixuan/data/agent_memory/public_view
```

### 6.3 冒烟（1 GPU）

```bash
CUDA_VISIBLE_DEVICES=0 $PY harness.py --selfcheck --model qwen1.5b --config configs/pilot.yaml
CUDA_VISIBLE_DEVICES=0 $PY tests/smoke.py --config configs/pilot.yaml
```

### 6.4 主网格（10 GPU，约 1h）

```bash
for i in 0 1 2 3 4; do
  CUDA_VISIBLE_DEVICES=$i $PY run_pilot.py --model qwen3b --shard $i/5 \
    > /work1/zixuan/logs/agent_memory/pilot_qwen3b_shard$i.log 2>&1 &
done
for i in 5 6 7 8 9; do
  CUDA_VISIBLE_DEVICES=$i $PY run_pilot.py --model qwen7b --shard $((i-5))/5 \
    > /work1/zixuan/logs/agent_memory/pilot_qwen7b_shard$((i-5)).log 2>&1 &
done
# 崩溃后重跑同样命令：已完成的 rollout 单元会被跳过
```
> ⚠️ 7B 首跑用 `gpu_memory_utilization=0.6` 会失败，须用 `configs/pilot_7b.yaml`（0.85）。

### 6.5 分析

```bash
$PY analyze.py --config configs/pilot.yaml \
  --rollouts "/work1/zixuan/outputs/agent_memory/pilot/rollouts_*.jsonl" \
  --out /work1/zixuan/outputs/agent_memory/pilot/analysis
```

### 6.6 P 估计线（CPU，无需 GPU）

```bash
cd pilot/peval
$PY build_pairs.py          # ~5s  → pairs.jsonl (640)
$PY p_evaluator.py          # ~7min → P_EVAL_RESULTS.json, pair_scores.jsonl
$PY gate_eval.py --model qwen7b   # ~10s
$PY gate_eval.py --model qwen3b
```

### 6.7 SFT 抽取器（GPU 1 张）

```bash
cd pilot/peval/phi_d/sft2
$PY mint_all.py             # 4,000 文本铸造（CPU）
$PY train_lora.py           # LoRA 训练
$PY eval_extract.py         # 8 门评测
cd ../sft2_eval
$PY extract_canonical_sft.py   # canonical 532 重抽（GPU，~516s）
$PY audit_sft_canonical.py     # 扩编审计 → 10/11 HARD VETO
```

### 6.8 论文编译

```bash
cd iclr2027 && pdflatex main && bibtex main && pdflatex main && pdflatex main
# 目标：0 错误 / 0 overfull / 0 未定义引用
```

---

## 7. 治理规则（本项目的灵魂，务必遵守）

这些规则是这个项目最有价值的资产，比任何单个结果都重要。

1. **负结果处置规则**（用户指令，优先级高于默认流程）：出现负结果（NO_GO、识别失败、与预期相悖的稳定结果）时，**先自行仔细分析成因，然后必须与 GPT-5.6（Codex）讨论之后，才能进行下一步动作**。讨论前冻结：不启动新实验、不修改 hypothesis、不写判定结论。要点须记入台账"外部讨论记录"。
2. **阈值先冻结后看数据**。不得为保持 loop 运行而放宽 `GATE_PROTOCOL.md` 已登记阈值。
3. **GO 与 NO_GO 同等详细记录。**
4. **禁止 post-result power chasing**：不得为把效应推过显著性阈值而追加算力。
5. **未达门槛的后续实验不再重启同构设计**；restart 需新预注册。
6. **oracle 隔离**：sealed 标签只用于评分，绝不进入模型输入或规则选择。
7. **分析脚本必须先于任何 outcome 检视 commit。**
8. **止损计数**：Gate A/B 连续 NO_GO 3 次触发修正、总计 6 次触发终止。当前假设层连续 NO_GO = **2**。
9. **措辞红线**（写作时）：
   - 不写 "first to causally audit individual memories"（Rocchi 已占）；
   - 不声称"确认 coverage 驱动 replay"（用 "supported-but-unresolved"）；
   - 全称尺度只在 frozen Qwen2.5 3B/7B 范围内声明；
   - 避免 "proof"、"zero leakage"，一律 "no evidence detected at this audit strength"；
   - 禁用 Skill-Pro 碰撞措辞（见 §3.1）。

---

## 8. 已知负结果与禁区（不要重复踩）

| 禁区 | 原因 |
|---|---|
| 用 LLM judge 判程序等价 | 实测 A10 100% 判错；STITCH 式 AUC 0.508 |
| 用 embedding 相似度当 P 的代理 | S=1 切面 AUC **0.529 = 硬币** |
| 训练 P 判别器并声称泛化 | P̂ v1 LOAO 0.590，conditional_write 0.408（低于随机）——标签枚举了机制 |
| 把 generator 的 `z` / procedural card / `oracle_trajectory()` 当"可执行件"证据 | **oracle laundering**：`MAPPING.md:15`、`build_raw_cards.py:156` 证明它们直接来自 sealed roles |
| 用现有 640 轨迹做多实例泛化 | `build_raw_cards.py:19-21`：4 张卡共享同一 source task，只换 decode seed，**不构成不同实例**；且 188/640 是 oracle fallback |
| 重启 Part V 同构设计 | 结构性天花板，终态纪律禁止 |
| 在 comparator v0 的 640 对上继续调规则 | 已 DEMOTE，一次跑完不再迭代 |
| 只报 pooled AUC | 主指标必须是 4 个留出 archetype 的 **macro 均值** |

---

## 9. P 的部署可得性：5 轮外部裁决结论（2026-08-10）

完整记录：[.aris/traces/p-estimation-adjudication/2026-08-10/](.aris/traces/p-estimation-adjudication/2026-08-10/)（R1–R5 的 prompt 与 reply）。方案草案：[pilot/peval/BLICC_PLAN_DRAFT.md](pilot/peval/BLICC_PLAN_DRAFT.md)。

### 9.1 核心结论

> **P 在部署态不是"待估计的量"。要么改变观测（让它可识别），要么改变目标（不再需要它）。**

**P 的三个性质各杀死一类方法**：
1. **关系性**（一条 A01 卡本身完全正确，问题只在于与这个目标不匹配）→ 杀死所有一元质量过滤器；
2. **evaluator-only**（部署无真值）→ 杀死"从日志免费学标签"；
3. **需跨未见机制泛化** → 杀死监督分类器。

**正确的 estimand**：三值部分识别
```
I_P(O) = {1[z_x ≡ z_m] : z_x ∈ Γ_x(O), z_m ∈ Γ_m(O)}
       → {1} certified match / {0} certified conflict / {0,1} unresolved
```
**记号纪律**：不要叫 `P̃`，叫 `C_R(O) ∈ {CONFLICT, UNRESOLVED}`；**`¬CONFLICT` 绝不能读成 P=1**。

### 9.2 路线排序（R1–R5）

| 路线 | 裁决 |
|---|---|
| **F′ 接口改造**（只保留 pair-discriminating witness + 用 sealed P 测接口的 P-identifiability value） | GO to develop，但 novelty confidence **中等偏低**，正式 claim 前必须专门检索 `skill verification / test-carrying agents / mutation-based workflow validation / distinguishing tests` |
| **D 执行式验证** | GO with major amendment（见 9.3） |
| **B utility U**（randomized canary + propensity → IPW/DR） | GO，部署主线 |
| **A SFT 抽取器 + 确定性比较器** | GO，benchmark-only（**已执行且成功，见 §3.7–3.8**） |
| **C harmful-flip 直接预测** | NO_GO standalone（联合反事实，单臂日志不可点识别） |
| **E 选择性风险控制** | 不是路线，是所有不完美判定器的**强制外壳** |

### 9.3 为什么"执行式验证"不能单独得到 P（三个代码级反例）

1. **不同签名、相同终态**：P1 的 J1/J2 签名不同（J2 多一次 policy READ），但 θ 相同时终态完全相同；
2. **相同签名、不同终态**：θ 不属于等价类，两个 P=1 实例可在同一状态走不同 branch；
3. **偏序 ≠ 终态语义**：识别 archive-before-delete 这类边**必须注入故障**。

### 9.4 冻结的验证门（若建 conflict certifier）

**Gate 1 证书有效性**：`VetoPrec` 单侧 95% LCB ≥0.95；`FalseVeto(P=1)` UCB ≤0.05（对 A10/A11 及逐机制分别成立）；A01 `VetoCov` LCB ≥0.20。
**Gate 2 准入安全**：A01 accept UCB ≤0.10；A11 retain LCB ≥0.50；**新增 A10 retain LCB ≥0.50**（conflict-only 最危险的失败正是杀掉跨表面 P=1）。
**Gate 3 策略价值**：family-cluster bootstrap（40 簇）；对最佳可部署 baseline 配对非劣 margin −3pp；必须做 `risk-only` vs `certifier+risk` ablation。

**样本量**：零错误时 precision LCB≥0.95 需 **59 次实际触发**；四项 Bonferroni 需 **86 次/机制**；覆盖门 20% 时需约 **430 个 P=0 族/机制**。100 族/机制只够 screening。

**防 generator 自证**：family split 在 rendering 前完成；confirm 用与开发集**完全不共享实现的 renderer**；certifier 先 hash；第五/第六机制由**独立 challenger 在 hash 之后**选择（含 P=1 正控）；challenge 失败不得 pooled rescue。

### 9.5 本次会话新增的实证（探索性，未冻结，不可用于挑选规则）

全部基于冻结 rollouts + 已注册 P̂ 分数，**零新增算力**：

**(a) 检索器在 A11/A01 之间扔硬币**（GATE_EVAL.json）
- 真实 embedding 检索器 top-1 **100% 落在 S=1**：A11 380/640，A01 260/640；
- 组内中位数 `|sim_embed(A11) − sim_embed(A01)| = 0.0032`。
- → 部署里 2×2 塌成 1×2，全部问题就是"分开 A11 和 A01"。**此事实尚未写进论文。**

**(b) 用可部署判据重做分解 → 趋势反转（不是衰减）**
| 7B | τ_struct | τ_replay | τ_trap |
|---|---:|---:|---:|
| 真 P×S（论文） | +9.2pp | **+14.4pp** | +8.1pp |
| LOAO P̂@0.5 × S | +20.7pp | **+1.6pp** | +14.6pp |

3B 的 τ_struct 从 **−6.6pp 翻成 +5.1pp**（scale reversal 被抹掉）。
原因：误分类**与结果相关**（differential）。非差分误分类只衰减保号，差分可任意翻转。
→ **"下游趋势一致"不能当验证标准**；**"没有 oracle 你会得出相反结论"是论文该有的 appendix 表。**

**(c) 但同一判据的策略价值保住大半**（7B，640 实例，精确非估计）
| 策略 | uplift vs 不用记忆 | 接受率 | A01 接受率 |
|---|---:|---:|---:|
| always_admit | +5.16pp | 1.000 | 1.00 |
| oracle-P（**不是天花板**） | +8.13pp | — | 0.00 |
| P̂ family-CV @0.6 | +8.59pp | 0.575 | 0.17 |
| P̂ LOAO @0.5 | **+6.25pp** | 0.306 | 0.23 |
| **真结果 oracle（top-1/N）** | **+14.38pp** | — | — |
| 真结果 oracle（5 选 1） | +28.44pp | — | — |

→ **测量效度与决策效度是两个不同目标，互不蕴含。**

**(d) 控制住 S 之后，P 预测的是风险不是均值**
| 7B | 全部 640 对 | **S=1 only（检索器实际返回）** |
|---|---|---|
| sim_embed → 效用 | +0.216 | **+0.105** |
| P → 效用 | +0.167 | **+0.208** |
| sim_embed → **伤害** | −0.161 | **−0.021（≈0）** |
| P → **伤害** | −0.119 | **−0.134** |

（Spearman ρ，n=640 / 320。3B 全线很弱。）
→ **进入检索集之后，相似度对伤害是零信息。**

**(e) 纯 P 对比（控制 S）的下行风险**
`A01 − A11` joint HFR：7B **+5.00pp** CI [+2.19, +8.12]；3B **+3.44pp** CI [+0.16, +6.72]（family-cluster bootstrap, 20k）。
→ 这是 P 构念效度的实证：**同样表面相似度下，程序不匹配显著多出"本来能做对却被做坏"。**

### 9.6 待办：BLICC（未冻结方案）

`Blind Lawful-Interface Ceiling Census`：在 532 文本 / 640 对上测"文本 → +schema → +provenance"每级能认证多少 P。5 天 CPU。二值 PASS 门与冻结清单见 [BLICC_PLAN_DRAFT.md](pilot/peval/BLICC_PLAN_DRAFT.md)。
**接口梯度中 X（可执行件）与 W（witness）本轮删除**——本 benchmark 无合法来源（见 §8 禁区）。

---

## 10. 论文状态

- **文件**：`iclr2027/main.tex` + `sections/*.tex`，编译 18 页 PDF（正文 17pp）。
- **标题**：*What Are Agent-Memory Gains Made Of? Factorially Decomposing Replay, Structural Transfer, and Surface Traps with Evaluator-Only Program Oracles*
- **贡献计数 2/3**：识别设计 ✔、会改变结论的经验发现 ✔、**打赢已发表 admission baseline 的方法结果 ✘**（TRU-Mem 已纪律性移除）。
- **外部评审**：auto-review-loop 3 轮 4/10 → 5/10 → **6/10 "Almost"**（达停止条件终止）。
- **相机就绪前余项**：图 vector 化、匿名复核、repo 脱敏、appendix 的 artifact 仓库地址改真仓。
- **已知弱点**（真问题，早在账上）：
  1. 外部效度——单一合成 SQLite 域，且签名相关位逐字写在文本里；Part V 外部验证线已关闭；
  2. H-DC provenance 污染（29.4% oracle fallback）；
  3. 缺方法胜绩。
- **资源裁决**：**不推迟投稿**。"把 P 线塞进当前论文"已被裁 NO_GO；接口线走通了是论文 #2。

---

## 11. 下一步（按优先级）

1. **S2 rc2 定稿 → 冻结 hash → 640 对一次跑**（当前活跃，另一会话在做）。这是 φ+d 线的收官动作。
   - 跑完必须报：`VetoPrec / VetoCov / FalseVeto`（分 A01/A10/A11 与逐机制），以及 §9.4 三个 Gate。
2. **把"检索器扔硬币"事实补进论文**（§9.5a，纯写作，数据已在冻结网格上）。这是从测量到系统指导的桥梁。
3. **"没有 oracle 会得出相反结论"做成 appendix 表**（§9.5b）。这是对"为什么需要密封 oracle"的最强论证。
4. **Part VI 冻结包实化 → hash-only 冻结裁决 → harvest**（≤60 A5000·h）。
5. 可选：**fallback-free re-harvest**（H-DC 真实部署验证，需新算力 + 前置裁决）。
6. 可选：BLICC（§9.6）。

---

## 12. 迁移到新服务器的注意事项

1. **路径全部硬编码在 `configs/*.yaml` 与脚本常量里**，按 `/work1/zixuan/` 前缀批量替换；`CLAUDE.md` 的工作区硬规则（projects/data/envs/cache/outputs/checkpoints/logs 分离）建议沿用。
2. **必须迁移的产物**（否则无法复现分析）：
   - `data/agent_memory/{public_view,sealed}`（23M，**sealed 是全部结果的真值来源**）
   - `outputs/agent_memory/pilot/`（203M，全部 rollouts——**重跑需 GPU 数小时且 decode 不保证逐位一致**）
   - `checkpoints/agent_memory/phi_sft/sft2/`（54M，φ 抽取器 LoRA）
3. **确定性依赖**：NumPy 1.26.4（Part V 冻结钉死）、vLLM 0.6.6.post1、`HF_HUB_OFFLINE=1`、embedding 模型 pin 到 `BAAI/bge-small-en-v1.5`。**版本漂移会破坏 hash 核验。**
4. **git 历史是证据链的一部分**：所有冻结 hash、prompt sha、config hash 都写在 commit message 与 receipt JSON 里，务必完整迁移 `.git`。
5. **`git_commit` 字段在早期 manifest 里记为 "unknown"**（当时目录还不是 git 仓库），那一期以 config hash 作复现锚点。
6. **并发风险**：`pilot/peval/phi_d/` 历史上出过并发子代理撞目录事故（REPORT.md §5 有完整披露与隔离记录）。多会话作业务必分目录。
7. **Codex（GPT-5.6）通道**：治理规则依赖它。CLI 在 VSCode ChatGPT 扩展内：
   ```
   /home/zixuan/.vscode-server/extensions/openai.chatgpt-<ver>-linux-x64/bin/linux-x86_64/codex
   ```
   **扩展版本号会变**，换机后先 `ls ~/.vscode-server/extensions | grep chatgpt` 重新定位；配置在 `~/.codex/config.toml`（model `gpt-5.6-sol`，effort high），鉴权 `~/.codex/auth.json`。
   非交互用法：`codex exec --sandbox read-only -o out.md - < prompt.md`；续话用 `codex exec resume <session_id> -c sandbox_mode=read-only`（**`resume` 不接受 `--sandbox` 参数**）。单轮 high-effort 可能跑 10–20 分钟，务必后台运行。

---

## 13. 未决问题清单

| 问题 | 状态 |
|---|---|
| S2 rc2 在 640 对上的真实表现 | **未知**，rc1/rc2 均未执行 |
| conflict certifier 能否过 §9.4 三个 Gate | 未知；prompted 时代 comparator v0 全灭，SFT 时代未测 |
| 文本能认证多少 P（BLICC） | 未测；裁决者预判 **FAIL**（签名位逐字明写 → T 点贴顶） |
| H-DC 在真实模型轨迹上是否成立 | **未确立**（+0.041 CI 跨 0），需 fallback-free re-harvest |
| Part VI 是否能达可估计门槛 | 未知，冻结包待实化 |
| 方法论文（agent memory retrieval）是否立项 | **未裁决**；动机图数据已备（§9.5a,d） |
| `NEXT_ACTION.md` | **已过期**，停留在 08-10 上午，勿依赖 |
| 台账 Round 1 checklist 233–236 行 | 与实际状态自相矛盾（历史遗留） |
| 台账"资源预算跟踪：累计 0 GPU 小时" | 未更新，实际已 33k+ rollouts |

---

## 14. 一段话总结给接手的人

这个项目最有价值的三样东西，按顺序是：**(1) 那套"先冻结阈值、负结果必须外部裁决、GO/NO_GO 同等记录"的治理纪律**——它挡掉了至少三次自欺（H-C 重标、H3 追算力、Part V 硬上）；**(2) 完整析因 + 密封 oracle 这个资产**——640 个实例 × 6 cells × 2 模型全齐，任何准入/路由策略都能精确离线评估、零估计误差，这是别人做不到的；**(3) 一串诚实的负结果**——相似度、LLM judge、监督判别器在"分开 A11 和 A01"这一刀上全部失败，这本身就是对社区最有用的信息。

接手时最容易犯的错误是：看到某条线"差一点就成了"，就去放宽一个已冻结的阈值。**不要那样做。** 这个项目到今天还站得住，靠的就是没那样做过。
