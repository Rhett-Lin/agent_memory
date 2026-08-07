# CausalMemBench Mini-Pilot 实现规格（Round 1）

依据：`loop_file/loop.markdown` §16（第一轮任务）、§7（Gate A）；`tech_report/causalmemagent_top_venue_technical_route.md` §6.2/§6.5/§6.6/§6.9/§16。实现前必须先读这两个文件的相关章节。

## 0. 目标

在单一 RelationalOps（SQLite）环境上执行 30–50 个 latent program families 的 Stage A 实验（A00/A01/A10/A11 + N/Q），产出四张核心图和 Gate A 判定所需的全部原始数据。**不实现 TRU-Mem，不扩展 Stage B/C/D。**

## 1. 代码布局（project root = /work1/zixuan/projects/agent_memory）

```
pilot/
  SPEC.md                 # 本文件
  program_dsl.py          # partial-order 程序规格 + oracle walker
  env_relationalops.py    # SQLite 环境、工具 API、终态谓词
  generate_families.py    # family/sibling/near-miss/candidate-memory 生成器（含 sealed oracle 输出）
  harness.py              # vLLM 离线推理的 ReAct 式 agent rollout 循环（固定注入 memory）
  run_pilot.py            # 实验网格编排：family × sibling × cell × seed × model → JSONL
  analyze.py              # 四张核心图 + 统计（cluster bootstrap、equivalence test）
  configs/pilot.yaml      # 全部超参（seed、token/step 预算、路径、模型路径）
  tests/smoke.py          # 端到端 smoke：2 families、Qwen2.5-1.5B、全部六 cells 各跑通
data -> /work1/zixuan/data/agent_memory/           # 生成的 benchmark（public view + sealed oracle 分开放）
outputs -> /work1/zixuan/outputs/agent_memory/     # 原始 JSONL、图、表格
logs -> /work1/zixuan/logs/agent_memory/
```

软链接或在 configs 里写死绝对路径均可，但**严禁**把数据写进 /tmp 或 /home。

## 2. RelationalOps 环境（单一环境）

SQLite 状态 + 程序化工具。实现 4 类业务模板域（CRM、库存、工单、日历），共用一套工具协议：

- 工具（HTTP 不必，直接 Python 函数调用，由 harness 解析 agent 的 JSON tool-call）：`list_tables`、`read(table, filter)`、`aggregate(...)`、`insert/update/delete(table, record, where)`、`finish(answer)`。
- 每次 rollout 在深拷贝的 DB 上进行；终态由**程序化谓词**判定（查询 DB 检查目标行/字段/计数/不存在性），不用 LLM judge。
- 状态生成随机化：实体名（人名/公司/SKU/工单号）、字段值、distractor 记录数、join 深度（1–3 表）、missing-field 与 permission 错误注入。

## 3. Latent program 与 sealed oracle

- 程序规格 z = (G_prec, C_safety, C_terminal, B_recovery)：必要偏序依赖（如"先读订单→才能退款"）、安全约束、合法终态、错误恢复条件。等价类 Π(z) = 满足全部约束的所有 plan（允许无依赖步骤交换顺序）。
- 从 ~6-8 个手写程序 schema 参数化出 30–50 个 families（参数：领域模板、表结构、谓词内容、分支条件）。每 family ≥4 个 program-preserving siblings（同一 z，不同表面实体/措辞/叙事模板/工具命名细节），外加 ≥1 个 near-miss 版本（表面极像，但关键前置条件、分支或动作顺序不同 → 属于另一等价类 z′）。
- **Oracle 隔离铁律**（技术报告 §6.2.1）：z、family ID、transformation ID、near-miss label、P/S 标签只写入 `data/sealed/`（evaluator 专用）；agent 可见的只有 task text、tool schema、通过工具暴露的 state。utility/harness 代码不得读 sealed。生成器同时产出 oracle plan（可执行的最短合法动作序列）。
- Oracle walker 必须对每个 sibling 实际执行 oracle plan，验证 100% 到达合法终态（§6.9-1），不通过的 family 重新采样或修复。

## 4. Candidate memories（Stage A fixed injection）

每 target sibling × cell 配一条 200–300 token 的自然语言 procedural card（schema：goal/preconditions/procedure/postconditions/failure_guards），从"源 episode"派生：

| Cell | P | S | 构造 |
|---|---|---|---|
| A11 | 1 | 1 | 同程序、高表面相似：同 family 另一 sibling 的正确 procedure，实体/措辞高度重合 |
| A10 | 1 | 0 | 同程序、低表面相似：同 family 不同领域模板渲染的 sibling 的正确 procedure（实体名、动词、叙事风格全部不同） |
| A01 | 0 | 1 | near-miss：表面高度相似但程序错误（来自 z′ 的 procedure，缺关键前置/顺序不同/约束不同） |
| A00 | 0 | 0 | unrelated control：不同领域不同程序的正确 procedure（对别的任务是对的） |
| Q | – | – | sham/placebo：长度、格式、成功标签、位置匹配，但内容为任务无关 procedure（如烹饪流程改写版），估 context/format effect |
| N | – | – | 无注入 |

