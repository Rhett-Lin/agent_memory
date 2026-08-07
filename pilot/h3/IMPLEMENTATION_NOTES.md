# H3 IMPLEMENTATION_NOTES（2026-08-08）

> 一切构造决策、偏差与可复现命令的记录。配套：`GATE_PROTOCOL.md` Part III（预注册，冻结）、`CONSTRUCTION_RULINGS.md`（parent 的五项构造裁决）、`h3_maxaware_inference.json`（max-stat 路线，**标注反保守禁用**）、`h3_inference_8tests.json`（采纳路线）。

## 预注册 vs 实现的偏差登记

| 项 | 预注册（冻结） | 实现 | 处置 |
|---|---|---|---|
| family 数 | 24，功效不足可升到 32 | 功效模拟 power(24)=0.640,<0.8 → **32**（冻结上限）| 按 §16 规则执行，记录在 `power_sim.json` |
| transcript 素材 | §14.5 用 qwen7b 真实 success rollout，无 oracle fallback | canonical-deterministic 渲染（从 sealed oracle_plan 执行轨迹派生；64/64 源任务真实执行过 oracle walker） | parent 裁决 R1：接受。§14.2 与 §14.5 互斥，内容匹配优先；生态维由 eco 臂承担真实 rollout 的风险敞口 |
| prefix 切法 | 同 H-C 的"300-token 处截断规则" | 命题边界，恰好只缺 write-decision+finish（断言 512/512 全过） | parent 裁决 R2：接受；token 失衡是覆盖的固有属性；token 协变量稳健性补做 |
| 校准 | SMD<0.2 | transcript_complete 均 713 tok，script_prefix 均 144，剪跨 arm >4 | 不满足 SMD 目标，按 R2/R3 以协变量方案替代，如实报告 |
| eco 构造 | "最有自然转录按 H-C raw 规则截断" | 与 transcript_complete 同源的完整转录做硬 300-token 截断（可断行） | 实测仍 suffit：eco ≈ H-C 的 raw 数值（7B −0.003 vs H-C −0.014）；与 prefix 0/512 重合 |
| rely grid 计数 | 24×4×5×3 | 32×4×{A10,A11}×5×3 = 960 arm-rollouts + N/Q 参考 384 → per-model 4608，双 model 9216 | power 上限 rules；N diff 文件错峰合并（`rollouts_h3_qwen7b_ndiff.jsonl`） |

## 推断路线裁定

- 主推断：`h3_inference_8tests.json`（GPT-5.6 route b：ε_form、ε_int、cov_script、cov_transcript 各自边际对比 × 2 models，Holm m=8）。
- 被否路线：`h3_maxaware_inference.json`（max-stat 试图保住"ε_cov = 较大者"的预注册 formulation；GPT-5.6 判"先选大号再算 p 是反保守"，已封存、只作历史记录，不得引用其 p=0.0004）。
- τ_rl(transcript_complete) 的 TOST：±3pp margin，两模型拒绝等价（实质性非零）。
- 敏感性：token-count LPM with family-cluster bootstrap（结果见 H3_RESULTS.json；7B 调整后 ε_form 更负 −0.102 SIG−）。

## 网格执行记录

- qwen7b：2026-08-07 21:02 → 08-08 02:36，8 分片（GPU0–3,5–8），4608(=768×5+384+384) 条，含 ndiff；parseable 99.8%。
- qwen3b：2026-08-08 05:41 起，8 分片（GPU0–3,5–8；GPU4/9 留空避开其他用户任务），4608 条；parseable 96.6%。
- 中间曾因共享节点上他名用户任务（GPU6/GPU7）短暂避让；无碰撞确认后恢复。
- 失败/超时事件：agent-7 两次 timeout（canonical 设计期）、agent-8 一次 timeout（网格后段）；中断期间分析与判定全部由 parent 接手续跑，未重跑任何 rollout。

## 可复现命令（从 /work1/zixuan/projects/agent_memory/pilot）

```bash
export HF_HOME=/work1/zixuan/cache/huggingface
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
# 1) 32 个 fresh families（oracle 640/640）
$PY h3/gen_fresh_families.py --config h3/configs/h3.yaml
# 2) canonical 卡（SA PASS、命题断言、隔离扫描）
$PY h3/canonical.py
# 3) 盲标注 + 六点验收
$PY h3/blind_annotate.py && $PY h3/acceptance.py
# 4) 网格（每 GPU 一片）
for i in 0 1 2 3 4 5 6 7; do
  CUDA_VISIBLE_DEVICES=$((i<4?i:i+1)) $PY h3/run_grid.py --model qwen7b --shard $i/8 &
done
# 5) 分析（冻结 estimand）
$PY h3/analyze.py
```

数据：
- cards：`/work1/zixuan/data/agent_memory/h3/public_view/cards/{arm}/<memory_id>.json`（2560 张 + map）
- rollouts：`/work1/zixuan/outputs/agent_memory/pilot/h3/rollouts_*.jsonl`
- 结果 JSON：`pilot/h3/H3_RESULTS.json`、`h3_inference_8tests.json`、`h3_maxaware_inference.json`（禁用路线，存档用）、`acceptance.json`

## 冻结措辞约束（parent 与 GPT-5.6 共同确立）

1. H3 只能写"formal NO_GO + informative clarification"：杀的是"大 script-over-transcript 解释"，不能写"确认 coverage 驱动"。
2. 合法写法："complete transcripts realize materially positive replay in both models（TOST 拒绝 ±3pp 等价）；coverage/truncation 方向性支持但未确认"
3. eco 的表述必须含"在 300-token 截断构建下"限定；max-stat 路线的任何 p 值不得引用、不得出现在论文或台账结论区。