- token 长度用 tokenizer 实测，六 cells 分布匹配（§6.9-4）；记录每条 memory 的 token 数。
- S 的操作化：用 (a) token overlap、(b) 冻结 embedding 双指标校准 high/low 桶，记录连续值（供后续 continuous-S 敏感性分析）。embedding 模型固定为 `BAAI/bge-small-en-v1.5`（已缓存于 HF_HOME，CPU 推理已验证；写进 config）。high/low 阈值写进 config 并由生成器验证分桶正确。
- 文本模板分配用 Latin-square/counterbalancing，避免某模板固定落某 cell（§6.7）。
- memory 中**禁止**出现 family ID / cell 标签 / 任何 oracle 编码特征（生成后用脚本自动 grep 校验）。

## 5. Agent harness

- vLLM 离线引擎（`vllm.LLM`），模型：Qwen2.5-3B-Instruct 与 Qwen2.5-7B-Instruct（HF 缓存已在 /work1/zixuan/cache/huggingface/hub）。smoke 用已缓存的 Qwen2.5-1.5B-Instruct。
- ReAct 循环：system prompt 固定（说明工具协议 + 有一段 [MEMORY] 区块的格式）；每个 step 输出 `{"tool": ..., "args": ...}` 或 `finish`。批量推进：所有 active episode 同步 step（vLLM generate 批量）。
- 预算：max_steps=12，每 step max_tokens=512，temperature=0.7、top_p=0.9，seed 显式固定（配对设计：同一 sibling × seed 组合下六 cells 用相同随机数种子生成初始状态，仅 memory 不同）。
- 记录：完整 trajectory（每 step raw completion + parsed action + tool result）、token 用量、终态谓词结果、是否显式引用/遵循 memory 的启发式指标（compliance： procedure 步骤字符串与 action 序列的匹配率 + memory 行被复述的 n-gram 重合，写明是启发式）。
- 推理前先做 **instruction-following 自检**：N 条件下跑 5 个任务，确认 parseable action 率 >90%，否则修 prompt/解析器。

## 6. 实验网格（run_pilot.py）

- families：PILOT_N_FAMILIES=40（config 可调，30–50 区间）；每 family 取 4 个 target siblings × {A00,A01,A10,A11,N,Q} × 4 seeds × 2 models = 40×4×6×4×2 = 15360 rollouts 的上限；允许 config 缩小（先 3B 全量 + 7B 半量也可，但 grid 必须可由单参数复原）。
- 调度：vLLM 每模型占 1–2 GPU；多 GPU 用 `CUDA_VISIBLE_DEVICES` 起多进程分片（按 family 分）。失败 rollout 重试 ≤2 次并落盘错误日志。
- 原始输出 `outputs/agent_memory/pilot/rollouts_*.jsonl`，每行一个 rollout 的完整记录（含 git commit、config hash、模型、vllm 版本、GPU 型号、seed）。

## 7. 分析（analyze.py）→ 四张核心图

1. P×S 四格成功率（分模型，带 family-cluster bootstrap 95% CI）；
2. 四格相对 N、相对 Q 的 uplift（risk difference + CI）；
3. memory–target embedding 相似度（连续）与 paired uplift 的散点 + 相关；
4. A01 的 paired harmful flip：可配对种子上 `N=1 & A01=0` 的比例（无法严格配对时报 marginal risks + bootstrap CI，并在图注说明）。
另输出：六 cells token 长度平衡表、no-memory sibling 难度 equivalence test（TOST，margin 在 config，默认 ±7pp）、compliance 汇总、oracle 验证报告。全部 JSON/CSV 落盘。

## 8. 验收标准（smoke 必须通过才算实现完成）

1. `tests/smoke.py`：2 families × 六 cells × 1 seed × Qwen2.5-1.5B 全程跑通，产出合法 JSONL 与四张图占位；
2. oracle walker 报告 100% 合法终态；
3. `grep -r "family_id\|cell_id" data/public_view` 无命中（除白名单字段）；
4. 难度初校准：1.5B 在 N 条件下的成功率落入 20–80%（pilot 正式跑前需用 3B 复核到 30–70%，可通过 config 调 distractor 数/步骤数校准）；
5. 全部运行命令、环境、版本写进 `pilot/README.md` 的 Reproduce 一节。

## 9. 严格不要做

- 不做 retrieval（Stage D）、不做 exact-exposure 嵌套（Stage B）、不做 D/I/V 切片（Stage C）；
- 不训练任何模型；不实现 utility predictor；不碰 TRU-Mem；
- 不伪造任何 rollout 数据；跑不动就报瓶颈，禁止 mock 成功结果。
